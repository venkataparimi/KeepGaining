import sys
from loguru import logger
from app.core.config import settings

def setup_logging():
    logger.remove()
    
    # Console Handler
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True,
    )
    
    # File Handler (JSON for structured logging)
    logger.add(
        "logs/app.json",
        rotation="500 MB",
        retention="10 days",
        compression="zip",
        serialize=True,
        level="INFO",
    )
    
    # Error File Handler
    logger.add(
        "logs/error.log",
        rotation="100 MB",
        retention="30 days",
        level="ERROR",
        backtrace=True,
        diagnose=True,
    )

    logger.info("Logging initialized")
