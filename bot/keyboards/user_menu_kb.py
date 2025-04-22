from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_user_menu_keyboard() -> ReplyKeyboardMarkup:
    """Возвращает клавиатуру меню пользователя с кнопками внизу экрана"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Мой профиль")],
            [KeyboardButton(text="💼 Подписка и оплата")],
            [KeyboardButton(text="🎁 Бонусы")],
            [KeyboardButton(text="ℹ️ Инфо")]
        ],
        resize_keyboard=True,  # Уменьшаем размер кнопок
        is_persistent=True,    # Делаем меню постоянным
        input_field_placeholder="Выберите действие в ftw.VPN..."
    ) 