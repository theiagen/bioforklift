import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logger(
    name: str,
    log_file: str | Path = "bioforklift.log",
    file_mode: str = "a",
    level: int = logging.INFO,
    max_bytes: int = 5_242_880,  # 5MB
    backup_count: int = 3,
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s",
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)

    formatter = logging.Formatter(log_format)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
