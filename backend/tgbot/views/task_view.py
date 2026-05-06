"""
任务列表 / 详情的统一视图渲染。

这里集中所有面向用户展示的文本和键盘构造逻辑，让 /tasks、/task_info、
通知消息共用同一套表达，避免散落不一致。

Callback 命名空间约定：
  tl:{filter}:{page}              列表翻页或过滤切换
  td:{task_short_id}              进入任务详情
  to:x:{task_short_id}            取消任务
  to:r:{task_short_id}            重试任务
  to:dl:{task_short_id}           下载主字幕（单语言）
  to:dl:{task_short_id}:{lang}    下载指定语言字幕（多语言）
  to:back:{filter}:{page}         从详情返回列表（保留过滤状态）
"""
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from models.task import Task, TaskStatus
from tgbot.services.error_hints import classify
from tgbot.utils import (
    format_duration,
    format_progress,
    format_task_status,
    format_time_ago,
    short_id,
)

# 列表过滤档位
FILTER_ALL = "all"
FILTER_ACTIVE = "active"      # PENDING + PROCESSING
FILTER_COMPLETED = "completed"
FILTER_FAILED = "failed"
PAGE_SIZE = 5

_FILTER_LABELS = {
    FILTER_ALL: "全部",
    FILTER_ACTIVE: "进行中",
    FILTER_COMPLETED: "已完成",
    FILTER_FAILED: "失败",
}


def filter_to_statuses(filter_kind: str) -> Optional[list[TaskStatus]]:
    """把过滤档位转换为状态集合。FILTER_ALL 返回 None 表示不过滤。"""
    if filter_kind == FILTER_ACTIVE:
        return [TaskStatus.PENDING, TaskStatus.PROCESSING]
    if filter_kind == FILTER_COMPLETED:
        return [TaskStatus.COMPLETED]
    if filter_kind == FILTER_FAILED:
        return [TaskStatus.FAILED]
    return None


def render_task_list(
    tasks: list[Task],
    total: int,
    filter_kind: str,
    page: int,
    daily_count: int,
    daily_limit: int,
) -> tuple[str, InlineKeyboardMarkup]:
    """渲染任务列表文本和键盘。"""
    label = _FILTER_LABELS.get(filter_kind, filter_kind)
    if not tasks:
        text = f"📋 我的任务（{label}）\n\n暂无记录。\n\n今日配额: {daily_count}/{daily_limit}"
        return text, _list_keyboard(filter_kind, page, has_prev=False, has_next=False)

    lines = [f"📋 我的任务（{label}） · 共 {total} 条\n"]
    start = page * PAGE_SIZE
    for i, task in enumerate(tasks, start=start + 1):
        status_str = format_task_status(_task_status_value(task))
        title = task.media_item_title or "未知"
        if len(title) > 25:
            title = title[:24] + "…"

        # 已完成任务在标题前加 🔍 标记来自外部搜索
        title_prefix = "🔍 " if (
            task.status == TaskStatus.COMPLETED and _is_external_subtitle(task)
        ) else ""

        extra = ""
        if task.status == TaskStatus.PROCESSING:
            extra = f" {format_progress(task.progress)}"
        elif task.status == TaskStatus.COMPLETED:
            extra = f" {format_time_ago(task.completed_at)}"
        elif task.status == TaskStatus.FAILED:
            stage = task.error_stage or ""
            extra = f" ({stage})" if stage else ""

        lines.append(f"{i}. {status_str} {title_prefix}{title}{extra}\n   🆔 {short_id(task.id)}")

    lines.append(f"\n今日配额: {daily_count}/{daily_limit}")
    text = "\n".join(lines)

    has_prev = page > 0
    has_next = (page + 1) * PAGE_SIZE < total
    keyboard = _list_keyboard(
        filter_kind, page,
        has_prev=has_prev, has_next=has_next,
        task_buttons=tasks,
    )
    return text, keyboard


