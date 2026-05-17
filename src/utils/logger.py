"""
日志工具模块
"""
import logging
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime


_loggers = {}


def setup_logger(
    name: str,
    level: str = "INFO",
    log_file: Optional[str] = None,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    设置日志记录器

    Args:
        name: 日志记录器名称
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径 (可选)
        format_string: 日志格式 (可选)

    Returns:
        logging.Logger: 配置好的日志记录器
    """
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # 清除已有的处理器
    logger.handlers.clear()

    # 日志格式
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    formatter = logging.Formatter(format_string)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _loggers[name] = logger
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    获取日志记录器
    如果不存在则创建一个默认配置

    Args:
        name: 日志记录器名称

    Returns:
        logging.Logger: 日志记录器
    """
    if name not in _loggers:
        return setup_logger(name)
    return _loggers[name]


class LoggerMixin:
    """
    日志混入类
    为类提供日志功能
    """

    @property
    def logger(self) -> logging.Logger:
        """获取当前类的日志记录器"""
        name = f"{self.__class__.__module__}.{self.__class__.__name__}"
        return get_logger(name)
