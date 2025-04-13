import json
import ssl
from typing import Dict
import aiohttp
import os
from bot.config import API_BASE_URL, INBOUND_ID, API_USERNAME, API_PASSWORD, COOKIES_FILE
from yarl import URL

class VPNService:
    def __init__(self):
        self.base_url = API_BASE_URL.rstrip('/')  # Убираем слеш в конце если есть
        self.username = API_USERNAME
        self.password = API_PASSWORD
        self.inbound_id = int(INBOUND_ID)
        self.cookies_file = COOKIES_FILE
        
        # Создаем директорию для cookies если её нет
        os.makedirs(os.path.dirname(self.cookies_file), exist_ok=True)
        
        # Настройка SSL для работы с самоподписанным сертификатом
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        self.cookies = self._load_cookies()
        
    def _load_cookies(self):
        try:
            if os.path.exists(self.cookies_file) and os.path.getsize(self.cookies_file) > 0:
                with open(self.cookies_file, 'r') as f:
                    return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass
        return None
        
    def _save_cookies(self, cookies):
        os.makedirs(os.path.dirname(self.cookies_file), exist_ok=True)
        with open(self.cookies_file, 'w') as f:
            json.dump(cookies, f)

    def _update_cookie_jar(self, cookie_jar, cookies_dict):
        if cookies_dict:
            for name, cookie in cookies_dict.items():
                cookie_jar.update_cookies({name: cookie})

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
                f"{self.base_url}/panel/api/inbounds/addClient",
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
                f"{self.base_url}/panel/api/inbounds/updateClient/{uuid}",
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
                f"{self.base_url}/panel/api/inbounds/delClient/{uuid}",
                headers=headers,
                ssl=self.ssl_context
            ) as response:
                return response.status == 200 

    async def create_config(self, nickname: str, user_uuid: str) -> bool:
        cookie_jar = aiohttp.CookieJar(unsafe=True)
        saved_cookies = await self.load_cookies()
        if saved_cookies:
            self._update_cookie_jar(cookie_jar, saved_cookies)
            print("🔹 Загружены сохраненные куки.")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        async with aiohttp.ClientSession(cookie_jar=cookie_jar) as session:
            need_auth = not saved_cookies
            if need_auth:
                login_url = f"{self.base_url}/login"
                login_data = {"username": self.username, "password": self.password}
                print("\n🔹 Отправляем запрос на авторизацию...")
                async with session.post(login_url, json=login_data, headers=headers, ssl=self.ssl_context) as response:
                    login_response_text = await response.text()
                    print("🔹 Статус-код авторизации:", response.status)
                    print("🔹 Ответ сервера:", login_response_text)
                    if response.status != 200:
                        raise Exception("❌ Ошибка авторизации!")
                cookies = session.cookie_jar.filter_cookies(URL(self.base_url))
                cookies_dict = {key: morsel.value for key, morsel in cookies.items()}
                await self._save_cookies(cookies_dict)
                print("🔹 Куки сохранены.")
            else:
                print("🔹 Используем сохраненные куки для авторизации.")

            user_flow = "xtls-rprx-vision"

            # Добавляем клиента
            client_data = {
                "id": int(self.inbound_id),
                "settings": json.dumps({
                    "clients": [{
                        "id": user_uuid,
                        "flow": user_flow,
                        "email": nickname,
                        "limitIp": 3,
                        "totalGB": 2 * 1024 * 1024 * 1024,
                        "expiryTime": 0,
                        "enable": True,
                        "tgId": "",
                        "subId": "test-sub-id",
                        "reset": 0
                    }]
                })
            }

            add_client_url = f"{self.base_url}/panel/api/inbounds/addClient"
            async with session.post(add_client_url, headers=headers, json=client_data, ssl=self.ssl_context) as response:
                client_response_text = await response.text()
                print("\n🔹 Статус-код при добавлении:", response.status)
                print("🔹 Ответ сервера:", client_response_text)
                if response.status != 200:
                    raise Exception(f"Ошибка при создании клиента: {client_response_text}")
                print(f"✅ Пользователь {nickname} ({user_uuid}) успешно добавлен!")

            # Обновляем клиента
            update_data = {
                "id": int(self.inbound_id),
                "settings": json.dumps({
                    "clients": [{
                        "id": user_uuid,
                        "flow": user_flow,
                        "email": nickname,
                        "limitIp": 3,
                        "totalGB": 2 * 1024 * 1024 * 1024,
                        "expiryTime": 0,
                        "enable": True,
                        "tgId": "",
                        "subId": "updated-sub-id",
                        "reset": 0
                    }]
                })
            }

            update_client_url = f"{self.base_url}/panel/api/inbounds/updateClient/{user_uuid}"
            async with session.post(update_client_url, json=update_data, headers=headers, ssl=self.ssl_context) as response:
                update_response_text = await response.text()
                print("🔹 Статус-код обновления:", response.status)
                print("🔹 Ответ сервера:", update_response_text)
                if response.status != 200:
                    raise Exception(f"Ошибка при обновлении клиента: {update_response_text}")
                print(f"✅ Пользователь {nickname} ({user_uuid}) успешно обновлен!")
            
            return True

    async def update_limits(self, uuid: str, gb_limit: int, ip_limit: int) -> bool:
        # Метод для обновления лимитов после оплаты
        async with aiohttp.ClientSession(cookies=self.cookies) as session:
            await self._ensure_auth(session)
            # Код обновления лимитов... 

    async def load_cookies(self):
        if os.path.exists(self.cookies_file):
            with open(self.cookies_file, "r") as f:
                return json.load(f)
        return {}

    async def save_cookies(self, cookies):
        os.makedirs(os.path.dirname(self.cookies_file), exist_ok=True)
        with open(self.cookies_file, "w") as f:
            json.dump(cookies, f) 