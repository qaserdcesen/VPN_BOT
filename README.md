# ftwVPN

Лёгкий Telegram-бот для автоматической выдачи VPN-ссылок (VLESS), оплаты подписки и управления промокодами.

## Основные возможности

- Получение одноразовой VLESS-ссылки  
- Оплата подписки прямо в чате  
- Генерация и применение промокодов  
- Админ-панель для управления тарифами и акциями
- Статистика использования

## Зависимости

Все внешние библиотеки перечислены в `requirements.txt`:
aiogram>=3.0.0
python-dotenv
sqlalchemy>=2.0.0
aiosqlite
yookassa


# Установка и запуск

1. Клонировать репозиторий:
   ```bash
   git clone https://github.com/yourusername/ftwVPN.git
   cd ftwVPN

Создать и активировать виртуальное окружение:

## Для Linux/macOS:

python3 -m venv venv
```source venv/bin/activate```

## Для Windows:

python -m venv venv
```.\venv\Scripts\activate```

## Установить зависимости:

```pip install -r requirements.txt```

## Скопировать .env.example в .env и заполнить его:

```BOT_TOKEN=ваш_токен_бота
BOT_TOKEN=...
DATABASE_URL=...
API_BASE_URL=...
INBOUND_ID=...
API_USERNAME=...
API_PASSWORD=...
YOOKASSA_SHOP_ID=...
YOOKASSA_SECRET_KEY=...
PAYMENT_RETURN_URL=...
TEST_MODE=...
```
Запустить приложение:

```python run_bot.py```
