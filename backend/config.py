from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "TinyLLM Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    DATABASE_HOST: str = "127.0.0.1"
    DATABASE_PORT: int = 3306
    DATABASE_USER: str = "root"
    DATABASE_PASSWORD: str = "root"
    DATABASE_NAME: str = "tinyllm"
    
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    
    INITIAL_POINTS: float = 10.0
    CHECKIN_REWARD: float = 1.0
    
    TRAINING_COST_MIN: float = 30.0
    TRAINING_COST_MAX: float = 100.0
    
    DEPLOY_COST_PER_DAY_MIN: float = 2.0
    DEPLOY_COST_PER_DAY_MAX: float = 10.0
    DEPLOY_COST_PER_HOUR: float = 0.125
    
    BASE_MODEL_PATH: str = "./base_models"
    TRAINED_MODELS_PATH: str = "./trained_models"
    DATASETS_PATH: str = "./datasets"
    MAX_TRAINING_TASKS: int = 5
    
    CORS_ORIGINS: list = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        "http://38.150.4.149:39999",
        "http://38.150.4.149:*",
        "*"
    ]
    
    CUSTOMER_EMAIL: str = "2151335401@qq.com"
    
    EMAIL_SENDER: str = "2151335401@qq.com"
    EMAIL_PASSWORD: str = "tnjvtthbsllsdiib"
    EMAIL_SMTP_SERVER: str = "smtp.qq.com"
    EMAIL_SMTP_PORT: int = 465
    
    DEVICE_HEARTBEAT_INTERVAL: int = 30
    
    API_PORT_START: int = 8001
    API_PORT_END: int = 8999
    
    VERIFICATION_CODE_EXPIRE_MINUTES: int = 5
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
