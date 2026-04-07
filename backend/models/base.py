"""
数据库基类和会话管理
"""
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from config.settings import settings

# 创建数据库引擎
engine = create_engine(
    settings.database_url,
    connect_args=(
        {"check_same_thread": False, "timeout": 30}
        if "sqlite" in settings.database_url
        else {}
    ),
    echo=settings.debug,
)


# SQLite 多线程并发优化：开启 WAL 模式 + busy_timeout，避免 "database is locked"
if "sqlite" in settings.database_url:
    @event.listens_for(engine, "connect")
    def _sqlite_pragma_on_connect(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            # WAL：允许多读单写并发，写者排队不直接报错
            cursor.execute("PRAGMA journal_mode=WAL")
            # 写锁等待 10 秒后再放弃，缓解高并发瞬时锁冲突
            cursor.execute("PRAGMA busy_timeout=10000")
            # 牺牲极端断电安全换取写入吞吐
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基类
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话
    用于 FastAPI 依赖注入
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    初始化数据库
    创建所有表
    """
    Base.metadata.create_all(bind=engine)
