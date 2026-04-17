"""
Dual-limit tool output truncation.

Two independent limits — whichever is hit first wins:
  - Line limit (default: 2000 lines)
  - Byte limit (default: 50 KB)

Two strategies:
  - truncate_head: keep the FIRST N lines/bytes — use for file reads,
    where the beginning of the file is most relevant.
  - truncate_tail: keep the LAST N lines/bytes — use for command/code
    output, where errors and final results appear at the end.

Never returns partial lines.
"""

from __future__ import annotations

DEFAULT_MAX_LINES = 2000
DEFAULT_MAX_BYTES = 50 * 1024  # 50 KB


def truncate_head(
    content: str,
    max_lines: int = DEFAULT_MAX_LINES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> str:
    """
    Keep the first N lines or B bytes, whichever limit is hit first.
    Appends a one-line summary when truncated.
    """
    if not content:
        return content

    lines = content.split("\n")
    total_lines = len(lines)
    total_bytes = len(content.encode("utf-8"))

    if total_lines <= max_lines and total_bytes <= max_bytes:
        return content

    kept: list[str] = []
    byte_count = 0

    for i, line in enumerate(lines):
        if i >= max_lines:
            _append_truncation_note(kept, total_lines, total_bytes, i, byte_count, "head")
            return "\n".join(kept)

        line_bytes = len((line + "\n").encode("utf-8"))
        if byte_count + line_bytes > max_bytes:
            _append_truncation_note(kept, total_lines, total_bytes, i, byte_count, "head")
            return "\n".join(kept)

        kept.append(line)
        byte_count += line_bytes

    return "\n".join(kept)


def truncate_tail(
    content: str,
    max_lines: int = DEFAULT_MAX_LINES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> str:
    """
    Keep the last N lines or B bytes, whichever limit is hit first.
    Prepends a one-line summary when truncated.
    Suitable for command/shell output where errors appear at the end.
    """
    if not content:
        return content

    lines = content.split("\n")
    total_lines = len(lines)
    total_bytes = len(content.encode("utf-8"))

    if total_lines <= max_lines and total_bytes <= max_bytes:
        return content

    kept: list[str] = []
    byte_count = 0

    for line in reversed(lines):
        if len(kept) >= max_lines:
            break
        line_bytes = len((line + "\n").encode("utf-8"))
        if byte_count + line_bytes > max_bytes:
            break
        kept.append(line)
        byte_count += line_bytes

    kept.reverse()
    dropped = total_lines - len(kept)
    size_kb = total_bytes / 1024
    note = (
        f"[...{dropped} lines ({size_kb:.1f} KB total) truncated from start — "
        f"showing last {len(kept)} lines]\n"
    )
    return note + "\n".join(kept)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _append_truncation_note(
    kept: list[str],
    total_lines: int,
    total_bytes: int,
    kept_count: int,
    kept_bytes: int,
    strategy: str,
) -> None:
    dropped = total_lines - kept_count
    size_kb = total_bytes / 1024
    kept_kb = kept_bytes / 1024
    kept.append(
        f"[...{dropped} lines ({size_kb:.1f} KB total, showing first {kept_kb:.1f} KB) truncated]"
    )
