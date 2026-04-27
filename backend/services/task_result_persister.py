"""
任务结果持久化辅助。
"""
from typing import Callable, Dict, List


class TaskResultPersister:
    """封装任务日志快照和阶段结果持久化。"""

    def __init__(
        self,
        task_id: str,
        task_manager,
        log_capture,
        run_async: Callable,
    ):
        self.task_id = task_id
        self.task_manager = task_manager
        self.log_capture = log_capture
        self.run_async = run_async

    def with_logs(self, extra: dict) -> dict:
        """合并日志快照到 extra_info 更新载荷。"""
        merged = dict(extra) if extra else {}
        merged["logs"] = self.log_capture.snapshot()
        return merged

    def update_result(self, **kwargs) -> None:
        """同步持久化任务结果字段。"""
        self.run_async(self.task_manager.update_task_result(self.task_id, **kwargs))

    def persist_step_logs(self, step_logs: dict) -> None:
        """持久化阶段日志。"""
        self.update_result(extra_info=self.with_logs({"step_logs": step_logs}))

    def persist_asr_result(self, segment_count: int, step_logs: dict) -> None:
        """持久化 ASR 段落数和阶段日志。"""
        self.update_result(
            segment_count=segment_count,
            extra_info=self.with_logs({"step_logs": step_logs}),
        )

    def persist_stage_weights(self, reporter) -> None:
        """持久化阶段权重，供前端渲染处理流程。"""
        self.update_result(
            extra_info={
                "stage_weights": {
                    name: list(weight)
                    for name, weight in reporter._stages.items()
                },
            }
        )

    def persist_translation_result(
        self,
        step_logs: dict,
        skipped_steps: List[str],
        target_languages: List[str],
        keep_source_subtitle: bool,
    ) -> None:
        """持久化翻译阶段结果摘要。"""
        self.update_result(
            extra_info=self.with_logs({
                "step_logs": step_logs,
                "skipped_steps": skipped_steps,
                "target_languages": list(target_languages),
                "keep_source_subtitle": keep_source_subtitle,
            }),
        )

    def persist_subtitle_result(
        self,
        subtitle_path: str,
        subtitle_paths: Dict[str, str],
        step_logs: dict,
    ) -> None:
        """持久化字幕文件生成结果。"""
        self.update_result(
            subtitle_path=subtitle_path,
            extra_info=self.with_logs({
                "step_logs": step_logs,
                "subtitles": [
                    {"lang": lang_code, "path": path}
                    for lang_code, path in subtitle_paths.items()
                ],
            }),
        )

    def persist_emby_result(
        self,
        step_logs: dict,
        skipped_steps: List[str],
    ) -> None:
        """持久化 Emby 回写结果。"""
        self.update_result(
            extra_info=self.with_logs({
                "step_logs": step_logs,
                "skipped_steps": skipped_steps,
            }),
        )


def format_step_log(stage: str, summary: str) -> str:
    """格式化阶段日志。当前保留透传行为，便于后续统一扩展。"""
    return summary
