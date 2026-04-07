"""
数据库迁移脚本：添加 Telegram 用户追踪字段

运行方式：
    python -m migrations.migrate_add_telegram_tracking
"""
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from models.base import engine, SessionLocal


def migrate():
    """执行迁移"""
    print("开始迁移：添加 Telegram 用户追踪字段...")
    
    db = SessionLocal()
    try:
        # 检查字段是否已存在
        result = db.execute(text(
            "SELECT COUNT(*) FROM pragma_table_info('tasks') WHERE name='telegram_user_id'"
        ))
        exists = result.scalar() > 0
        
        if exists:
            print("✓ 字段已存在，跳过迁移")
            return
        
        # 添加字段
        print("添加 telegram_user_id 字段...")
        db.execute(text("ALTER TABLE tasks ADD COLUMN telegram_user_id BIGINT"))
        
        print("添加 telegram_username 字段...")
        db.execute(text("ALTER TABLE tasks ADD COLUMN telegram_username VARCHAR"))
        
        print("添加 telegram_display_name 字段...")
        db.execute(text("ALTER TABLE tasks ADD COLUMN telegram_display_name VARCHAR"))
        
        print("添加 emby_username 字段...")
        db.execute(text("ALTER TABLE tasks ADD COLUMN emby_username VARCHAR"))
        
        # 创建索引
        print("创建索引...")
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_tasks_telegram_user_id ON tasks(telegram_user_id)"
        ))
        
        db.commit()
        print("✓ 迁移完成！")
        
    except Exception as e:
        db.rollback()
        print(f"✗ 迁移失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
