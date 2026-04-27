"""
Emby 路径映射工具。
"""
from typing import Optional


def apply_path_mapping(
    emby_path: str,
    path_mappings: list,
    path_mapping_index: Optional[int] = None,
    library_id: Optional[str] = None,
) -> Optional[str]:
    """
    将 Emby 服务器上的视频路径映射为本地可访问路径。

    匹配优先级：
    1. 明确指定 path_mapping_index
    2. library_id 匹配映射规则的 library_ids
    3. emby_prefix 前缀匹配（最长前缀优先）
    """
    if not path_mappings:
        return None

    def _do_replace(emby_path: str, emby_prefix: str, local_prefix: str) -> Optional[str]:
        norm_path = emby_path.replace("\\", "/")
        norm_emby_prefix = emby_prefix.replace("\\", "/").rstrip("/")
        norm_local_prefix = local_prefix.replace("\\", "/").rstrip("/")

        if not norm_path.startswith(norm_emby_prefix):
            return None

        suffix = norm_path[len(norm_emby_prefix):]
        result = norm_local_prefix + suffix

        is_windows_local = len(local_prefix) >= 2 and local_prefix[1] == ":"
        if is_windows_local:
            result = result.replace("/", "\\")

        return result

    if path_mapping_index is not None:
        if 0 <= path_mapping_index < len(path_mappings):
            mapping = path_mappings[path_mapping_index]
            emby_prefix = mapping.get("emby_prefix", "")
            local_prefix = mapping.get("local_prefix", "")
            result = _do_replace(emby_path, emby_prefix, local_prefix)
            if result:
                return result

            norm_local = local_prefix.replace("\\", "/").rstrip("/")
            basename = emby_path.replace("\\", "/").split("/")[-1]
            fallback = norm_local + "/" + basename
            is_windows_local = len(local_prefix) >= 2 and local_prefix[1] == ":"
            return fallback.replace("/", "\\") if is_windows_local else fallback
        return None

    if library_id:
        for mapping in path_mappings:
            lib_ids = mapping.get("library_ids", [])
            if library_id in lib_ids:
                result = _do_replace(
                    emby_path,
                    mapping.get("emby_prefix", ""),
                    mapping.get("local_prefix", ""),
                )
                if result:
                    return result

    best_match = None
    best_len = 0
    for mapping in path_mappings:
        norm_prefix = mapping.get("emby_prefix", "").replace("\\", "/").rstrip("/")
        norm_path = emby_path.replace("\\", "/")
        if norm_path.startswith(norm_prefix) and len(norm_prefix) > best_len:
            best_match = mapping
            best_len = len(norm_prefix)

    if best_match:
        result = _do_replace(emby_path, best_match["emby_prefix"], best_match["local_prefix"])
        if result:
            return result

    return None
