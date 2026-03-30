"""
日志系统测试

测试日志配置、输出和轮转功能
"""
import pytest
import logging
import tempfile
import shutil
from pathlib import Path
from backend.utils.logger import setup_logger, get_logger, Logger


class TestLogger:
    """日志系统测试类"""
    
    def setup_method(self):
        """每个测试前的设置"""
        # 创建临时目录用于测试日志文件
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = str(Path(self.temp_dir) / "test.log")
        
        # 重置日志管理器
        Logger._instance = None
        Logger._initialized = False
    
    def teardown_method(self):
        """每个测试后的清理"""
        # 清理临时目录
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)
    
    def test_setup_logger_creates_logger(self):
        """测试创建日志记录器"""
        logger = setup_logger(
            name="test_logger",
            log_level="INFO",
            log_file=self.log_file
        )
        
        assert logger is not None
        assert logger.name == "test_logger"
        assert logger.level == logging.INFO
    
    def test_logger_writes_to_file(self):
        """测试日志写入文件"""
        logger = setup_logger(
            name="test_logger",
            log_level="INFO",
            log_file=self.log_file,
            log_to_console=False
        )
        
        # 写入日志
        test_message = "Test log message"
        logger.info(test_message)
        
        # 强制刷新处理器
        for handler in logger.handlers:
            handler.flush()
        
        # 验证文件存在且包含日志内容
        assert Path(self.log_file).exists()
        
        with open(self.log_file, 'r', encoding='utf-8') as f:
            content = f.read()
            assert test_message in content
    
    def test_logger_respects_log_level(self):
        """测试日志级别过滤"""
        logger = setup_logger(
            name="test_logger",
            log_level="WARNING",
            log_file=self.log_file,
            log_to_console=False
        )
        
        # 写入不同级别的日志
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        
        # 强制刷新
        for handler in logger.handlers:
            handler.flush()
        
        # 读取日志文件
        with open(self.log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 验证只有 WARNING 及以上级别的日志被记录
        assert "Debug message" not in content
        assert "Info message" not in content
        assert "Warning message" in content
        assert "Error message" in content
    
    def test_get_logger_returns_same_instance(self):
        """测试获取相同的日志记录器实例"""
        logger1 = setup_logger(
            name="test_logger",
            log_file=self.log_file
        )
        logger2 = get_logger("test_logger")
        
        assert logger1 is logger2
    
    def test_logger_singleton_pattern(self):
        """测试日志管理器单例模式"""
        manager1 = Logger()
        manager2 = Logger()
        
        assert manager1 is manager2
    
    def test_logger_creates_log_directory(self):
        """测试自动创建日志目录"""
        nested_log_file = str(Path(self.temp_dir) / "nested" / "dir" / "test.log")
        
        logger = setup_logger(
            name="test_logger",
            log_file=nested_log_file,
            log_to_console=False
        )
        
        logger.info("Test message")
        
        # 强制刷新
        for handler in logger.handlers:
            handler.flush()
        
        # 验证目录和文件都被创建
        assert Path(nested_log_file).parent.exists()
        assert Path(nested_log_file).exists()
    
    def test_logger_format_includes_timestamp(self):
        """测试日志格式包含时间戳"""
        logger = setup_logger(
            name="test_logger",
            log_file=self.log_file,
            log_to_console=False
        )
        
        logger.info("Test message")
        
        # 强制刷新
        for handler in logger.handlers:
            handler.flush()
        
        with open(self.log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 验证日志格式包含时间戳、名称、级别和消息
        assert "test_logger" in content
        assert "INFO" in content
        assert "Test message" in content
        # 简单验证时间戳格式 (YYYY-MM-DD)
        import re
        assert re.search(r'\d{4}-\d{2}-\d{2}', content)
    
    def test_multiple_loggers_independent(self):
        """测试多个日志记录器相互独立"""
        log_file1 = str(Path(self.temp_dir) / "test1.log")
        log_file2 = str(Path(self.temp_dir) / "test2.log")
        
        logger1 = setup_logger(
            name="logger1",
            log_file=log_file1,
            log_to_console=False
        )
        logger2 = setup_logger(
            name="logger2",
            log_file=log_file2,
            log_to_console=False
        )
        
        logger1.info("Message from logger1")
        logger2.info("Message from logger2")
        
        # 强制刷新
        for handler in logger1.handlers:
            handler.flush()
        for handler in logger2.handlers:
            handler.flush()
        
        # 验证日志分别写入不同文件
        with open(log_file1, 'r', encoding='utf-8') as f:
            content1 = f.read()
        with open(log_file2, 'r', encoding='utf-8') as f:
            content2 = f.read()
        
        assert "Message from logger1" in content1
        assert "Message from logger2" not in content1
        assert "Message from logger2" in content2
        assert "Message from logger1" not in content2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
