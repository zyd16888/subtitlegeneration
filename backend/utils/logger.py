"""
日志系统配置

提供统一的日志记录功能，支持：
- 控制台和文件输出
- 日志轮转（按日期，保留 30 天）
- 可配置的日志级别
- 结构化日志格式

Requirements: 13.1, 13.2, 13.3, 13.4, 13.5
"""
import logging
import sys
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from typing import Optional


class Logger:
    """日志管理器"""
    
    _instance: Optional['Logger'] = None
    _initialized: bool = False
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化日志系统"""
        if self._initialized:
            return
        
        self._initialized = True
        self.loggers = {}
    
    def setup_logger(
        self,
        name: str = "subtitle_service",
        log_level: str = "INFO",
        log_file: str = "logs/subtitle_service.log",
        log_to_console: bool = True,
        log_to_file: bool = True
    ) -> logging.Logger:
        """
        配置日志记录器
        
        Args:
            name: 日志记录器名称
            log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
            log_file: 日志文件路径
            log_to_console: 是否输出到控制台
            log_to_file: 是否输出到文件
            
        Returns:
            配置好的日志记录器
        """
        # 如果已经配置过，直接返回
        if name in self.loggers:
            return self.loggers[name]
        
        # 创建日志记录器
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, log_level.upper()))
        
        # 清除已有的处理器
        logger.handlers.clear()
        
        # 日志格式
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 控制台处理器
        if log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(getattr(logging, log_level.upper()))
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        # 文件处理器（带日志轮转）
        if log_to_file:
            # 确保日志目录存在
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 使用 TimedRotatingFileHandler 实现按日期轮转
            # when='midnight' 表示每天午夜轮转
            # interval=1 表示每 1 天轮转一次
            # backupCount=30 表示保留最近 30 天的日志
            file_handler = TimedRotatingFileHandler(
                filename=log_file,
                when='midnight',
                interval=1,
                backupCount=30,
                encoding='utf-8'
            )
            file_handler.setLevel(getattr(logging, log_level.upper()))
            file_handler.setFormatter(formatter)
            
            # 设置日志文件名后缀格式
            file_handler.suffix = "%Y-%m-%d"
            
            logger.addHandler(file_handler)
        
        # 缓存日志记录器
        self.loggers[name] = logger
        
        return logger
    
    def get_logger(self, name: str = "subtitle_service") -> logging.Logger:
        """
        获取日志记录器
        
        Args:
            name: 日志记录器名称
            
        Returns:
            日志记录器
        """
        if name not in self.loggers:
            # 如果没有配置过，使用默认配置
            return self.setup_logger(name)
        return self.loggers[name]


# 全局日志管理器实例
logger_manager = Logger()


def get_logger(name: str = "subtitle_service") -> logging.Logger:
    """
    获取日志记录器的便捷函数
    
    Args:
        name: 日志记录器名称
        
    Returns:
        日志记录器
    """
    return logger_manager.get_logger(name)


def setup_logger(
    name: str = "subtitle_service",
    log_level: str = "INFO",
    log_file: str = "logs/subtitle_service.log",
    log_to_console: bool = True,
    log_to_file: bool = True
) -> logging.Logger:
    """
    配置日志记录器的便捷函数
    
    Args:
        name: 日志记录器名称
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        log_file: 日志文件路径
        log_to_console: 是否输出到控制台
        log_to_file: 是否输出到文件
        
    Returns:
        配置好的日志记录器
    """
    return logger_manager.setup_logger(
        name=name,
        log_level=log_level,
        log_file=log_file,
        log_to_console=log_to_console,
        log_to_file=log_to_file
    )
