"""
全局错误处理测试

测试 FastAPI 全局异常处理器和请求日志中间件
"""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
import logging
from backend.main import app


class TestErrorHandling:
    """错误处理测试类"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.client = TestClient(app)
    
    def test_http_exception_handler(self):
        """测试 HTTP 异常处理"""
        # 访问不存在的端点
        response = self.client.get("/api/nonexistent")
        
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["status_code"] == 404
        assert "path" in data
    
    def test_validation_error_handler(self):
        """测试请求验证错误处理"""
        # 发送无效的请求体到创建任务端点
        response = self.client.post(
            "/api/tasks",
            json={"invalid_field": "value"}
        )
        
        # 验证返回 422 状态码
        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["status_code"] == 422
        assert "message" in data
    
    def test_request_logging_middleware(self):
        """测试请求日志中间件"""
        # 发送请求
        response = self.client.get("/")
        
        # 验证响应包含处理时间头
        assert "X-Process-Time" in response.headers
        assert response.status_code == 200
    
    def test_health_check_endpoint(self):
        """测试健康检查端点"""
        response = self.client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    def test_root_endpoint(self):
        """测试根端点"""
        response = self.client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestErrorResponseFormat:
    """错误响应格式测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.client = TestClient(app)
    
    def test_error_response_has_standard_format(self):
        """测试错误响应具有标准格式"""
        response = self.client.get("/api/nonexistent")
        
        data = response.json()
        
        # 验证标准字段存在
        assert "error" in data
        assert "status_code" in data
        assert "message" in data
        assert "path" in data
        
        # 验证字段类型
        assert isinstance(data["error"], str)
        assert isinstance(data["status_code"], int)
        assert isinstance(data["message"], str)
        assert isinstance(data["path"], str)
    
    def test_validation_error_includes_details(self):
        """测试验证错误包含详细信息"""
        response = self.client.post(
            "/api/tasks",
            json={"invalid": "data"}
        )
        
        assert response.status_code == 422
        data = response.json()
        
        # 验证包含详细错误信息
        assert "details" in data
        assert isinstance(data["details"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
