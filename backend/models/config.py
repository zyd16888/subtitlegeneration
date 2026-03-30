"""
系统配置数据模型
"""
from sqlalchemy import Column, String, Integer, Boolean, Text
from .base import Base


class SystemConfig(Base):
    """
    系统配置模型
    
    存储系统的所有配置参数，使用键值对形式
    """
    __tablename__ = "system_config"
    
    key = Column(String, primary_key=True, index=True, comment="配置键")
    value = Column(Text, nullable=True, comment="配置值")
    description = Column(String, nullable=True, comment="配置描述")
    
    def __repr__(self):
        return f"<SystemConfig(key={self.key}, value={self.value})>"
