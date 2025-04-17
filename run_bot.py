#!/usr/bin/env python
import sys
import os
import logging
import asyncio

# Настройка путей для корректных импортов
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Добавление пути к пакетам виртуального окружения
venv_path = os.environ.get('VIRTUAL_ENV')
if venv_path:
    site_packages = os.path.join(venv_path, 'lib', 'python3.13', 'site-packages')
    sys.path.insert(0, site_packages)
    print(f"Добавлен путь к пакетам: {site_packages}")
else:
    print("Виртуальное окружение не активировано! Используйте: source .venv/bin/activate")

# Подготовка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
)

try:
    # Импорт модулей бота
    from bot.bot import main
    
    # Запуск бота
    if __name__ == "__main__":
        print("Запуск бота...")
        asyncio.run(main())
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Проверьте, что все зависимости установлены. Выполните: pip install -r requirements.txt")
except Exception as e:
    print(f"Ошибка при запуске: {e}") 