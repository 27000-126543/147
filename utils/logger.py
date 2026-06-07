import os
import sys
from loguru import logger
from config import settings


def setup_logger(name: str = "marketing_attribution") -> logger:
    log_file = os.path.join(settings.LOG_DIR, f"{name}.log")
    
    config = {
        "handlers": [
            {
                "sink": sys.stdout,
                "format": "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
                "level": "INFO",
                "enqueue": True,
            },
            {
                "sink": log_file,
                "format": "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
                "level": "DEBUG",
                "rotation": "100 MB",
                "retention": f"{settings.LOG_RETENTION_DAYS} days",
                "compression": "zip",
                "enqueue": True,
            }
        ]
    }
    
    logger.configure(**config)
    return logger


def get_logger(name: str = None) -> logger:
    if name:
        return logger.bind(module=name)
    return logger
