"""truncate_head / truncate_tail edge coverage."""

from app.utils.truncate import _append_truncation_note, truncate_head, truncate_tail


def test_empty_content():
    assert truncate_head("") == ""
    assert truncate_tail("") == ""


def test_truncate_head_under_limits():
    s = "a\nb"
    assert truncate_head(s, max_lines=10, max_bytes=10_000) == s


def test_truncate_head_by_lines():
    txt = "\n".join(["x"] * 5)
    out = truncate_head(txt, max_lines=2, max_bytes=10_000)
    assert "truncated" in out
    assert out.startswith("x\nx")


def test_truncate_head_hits_byte_cap():
    long_line = ("a" * 400 + "\n") * 80
    out = truncate_head(long_line, max_lines=5000, max_bytes=200)
    assert "truncated" in out


def test_truncate_tail_hits_byte_cap():
    long_line = ("b" * 400 + "\n") * 80 + "\nfinal"
    out = truncate_tail(long_line, max_lines=5000, max_bytes=200)
    assert "truncated from start" in out


def test_truncate_tail_many_short_lines_keeps_footer():
    tail = ["z"] * 600
    txt = "\n".join(["header"] + tail)
    out = truncate_tail(txt, max_lines=3, max_bytes=50_000)
    assert "truncated from start" in out
    assert len(out.splitlines()) >= 4


def test_append_truncation_note_mutates_kept():
    kept: list[str] = []
    _append_truncation_note(
        kept,
        total_lines=100,
        total_bytes=2048,
        kept_count=2,
        kept_bytes=512,
        strategy="head",
    )
    assert kept and kept[-1].startswith("[...")