def _list_keyboard(
    filter_kind: str,
    page: int,
    has_prev: bool,
    has_next: bool,
    task_buttons: Optional[list[Task]] = None,
) -> InlineKeyboardMarkup:
    """构建列表键盘：过滤切换 + 任务详情快捷 + 翻页。"""
    rows: list[list[InlineKeyboardButton]] = []

    # 过滤切换
    filter_row = []
    for kind in (FILTER_ALL, FILTER_ACTIVE, FILTER_COMPLETED, FILTER_FAILED):
        label = _FILTER_LABELS[kind]
        prefix = "● " if kind == filter_kind else ""
        filter_row.append(
            InlineKeyboardButton(
                f"{prefix}{label}",
                callback_data=f"tl:{kind}:0",
            )
        )
    rows.append(filter_row)

    # 任务详情快捷按钮（每个任务一行）
    if task_buttons:
        for task in task_buttons:
            title = task.media_item_title or short_id(task.id)
            if len(title) > 28:
                title = title[:27] + "…"
            rows.append([
                InlineKeyboardButton(
                    f"🔍 {title}",
                    callback_data=f"td:{short_id(task.id)}",
                )
            ])

    # 翻页
    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton("◀ 上一页", callback_data=f"tl:{filter_kind}:{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton("下一页 ▶", callback_data=f"tl:{filter_kind}:{page + 1}"))
    if nav:
        rows.append(nav)

    return InlineKeyboardMarkup(rows)


def render_task_detail(
    task: Task,
    back_filter: str = FILTER_ALL,
    back_page: int = 0,
) -> tuple[str, InlineKeyboardMarkup]:
    """渲染任务详情文本和键盘。"""
    status_value = _task_status_value(task)
    status_str = format_task_status(status_value)
    title = task.media_item_title or "未知"

    lines = [
        f"📺 {title}",
        f"状态: {status_str}",
        f"🆔 {short_id(task.id)}",
    ]

    if task.status == TaskStatus.PROCESSING:
        lines.append(f"进度: {format_progress(task.progress)}")
        if task.started_at:
            lines.append(f"开始于 {format_time_ago(task.started_at)}")
    elif task.status == TaskStatus.COMPLETED:
        if _is_external_subtitle(task):
            lines.append("🔍 字幕来源：外部搜索（迅雷字幕）")
            matched = (task.extra_info or {}).get("matched_languages") or []
            if matched:
                lines.append(f"   命中语言: {', '.join(matched)}")
        else:
            lines.append("🤖 字幕来源：本机 ASR + 翻译")
        if task.processing_time:
            lines.append(f"⏱ 耗时 {format_duration(task.processing_time)}")
        if task.segment_count:
            lines.append(f"📝 字幕条数 {task.segment_count}")
        if task.completed_at:
            lines.append(f"完成于 {format_time_ago(task.completed_at)}")
    elif task.status == TaskStatus.FAILED:
        reason, suggestion = classify(task.error_stage, task.error_message)
        lines.append(f"❗ {reason}")
        lines.append(f"💡 {suggestion}")
        if task.error_message:
            err = task.error_message
            if len(err) > 120:
                err = err[:117] + "..."
            lines.append(f"💬 {err}")

    # 配置摘要（小字）
    cfg_parts = []
    if task.asr_engine:
        cfg_parts.append(f"ASR: {task.asr_engine}")
    if task.translation_service:
        cfg_parts.append(f"翻译: {task.translation_service}")
    if task.source_language and task.target_language:
        cfg_parts.append(f"{task.source_language} → {task.target_language}")
    if cfg_parts:
        lines.append("\n" + " · ".join(cfg_parts))

    text = "\n".join(lines)
    keyboard = render_task_detail_keyboard(task, back_filter, back_page)
    return text, keyboard


def render_task_detail_keyboard(
    task: Task,
    back_filter: str = FILTER_ALL,
    back_page: int = 0,
) -> InlineKeyboardMarkup:
    """构建任务详情键盘，按状态显示不同操作。"""
    rows: list[list[InlineKeyboardButton]] = []
    sid = short_id(task.id)

    if task.status in (TaskStatus.PENDING, TaskStatus.PROCESSING):
        rows.append([InlineKeyboardButton("❌ 取消", callback_data=f"to:x:{sid}")])
    elif task.status == TaskStatus.FAILED:
        rows.append([InlineKeyboardButton("🔄 重试", callback_data=f"to:r:{sid}")])
        rows.append([InlineKeyboardButton("🌐 换源语言重试", callback_data=f"to:rl:{sid}")])
    elif task.status == TaskStatus.COMPLETED:
        # 多语言字幕：每个语言一个按钮；单语言：一个总下载按钮
        subtitles = _list_subtitles(task)
        if len(subtitles) > 1:
            for sub in subtitles:
                lang = sub.get("lang", "")
                rows.append([
                    InlineKeyboardButton(
                        f"📥 下载 {lang}.srt",
                        callback_data=f"to:dl:{sid}:{lang}",
                    )
                ])
        elif task.subtitle_path:
            rows.append([
                InlineKeyboardButton("📥 下载字幕", callback_data=f"to:dl:{sid}")
            ])

    rows.append([
        InlineKeyboardButton(
            "🔙 返回列表",
            callback_data=f"to:back:{back_filter}:{back_page}",
        )
    ])
    return InlineKeyboardMarkup(rows)


def render_completion_notification_keyboard(task: Task) -> Optional[InlineKeyboardMarkup]:
    """完成通知附带的下载/详情键盘。"""
    rows: list[list[InlineKeyboardButton]] = []
    sid = short_id(task.id)

    subtitles = _list_subtitles(task)
    if len(subtitles) > 1:
        for sub in subtitles:
            lang = sub.get("lang", "")
            rows.append([
                InlineKeyboardButton(
                    f"📥 下载 {lang}.srt",
                    callback_data=f"to:dl:{sid}:{lang}",
                )
            ])
    elif task.subtitle_path:
        rows.append([
            InlineKeyboardButton("📥 下载字幕", callback_data=f"to:dl:{sid}")
        ])

    rows.append([
        InlineKeyboardButton("🔍 详情", callback_data=f"td:{sid}")
    ])
    return InlineKeyboardMarkup(rows) if rows else None


def render_failure_notification_keyboard(task: Task) -> InlineKeyboardMarkup:
    """失败通知附带的重试/详情键盘。"""
    sid = short_id(task.id)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 立即重试", callback_data=f"to:r:{sid}")],
        [InlineKeyboardButton("🌐 换源语言重试", callback_data=f"to:rl:{sid}")],
        [InlineKeyboardButton("🔍 详情", callback_data=f"td:{sid}")],
    ])


def _list_subtitles(task: Task) -> list[dict]:
    """从 extra_info 提取多语言字幕条目，没有时返回空列表。"""
    if not task.extra_info:
        return []
    items = task.extra_info.get("subtitles") or []
    if isinstance(items, list):
        return [it for it in items if isinstance(it, dict) and it.get("path")]
    return []


def _is_external_subtitle(task: Task) -> bool:
    """判断任务的字幕是否来自外部搜索（迅雷字幕 API）。"""
    if not task.extra_info:
        return False
    return task.extra_info.get("subtitle_source") == "xunlei_search"


def _task_status_value(task: Task) -> str:
    """统一拿到状态字符串，无论存的是枚举还是字符串。"""
    return task.status.value if isinstance(task.status, TaskStatus) else task.status


__all__ = [
    "FILTER_ALL", "FILTER_ACTIVE", "FILTER_COMPLETED", "FILTER_FAILED",
    "PAGE_SIZE",
    "filter_to_statuses",
    "render_task_list",
    "render_task_detail",
    "render_task_detail_keyboard",
    "render_completion_notification_keyboard",
    "render_failure_notification_keyboard",
]
