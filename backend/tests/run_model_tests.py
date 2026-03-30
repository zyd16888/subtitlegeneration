"""
简单的测试运行脚本
用于验证数据库模型测试
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 运行 pytest
import pytest

if __name__ == "__main__":
    # 运行 test_models.py 测试
    exit_code = pytest.main([
        "backend/tests/test_models.py",
        "-v",
        "--tb=short"
    ])
    sys.exit(exit_code)
