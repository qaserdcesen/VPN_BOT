import json
import ssl
from typing import Dict
import aiohttp
import os
from bot.config import API_BASE_URL, INBOUND_ID, API_USERNAME, API_PASSWORD, COOKIES_FILE

class VPNService:
    def __init__(self):
        self.api_base_url = API_BASE_URL
        self.inbound_id = INBOUND_ID
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        self.cookies = self._load_cookies()
        
    def _load_cookies(self):
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, 'r') as f:
                return json.load(f)
        return None
        
    def _save_cookies(self, cookies):
        os.makedirs(os.path.dirname(COOKIES_FILE), exist_ok=True)
        with open(COOKIES_FILE, 'w') as f:
            json.dump(cookies, f)

    async def _ensure_auth(self, session):
        if not self.cookies:
            async with session.post(
                f"{API_BASE_URL}/login",
                json={"username": API_USERNAME, "password": API_PASSWORD}
            ) as response:
                if response.status == 200:
                    self.cookies = response.cookies
                    self._save_cookies(dict(response.cookies))

    async def create_client(self, nickname: str, uuid: str, gb_limit: int = 5) -> Dict:
        headers = {"Accept": "application/json"}
        client_data = {
            "id": self.inbound_id,
            "settings": {
                "clients": [{
                    "id": uuid,
                    "flow": "",
                    "email": nickname,
                    "limitIp": 1,
                    "totalGB": gb_limit * 1024 * 1024 * 1024,
                    "expiryTime": 0,
                    "enable": True,
                    "tgId": "",
                    "subId": "",
                    "reset": 0
                }]
            }
        }

        async with aiohttp.ClientSession(cookies=self.cookies) as session:
            await self._ensure_auth(session)
            # Создание клиента
            async with session.post(
                f"{self.api_base_url}/panel/api/inbounds/addClient",
                headers=headers,
                json=client_data,
                ssl=self.ssl_context
            ) as response:
                if response.status != 200:
                    raise Exception(f"Ошибка при создании клиента: {await response.text()}")
                
            # Обновление настроек клиента
            update_data = {
                "id": self.inbound_id,
                "settings": json.dumps({
                    "clients": [{
                        "id": uuid,
                        "flow": "",
                        "email": nickname,
                        "limitIp": 1,
                        "totalGB": gb_limit * 1024 * 1024 * 1024,
                        "expiryTime": 0,
                        "enable": True,
                        "tgId": "",
                        "subId": f"sub-{uuid}",
                        "reset": 0
                    }]
                })
            }
            
            async with session.post(
                f"{self.api_base_url}/panel/api/inbounds/updateClient/{uuid}",
                json=update_data,
                headers=headers,
                ssl=self.ssl_context
            ) as response:
                if response.status != 200:
                    raise Exception(f"Ошибка при обновлении клиента: {await response.text()}")
                
                return await response.json()

    async def delete_client(self, uuid: str) -> bool:
        headers = {"Accept": "application/json"}
        
        async with aiohttp.ClientSession(cookies=self.cookies) as session:
            async with session.post(
                f"{self.api_base_url}/panel/api/inbounds/delClient/{uuid}",
                headers=headers,
                ssl=self.ssl_context
            ) as response:
                return response.status == 200 

    async def create_config(self, nickname: str, uuid: str) -> dict:
        async with aiohttp.ClientSession(cookies=self.cookies) as session:
            await self._ensure_auth(session)
            
            # Ваш существующий код создания конфига с фиксированными параметрами
            client_data = {
                "id": "ваш_inbound_id",
                "settings": {
                    "clients": [{
                        "id": uuid,
                        "email": nickname,
                        "limitIp": 3,  # 3 IP
                        "totalGB": 2 * 1024 * 1024 * 1024,  # 2 GB
                        "enable": True
                    }]
                }
            }
            
            # Остальной код создания и обновления клиента...
            return {"status": "success", "config": "конфиг"}

    async def update_limits(self, uuid: str, gb_limit: int, ip_limit: int) -> bool:
        # Метод для обновления лимитов после оплаты
        async with aiohttp.ClientSession(cookies=self.cookies) as session:
            await self._ensure_auth(session)
            # Код обновления лимитов... 