"""把用户提供的项目编号和文件路径限制在指定根目录内。"""
from __future__ import annotations

from pathlib import Path


class PathEscapeError(ValueError):
    """路径会离开允许的根目录，或含有目录分隔符。"""


def safe_path_token(value: str, *, kind: str = "名称") -> str:
    """单个路径分量。拒绝空串、`.`、`..` 和分隔符。"""
    if not isinstance(value, str):
        raise PathEscapeError(f"无效的{kind}")
    text = value.strip()
    if not text or text in {".", ".."}:
        raise PathEscapeError(f"无效的{kind}")
    if any(ch in text for ch in "/\\:\x00"):
        raise PathEscapeError(f"无效的{kind}")
    return text


def resolve_contained(root: Path, *parts: str) -> Path:
    """把若干路径分量拼到 root 下，解析后仍必须位于 root 内。"""
    root_resolved = Path(root).resolve()
    current = root_resolved
    for part in parts:
        token = safe_path_token(part)
        current = (current / token).resolve()
        try:
            current.relative_to(root_resolved)
        except ValueError as exc:
            raise PathEscapeError("路径不能离开工作区") from exc
    return current


def contained_file(root: Path, raw: str) -> Path:
    """绝对路径或相对 root 的路径，解析后必须是 root 里面的文件路径。"""
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise PathEscapeError("无效的文件路径")
    root_resolved = Path(root).resolve()
    candidate = Path(raw.strip())
    if not candidate.is_absolute():
        candidate = root_resolved / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PathEscapeError("文件不在项目目录内") from exc
    if resolved == root_resolved:
        raise PathEscapeError("文件不在项目目录内")
    return resolved
