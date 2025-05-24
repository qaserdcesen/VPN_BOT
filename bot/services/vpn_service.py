import json
import aiohttp
import os
from bot.config import API_BASE_URL, INBOUND_ID, API_USERNAME, API_PASSWORD, COOKIES_FILE
from yarl import URL
import logging

# Настройка логирования
logger = logging.getLogger(__name__)

class VPNSettings:
    def __init__(self, 
                 host="qaserdcesen.minecraftnoob.com",
                 port=443,
                 type="tcp",
                 security="reality",
                 pbk="LtGGe_WR1PR3JdlvdEcURLVimtOl9_EERwt_kPT8mRk",
                 fp="chrome",
                 sni="google.com",
                 sid="9c15e6373b6177e9",
                 spx="/",
                 flow="xtls-rprx-vision"):
        self.host = host
        self.port = port
        self.type = type
        self.security = security
        self.pbk = pbk
        self.fp = fp
        self.sni = sni
        self.sid = sid
        self.spx = spx
        self.flow = flow

class VPNService:
    def __init__(self):
        self.base_url = API_BASE_URL.rstrip('/')
        self.username = API_USERNAME
        self.password = API_PASSWORD
        self.inbound_id = int(INBOUND_ID)
        self.cookies_file = COOKIES_FILE
        
        # Создаем директорию для cookies если её нет
        os.makedirs(os.path.dirname(self.cookies_file), exist_ok=True)
        
        # Настройки для генерации URL
        self.vpn_settings = VPNSettings()
        
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

    def generate_vpn_url(self, user_uuid, nickname):
        """Генерирует URL для VPN-клиента"""
        # URL-encode для специальных символов в spx
        spx_encoded = self.vpn_settings.spx.replace("/", "%2F")
        
        # Формируем URL
        url = (
            f"vless://{user_uuid}@{self.vpn_settings.host}:{self.vpn_settings.port}"
            f"?type={self.vpn_settings.type}"
            f"&security={self.vpn_settings.security}"
            f"&pbk={self.vpn_settings.pbk}"
            f"&fp={self.vpn_settings.fp}"
            f"&sni={self.vpn_settings.sni}"
            f"&sid={self.vpn_settings.sid}"
            f"&spx={spx_encoded}"
            f"&flow={self.vpn_settings.flow}"
            f"#{nickname}"
        )
        
        return url
    
    def update_vpn_settings(self, settings):
        """Обновляет настройки VPN"""
        self.vpn_settings = settings

    # Только один метод для создания VPN
    async def create_config(self, nickname: str, user_uuid: str, traffic_limit=None, limit_ip=3) -> tuple[bool, str]:
        """Создает конфигурацию VPN на сервере и возвращает URL
        
        Args:
            nickname: Имя пользователя для VPN
            user_uuid: UUID клиента
            traffic_limit: Лимит трафика в байтах (0 для безлимита)
            limit_ip: Максимальное количество одновременных подключений
            
        Returns:
            tuple: (success, vpn_url)
        """
        cookie_jar = aiohttp.CookieJar(unsafe=True)
        saved_cookies = self._load_cookies()
        if saved_cookies:
            self._update_cookie_jar(cookie_jar, saved_cookies)
            print("🔹 Загружены сохраненные куки.")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Если трафик не указан, используем 2GB по умолчанию
        if traffic_limit is None:
            traffic_limit = 2 * 1024 * 1024 * 1024

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
                        "limitIp": limit_ip,
                        "totalGB": traffic_limit,
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
            
            # После успешного создания клиента генерируем URL
            vpn_url = self.generate_vpn_url(user_uuid, nickname)
            return True, vpn_url
    
    async def update_client_on_server(self, user_uuid: str, nickname: str, traffic_limit: int, 
                                     limit_ip: int, expiry_time: int = 0) -> bool:
        """
        Обновляет параметры клиента на VPN сервере
        
        Args:
            user_uuid: UUID клиента
            nickname: Имя пользователя
            traffic_limit: Лимит трафика в байтах (0 для безлимита)
            limit_ip: Максимальное количество одновременных подключений
            expiry_time: Время истечения в миллисекундах (0 - бессрочно)
            
        Returns:
            bool: True если успешно обновлено
        """
        try:
            cookie_jar = aiohttp.CookieJar(unsafe=True)
            saved_cookies = self._load_cookies()
            if saved_cookies:
                self._update_cookie_jar(cookie_jar, saved_cookies)
                logger.info("Загружены сохраненные куки для обновления клиента.")

            headers = {"Accept": "application/json"}

            async with aiohttp.ClientSession(cookie_jar=cookie_jar) as session:
                # Проверка необходимости авторизации
                need_auth = not saved_cookies
                if need_auth:
                    login_url = f"{self.base_url}/login"
                    login_data = {"username": self.username, "password": self.password}
                    logger.info("Отправляем запрос на авторизацию для обновления клиента...")
                    async with session.post(login_url, json=login_data, headers=headers) as response:
                        login_response_text = await response.text()
                        logger.info(f"Статус-код авторизации: {response.status}")
                        logger.debug(f"Ответ сервера: {login_response_text}")
                        if response.status != 200:
                            raise Exception("Ошибка авторизации!")
                    cookies = session.cookie_jar.filter_cookies(URL(self.base_url))
                    cookies_dict = {key: morsel.value for key, morsel in cookies.items()}
                    self._save_cookies(cookies_dict)
                    logger.info("Куки сохранены.")
                else:
                    logger.info("Используем сохраненные куки для авторизации.")

                # Обновляем клиента
                client_data = {
                    "id": int(self.inbound_id),
                    "settings": json.dumps({
                        "clients": [{
                            "id": user_uuid,
                            "flow": "xtls-rprx-vision",
                            "email": nickname,
                            "limitIp": limit_ip,
                            "totalGB": traffic_limit,
                            "expiryTime": expiry_time,
                            "enable": True,
                            "tgId": "",
                            "subId": "test-sub-id",
                            "reset": 0
                        }]
                    })
                }

                update_client_url = f"{self.base_url}/panel/api/inbounds/updateClient/{user_uuid}"
                logger.info(f"Отправляем запрос на обновление клиента {nickname} ({user_uuid})")
                logger.info(f"Данные для обновления: {client_data}")
                logger.info(f"URL запроса: {update_client_url}")
                
                async with session.post(update_client_url, headers=headers, json=client_data) as response:
                    client_response_text = await response.text()
                    logger.info(f"Статус-код при обновлении: {response.status}")
                    logger.info(f"Ответ сервера: {client_response_text}")
                    
                    if response.status != 200:
                        logger.error(f"Ошибка при обновлении клиента: {client_response_text}")
                        raise Exception(f"Ошибка при обновлении клиента: {client_response_text}")
                    
                    logger.info(f"Клиент {nickname} ({user_uuid}) успешно обновлен!")
                    return True
                    
        except Exception as e:
            logger.error(f"Ошибка при обновлении клиента {user_uuid}: {e}")
            return False 