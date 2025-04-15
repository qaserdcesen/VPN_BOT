import json
import aiohttp
import os
from bot.config import API_BASE_URL, INBOUND_ID, API_USERNAME, API_PASSWORD, COOKIES_FILE
from yarl import URL

class VPNService:
    def __init__(self):
        self.base_url = API_BASE_URL.rstrip('/')
        self.username = API_USERNAME
        self.password = API_PASSWORD
        self.inbound_id = int(INBOUND_ID)
        self.cookies_file = COOKIES_FILE
        
        # Создаем директорию для cookies если её нет
        os.makedirs(os.path.dirname(self.cookies_file), exist_ok=True)
        
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

    # Только один метод для создания VPN
    async def create_config(self, nickname: str, user_uuid: str) -> bool:
        """Создает конфигурацию VPN на сервере"""
        cookie_jar = aiohttp.CookieJar(unsafe=True)
        saved_cookies = self._load_cookies()
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
                async with session.post(login_url, json=login_data, headers=headers) as response:
                    login_response_text = await response.text()
                    print("🔹 Статус-код авторизации:", response.status)
                    print("🔹 Ответ сервера:", login_response_text)
                    if response.status != 200:
                        raise Exception("❌ Ошибка авторизации!")
                cookies = session.cookie_jar.filter_cookies(URL(self.base_url))
                cookies_dict = {key: morsel.value for key, morsel in cookies.items()}
                self._save_cookies(cookies_dict)
                print("🔹 Куки сохранены.")
            else:
                print("🔹 Используем сохраненные куки для авторизации.")

            # Добавляем клиента
            client_data = {
                "id": int(self.inbound_id),
                "settings": json.dumps({
                    "clients": [{
                        "id": user_uuid,
                        "flow": "xtls-rprx-vision",
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
            async with session.post(add_client_url, headers=headers, json=client_data) as response:
                client_response_text = await response.text()
                print("\n🔹 Статус-код при добавлении:", response.status)
                print("🔹 Ответ сервера:", client_response_text)
                if response.status != 200:
                    raise Exception(f"Ошибка при создании клиента: {client_response_text}")
                print(f"✅ Пользователь {nickname} ({user_uuid}) успешно добавлен!")
            
            return True 