from app.utils.http_headers import redact_response_headers


def test_redact_response_headers_strips_sensitive_names():
    raw = {
        'Content-Type': 'application/json',
        'Set-Cookie': 'session=secret',
        'authorization': 'Bearer token',
        'X-Custom': 'visible',
    }
    out = redact_response_headers(raw)

    assert out['Content-Type'] == 'application/json'
    assert out['Set-Cookie'] == '[redacted]'
    assert out['authorization'] == '[redacted]'
    assert out['X-Custom'] == 'visible'
