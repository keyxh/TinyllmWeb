import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random
from datetime import datetime, timedelta
from typing import Optional, Dict
import threading

from tinlyllmWeb.backend.config import settings


class EmailService:
    _verification_codes: Dict[str, dict] = {}
    _lock = threading.Lock()
    
    @staticmethod
    def generate_verification_code() -> str:
        return ''.join([str(random.randint(0, 9)) for _ in range(6)])
    
    @staticmethod
    def save_verification_code(email: str, code: str, expires_at: datetime):
        with EmailService._lock:
            EmailService._verification_codes[email] = {
                'code': code,
                'expires_at': expires_at
            }
    
    @staticmethod
    def get_and_verify_code(email: str, code: str) -> bool:
        with EmailService._lock:
            if email not in EmailService._verification_codes:
                return False
            
            stored = EmailService._verification_codes[email]
            
            if datetime.utcnow() > stored['expires_at']:
                del EmailService._verification_codes[email]
                return False
            
            if stored['code'] != code:
                return False
            
            del EmailService._verification_codes[email]
            return True
    
    @staticmethod
    def cleanup_expired_codes():
        with EmailService._lock:
            now = datetime.utcnow()
            expired_emails = [
                email for email, data in EmailService._verification_codes.items()
                if now > data['expires_at']
            ]
            for email in expired_emails:
                del EmailService._verification_codes[email]
    
    @staticmethod
    def send_verification_code(email: str, code: str) -> bool:
        try:
            msg = MIMEMultipart()
            msg['From'] = settings.EMAIL_SENDER
            msg['To'] = email
            msg['Subject'] = 'TinyLLM 验证码'
            
            body = f'''
            <html>
            <body>
                <h2>TinyLLM 验证码</h2>
                <p>您的验证码是：<strong style="font-size: 24px; color: #667eea;">{code}</strong></p>
                <p>验证码有效期为 {settings.VERIFICATION_CODE_EXPIRE_MINUTES} 分钟，请尽快使用。</p>
                <p>如果这不是您的操作，请忽略此邮件。</p>
            </body>
            </html>
            '''
            
            msg.attach(MIMEText(body, 'html', 'utf-8'))
            
            with smtplib.SMTP_SSL(settings.EMAIL_SMTP_SERVER, settings.EMAIL_SMTP_PORT) as server:
                server.login(settings.EMAIL_SENDER, settings.EMAIL_PASSWORD)
                server.send_message(msg)
            
            return True
        except Exception as e:
            print(f"发送邮件失败: {e}")
            return False
    
    @staticmethod
    def get_verification_code_expires_at() -> datetime:
        return datetime.utcnow() + timedelta(minutes=settings.VERIFICATION_CODE_EXPIRE_MINUTES)
    
    @staticmethod
    def is_verification_code_valid(expires_at: Optional[datetime]) -> bool:
        if not expires_at:
            return False
        return datetime.utcnow() <= expires_at


email_service = EmailService()
