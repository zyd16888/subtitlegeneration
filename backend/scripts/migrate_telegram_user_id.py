"""
P0 迁移脚本：把 Task.extra_info["telegram_user_id"] 回填到 Task.telegram_user_id 字段。

背景：早期 TG 任务把 telegram_user_id 同时写到 extra_info 和 telegram_user_id 字段，
后来发现部分查询走的是 extra_info 模糊匹配，存在双写风险。本脚本统一回填到字段，
之后查询全部使用字段。

运行方式（在 backend/ 目录下，激活 ame 环境后）：
    python -m scripts.migrate_telegram_user_id

幂等：可重复运行，只会处理 telegram_user_id IS NULL 但 extra_info 有该键的任务。
"""
import logging

from models.base import SessionLocal
from models.task import Task

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def migrate() -> tuple[int, int]:
    """
    回填 telegram_user_id 字段。

    Returns:
        (扫描数, 回填数)
    """
    db = SessionLocal()
    try:
        candidates = db.query(Task).filter(
            Task.telegram_user_id.is_(None),
            Task.extra_info.isnot(None),
        ).all()

        scanned = len(candidates)
        filled = 0

        for task in candidates:
            info = task.extra_info or {}
            tg_id = info.get("telegram_user_id")
            if tg_id is None:
                continue
            try:
                task.telegram_user_id = int(tg_id)
                filled += 1
            except (TypeError, ValueError):
                logger.warning(
                    "任务 %s extra_info.telegram_user_id 非整数: %r",
                    task.id, tg_id,
                )

        db.commit()
        return scanned, filled
    finally:
        db.close()


if __name__ == "__main__":
    scanned, filled = migrate()
    logger.info("扫描 %d 条候选任务，回填 %d 条 telegram_user_id", scanned, filled)
