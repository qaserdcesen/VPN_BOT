from fastapi import APIRouter, Request, Depends, HTTPException
import json
import hmac
import hashlib
import base64
import logging
from bot.services.payment_service import PaymentService
from bot.config import YOOKASSA_SECRET_KEY

router = APIRouter()
logger = logging.getLogger(__name__)

def verify_signature(request_body, signature):
    """
    Проверяет подпись уведомления от YooKassa
    
    Args:
        request_body: Тело запроса
        signature: Подпись из заголовка
        
    Returns:
        bool: True если подпись верна
    """
    if not YOOKASSA_SECRET_KEY:
        logger.warning("YOOKASSA_SECRET_KEY не настроен, пропускаем проверку подписи")
        return True
        
    try:
        secret_key = YOOKASSA_SECRET_KEY.encode('utf-8')
        digest = hmac.new(secret_key, request_body, hashlib.sha1).digest()
        signature_digest = base64.b64encode(digest).decode('utf-8')
        return signature_digest == signature
    except Exception as e:
        logger.error(f"Ошибка при проверке подписи: {e}")
        return False

@router.post("/yookassa/notification")
async def yookassa_notification(request: Request):
    """
    Обработчик уведомлений от YooKassa
    """
    try:
        # Получаем заголовок с подписью
        signature = request.headers.get("X-Request-Signature")
        if not signature:
            logger.warning("Отсутствует заголовок X-Request-Signature")
            raise HTTPException(status_code=400, detail="Missing signature")
        
        # Получаем тело запроса
        body = await request.body()
        
        # Проверяем подпись
        if not verify_signature(body, signature):
            logger.warning("Неверная подпись уведомления")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        # Разбираем JSON
        payment_data = json.loads(body.decode('utf-8'))
        
        # Логируем уведомление
        logger.info(f"Получено уведомление от YooKassa: {payment_data.get('event')}")
        
        # Обрабатываем уведомление
        result = await PaymentService.process_notification(payment_data)
        
        if result:
            return {"status": "success"}
        else:
            raise HTTPException(status_code=500, detail="Failed to process notification")
            
    except json.JSONDecodeError:
        logger.error("Ошибка декодирования JSON")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Ошибка при обработке уведомления: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") 