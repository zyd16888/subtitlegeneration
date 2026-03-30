"""
Task 11 集成测试

测试日志系统和全局错误处理的集成
"""
import pytest
import tempfile
import shutil
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.utils.logger import setup_logger, get_logger


class TestTask11Integration:
    """Task 11 集成测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.client = TestClient(app)
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = str(Path(self.temp_dir) / "test_integration.log")
    
    def teardown_method(self):
        """每个测试后的清理"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)
    
    def test_logger_and_error_handler_integration(self):
        """测试日志系统和错误处理器集成"""
        # 配置测试日志
        logger = setup_logger(
            name="test_integration",
            log_level="INFO",
            log_file=self.log_file,
            log_to_console=False
        )
        
        # 写入测试日志
        logger.info("Integration test started")
        logger.error("Test error message")
        
        # 强制刷新
        for handler in logger.handlers:
            handler.flush()
        
        # 验证日志文件
        assert Path(self.log_file).exists()
        
        with open(self.log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert "Integration test started" in content
        assert "Test error message" in content
        assert "INFO" in content
        assert "ERROR" in content
    
    def test_api_request_logging(self):
        """测试 API 请求日志记录"""
        # 发送请求到健康检查端点
        response = self.client.get("/health")
        
        # 验证响应成功
        assert response.status_code == 200
        
        # 验证响应头包含处理时间
        assert "X-Process-Time" in response.headers
        process_time = float(response.headers["X-Process-Time"])
        assert process_time >= 0
    
    def test_error_response_format_with_logging(self):
        """测试错误响应格式和日志记录"""
        # 访问不存在的端点
        response = self.client.get("/api/nonexistent")
        
        # 验证错误响应格式
        assert response.status_code == 404
        data = response.json()
        
        assert "error" in data
        assert "status_code" in data
        assert "message" in data
        assert "path" in data
        
        assert data["status_code"] == 404
        assert data["path"] == "/api/nonexistent"
    
    def test_multiple_log_levels(self):
        """测试多个日志级别"""
        logger = setup_logger(
            name="test_levels",
            log_level="DEBUG",
            log_file=self.log_file,
            log_to_console=False
        )
        
        # 写入不同级别的日志
        logger.debug("Debug level message")
        logger.info("Info level message")
        logger.warning("Warning level message")
        logger.error("Error level message")
        
        # 强制刷新
        for handler in logger.handlers:
            handler.flush()
        
        # 验证所有级别都被记录
        with open(self.log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert "DEBUG" in content
        assert "INFO" in content
        assert "WARNING" in content
        assert "ERROR" in content
        assert "Debug level message" in content
        assert "Info level message" in content
        assert "Warning level message" in content
        assert "Error level message" in content


class TestLogRotation:
    """日志轮转测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = str(Path(self.temp_dir) / "rotation_test.log")
    
    def teardown_method(self):
        """每个测试后的清理"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)
    
    def test_log_rotation_configuration(self):
        """测试日志轮转配置"""
        logger = setup_logger(
            name="rotation_test",
            log_level="INFO",
            log_file=self.log_file,
            log_to_console=False
        )
        
        # 验证日志处理器配置
        file_handlers = [h for h in logger.handlers if hasattr(h, 'backupCount')]
        
        assert len(file_handlers) > 0
        
        # 验证轮转配置
        handler = file_handlers[0]
        assert handler.backupCount == 30  # 保留 30 天
        assert handler.when == 'midnight'  # 每天午夜轮转
        assert handler.interval == 1  # 每 1 天


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
