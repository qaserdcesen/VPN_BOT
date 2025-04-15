from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Константы для тарифов
TARIFFS = {
    "base": {
        "name": "ftw.base",
        "price": 69,
        "traffic": "25ГБ/месяц",
        "ips": "3IP",
        "callback_data": "tariff_base"
    },
    "middle": {
        "name": "ftw.middle",
        "price": 149,
        "traffic": "Безлимит",
        "ips": "3IP",
        "callback_data": "tariff_middle"
    },
    "unlimited": {
        "name": "ftw.unlimited",
        "price": 199,
        "traffic": "Безлимит",
        "ips": "6IP",
        "callback_data": "tariff_unlimited"
    }
}

def get_tariffs_info() -> str:
    """Формирует текстовое описание всех тарифов"""
    info = "Подписка и оплата\n\n"
    info += "Всего есть 3 тарифа:\n"
    
    for tariff in TARIFFS.values():
        info += f"• {tariff['name']} -- {tariff['price']}₽/месяц -- {tariff['traffic']} и {tariff['ips']}\n"
    
    info += "\nВыбери какой тариф хочешь ты"
    
    return info

def get_tariffs_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопками выбора тарифа"""
    keyboard = []
    
    for tariff in TARIFFS.values():
        keyboard.append([
            InlineKeyboardButton(
                text=f"{tariff['name']} -- {tariff['price']} РУБ",
                callback_data=tariff["callback_data"]
            )
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_payment_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопками выбора способа оплаты"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="С моего бонусного баланса",
                    callback_data="pay_bonus"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Банковская карта/СБП/SbaerPay",
                    callback_data="pay_card"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Назад",
                    callback_data="back_to_tariffs"
                )
            ]
        ]
    ) 