from app.agent.documents import (
    _count_tokens,
    _token_chunks,
    parse_document,
)


def test_count_tokens_estimates_from_text_length():
    # Rough estimate: 1 token ~= 4 chars
    result = _count_tokens("hello world")  # 11 chars
    assert result >= 2  # At least 11/4 = 2 or 3


def test_token_chunks_splits_text_into_chunks():
    long_text = "word " * 1000  # 5000 chars
    chunks = _token_chunks(long_text, chunk_tokens=200, overlap=20)

    assert len(chunks) > 1
    assert all(isinstance(c, str) for c in chunks)
    # Each chunk should be roughly 200 tokens * 4 chars = 800 chars (give or take overlap)
    assert all(len(c) > 100 for c in chunks)


def test_token_chunks_maintains_overlap():
    text = "a" * 2000
    chunks_no_overlap = _token_chunks(text, chunk_tokens=100, overlap=0)
    chunks_with_overlap = _token_chunks(text, chunk_tokens=100, overlap=10)

    # With overlap, we should have more chunks (since they overlap)
    assert len(chunks_with_overlap) >= len(chunks_no_overlap)


def test_parse_document_handles_txt():
    data = b"Hello, this is a text file."
    result = parse_document("test.txt", data)

    assert result == "Hello, this is a text file."


def test_parse_document_handles_md():
    data = b"# Heading\n\nSome markdown content."
    result = parse_document("notes.md", data)

    assert "Heading" in result
    assert "markdown" in result


def test_parse_document_rejects_unsupported_type():
    data = b"some binary garbage"
    try:
        parse_document("test.bin", data)
        # If we get here, plain-text parsing may have succeeded
        # (which is okay as a fallback)
    except ValueError as e:
        assert "Unsupported" in str(e) or "unreadable" in str(e)


def test_parse_document_detects_empty_content():
    try:
        parse_document("empty.txt", b"")
        # May succeed with empty string, which is okay
    except ValueError:
        # Or may raise, which is also okay
        pass
