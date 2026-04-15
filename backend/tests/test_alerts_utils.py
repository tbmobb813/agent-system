from unittest.mock import AsyncMock

from app.utils.alerts import AlertManager


async def test_check_and_notify_skips_when_budget_non_positive(monkeypatch):
    mgr = AlertManager()
    send_mock = AsyncMock()
    monkeypatch.setattr(mgr, '_send', send_mock)

    await mgr.check_and_notify(spent=10, budget=0)

    send_mock.assert_not_awaited()


async def test_check_and_notify_deduplicates_thresholds_per_month(monkeypatch):
    mgr = AlertManager()
    send_mock = AsyncMock()
    monkeypatch.setattr(mgr, '_send', send_mock)

    await mgr.check_and_notify(spent=96, budget=100)  # triggers 80% and 95%
    await mgr.check_and_notify(spent=97, budget=100)  # same month, should not trigger again

    assert send_mock.await_count == 2


async def test_send_calls_telegram_and_webhook(monkeypatch):
    mgr = AlertManager()
    t_mock = AsyncMock()
    w_mock = AsyncMock()
    monkeypatch.setattr(mgr, '_telegram', t_mock)
    monkeypatch.setattr(mgr, '_webhook', w_mock)

    await mgr._send('warn', spent=8.0, budget=10.0, percent=80.0)

    t_mock.assert_awaited_once()
    w_mock.assert_awaited_once()


async def test_telegram_skips_when_missing_config(monkeypatch):
    mgr = AlertManager()
    monkeypatch.setattr('app.config.settings.TELEGRAM_BOT_TOKEN', '')
    monkeypatch.setattr('app.config.settings.TELEGRAM_CHAT_ID', '')

    # Should not raise and should return early.
    await mgr._telegram('hello')


async def test_telegram_handles_non_200_response(monkeypatch):
    mgr = AlertManager()
    monkeypatch.setattr('app.config.settings.TELEGRAM_BOT_TOKEN', 'token')
    monkeypatch.setattr('app.config.settings.TELEGRAM_CHAT_ID', 'chat')

    class _Resp:
        status_code = 500
        text = 'fail'

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr('app.utils.alerts.httpx.AsyncClient', lambda timeout=10.0: _Client())

    await mgr._telegram('hello')


async def test_telegram_handles_exception(monkeypatch):
    mgr = AlertManager()
    monkeypatch.setattr('app.config.settings.TELEGRAM_BOT_TOKEN', 'token')
    monkeypatch.setattr('app.config.settings.TELEGRAM_CHAT_ID', 'chat')

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            raise RuntimeError('network down')

    monkeypatch.setattr('app.utils.alerts.httpx.AsyncClient', lambda timeout=10.0: _Client())

    await mgr._telegram('hello')


async def test_webhook_skips_when_url_missing(monkeypatch):
    mgr = AlertManager()
    monkeypatch.setattr('app.config.settings.ALERT_WEBHOOK_URL', '')

    await mgr._webhook('warn', 8.0, 10.0, 80.0)


async def test_webhook_handles_success_failure_and_exception(monkeypatch):
    mgr = AlertManager()
    monkeypatch.setattr('app.config.settings.ALERT_WEBHOOK_URL', 'https://example.com/hook')

    class _RespOK:
        status_code = 200

    class _RespFail:
        status_code = 500

    class _ClientOK:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return _RespOK()

    class _ClientFail:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return _RespFail()

    class _ClientBoom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            raise RuntimeError('hook down')

    monkeypatch.setattr('app.utils.alerts.httpx.AsyncClient', lambda timeout=10.0: _ClientOK())
    await mgr._webhook('warn', 8.0, 10.0, 80.0)

    monkeypatch.setattr('app.utils.alerts.httpx.AsyncClient', lambda timeout=10.0: _ClientFail())
    await mgr._webhook('warn', 8.0, 10.0, 80.0)

    monkeypatch.setattr('app.utils.alerts.httpx.AsyncClient', lambda timeout=10.0: _ClientBoom())
    await mgr._webhook('warn', 8.0, 10.0, 80.0)
