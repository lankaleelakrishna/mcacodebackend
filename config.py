import os

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(24).hex())
    DB_HOST = 'localhost'
    DB_PORT = 3306
    DB_USERNAME = 'root'
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'Dp@333666')
    DB_NAME = 'design'
    AUTH_TOKEN = os.getenv('AUTH_TOKEN', 'mysecrettoken')
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
    SUPPORTED_IMAGE_TYPES = {
        'image/jpeg': 'jpg',
        'image/png': 'png',
        'image/gif': 'gif',
        'image/bmp': 'bmp',
        'image/webp': 'webp'
    }
    # Email configuration
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'dpprasad468@gmail.com')
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_USER = os.getenv('SMTP_USER', 'dpprasad468@gmail.com')
    SMTP_PASS = os.getenv('SMTP_PASS', 'kfid rfrf iyxg fbam')