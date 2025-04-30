from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_instruction_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру с кнопками инструкций для разных устройств"""
    
    # Разные URL для разных платформ
    v2ray_url = "https://teletype.in/@vpn_linkbot/v2rayTun"
    hiddify_url = "https://teletype.in/@vpn_linkbot/hiddify"
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Android/iPhone/macOS", 
                    url=v2ray_url
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Windows/Linux", 
                    url=hiddify_url
                )
            ]
        ]
    ) 
