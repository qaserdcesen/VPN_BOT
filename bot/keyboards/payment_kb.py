from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_payment_keyboard(payment_id: str, payment_url: str, is_test: bool = False):
    """Создает клавиатуру для оплаты"""
    
    keyboard = [
        [InlineKeyboardButton(text="💳 Оплатить", url=payment_url)]
    ]
    
    # Для тестовых платежей добавляем кнопку тестовой оплаты
    if is_test:
        keyboard.append([
            InlineKeyboardButton(text="✅ Тестовая оплата (успех)", callback_data=f"test_success_{payment_id}")
        ])
        keyboard.append([
            InlineKeyboardButton(text="❌ Отменить платеж", callback_data=f"cancel_payment_{payment_id}")
        ])
    else:
        # Для YooKassa добавляем кнопку успешной оплаты для тестирования в тестовом режиме
        keyboard.append([
            InlineKeyboardButton(text="✅ YooKassa: Платеж успешен", callback_data=f"yookassa_success_{payment_id}")
        ])
        keyboard.append([
            InlineKeyboardButton(text="❌ Отменить платеж", callback_data=f"cancel_payment_{payment_id}")
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard) 