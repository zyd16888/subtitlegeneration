"""
任务失败错误归类与用户友好提示。

把 Task.error_stage / error_message 映射为可读的"原因 + 建议"，
让用户在通知里第一眼就知道接下来该怎么办（重试、找管理员、还是改配置）。
"""
from typing import Optional


# error_stage（如果 worker 写入了）→ 友好说明
_STAGE_HINTS: dict[str, tuple[str, str]] = {
    "audio_extraction": ("音频提取失败", "通常是源文件无法访问或 FFmpeg 出错，可重试一次"),
    "asr": ("语音识别失败", "可能是模型加载超时或音频损坏，可重试或联系管理员切换 ASR 引擎"),
    "translation": ("翻译失败", "翻译服务可能临时不可用或超出配额，稍后重试"),
    "subtitle_generation": ("字幕生成失败", "请联系管理员检查输出目录权限"),
    "emby_upload": ("回写 Emby 失败", "Emby 服务可能不可达，可重试；如果仍然失败请联系管理员"),
}


# 关键字 → 友好说明（按顺序匹配，先命中先用）
_KEYWORD_HINTS: list[tuple[tuple[str, ...], tuple[str, str]]] = [
    (
        ("ffmpeg", "audio_extract", "extract_audio"),
        ("音频提取失败", "通常是源文件无法访问或 FFmpeg 出错，可重试一次"),
    ),
    (
        ("timeout", "timed out", "超时"),
        ("处理超时", "可能是音频较长或外部服务慢，重试时建议错峰"),
    ),
    (
        ("connection", "connect", "refused", "unreachable", "network"),
        ("网络连接失败", "请确认 Emby/翻译服务可达，稍后重试"),
    ),
    (
        ("api key", "apikey", "unauthorized", "401", "403"),
        ("认证失败", "API Key 失效或无权限，请联系管理员检查配置"),
    ),
    (
        ("rate limit", "too many requests", "429", "quota"),
        ("接口限流", "翻译服务超出配额，稍后重试"),
    ),
    (
        ("translation", "translate"),
        ("翻译失败", "翻译服务临时异常，稍后重试"),
    ),
    (
        ("asr", "transcrib", "sherpa", "model"),
        ("语音识别失败", "可能是模型加载或音频问题，可重试或联系管理员"),
    ),
    (
        ("emby", "upload"),
        ("回写 Emby 失败", "Emby 临时不可达，可重试"),
    ),
    (
        ("permission", "denied", "no such file", "not found", "ioerror"),
        ("文件访问错误", "请联系管理员检查工作目录或源文件权限"),
    ),
]


def classify(error_stage: Optional[str], error_message: Optional[str]) -> tuple[str, str]:
    """
    把错误归类成 (简短原因, 建议)。

    Args:
        error_stage: Task.error_stage（可能为 None）
        error_message: Task.error_message（可能为 None）

    Returns:
        (reason, suggestion) 二元组。命中不到任何规则时返回通用兜底。
    """
    if error_stage:
        hit = _STAGE_HINTS.get(error_stage.lower())
        if hit:
            return hit

    if error_message:
        msg_lower = error_message.lower()
        for keywords, hint in _KEYWORD_HINTS:
            for kw in keywords:
                if kw in msg_lower:
                    return hint

    return ("生成失败", "可重试一次；多次失败请联系管理员")
