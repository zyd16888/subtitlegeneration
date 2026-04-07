-- 添加 Telegram 用户追踪字段到 tasks 表
-- 迁移日期: 2026-04-07

-- 添加用户追踪字段
ALTER TABLE tasks ADD COLUMN telegram_user_id BIGINT;
ALTER TABLE tasks ADD COLUMN telegram_username VARCHAR;
ALTER TABLE tasks ADD COLUMN telegram_display_name VARCHAR;
ALTER TABLE tasks ADD COLUMN emby_username VARCHAR;

-- 为 telegram_user_id 创建索引以提高查询性能
CREATE INDEX IF NOT EXISTS idx_tasks_telegram_user_id ON tasks(telegram_user_id);

-- 注释说明
COMMENT ON COLUMN tasks.telegram_user_id IS '提交任务的 Telegram 用户 ID';
COMMENT ON COLUMN tasks.telegram_username IS 'Telegram 用户名';
COMMENT ON COLUMN tasks.telegram_display_name IS 'Telegram 显示名称';
COMMENT ON COLUMN tasks.emby_username IS '关联的 Emby 用户名';
