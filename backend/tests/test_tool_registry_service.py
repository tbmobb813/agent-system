from app.tools.tool_registry import Tool, ToolRegistry
import types
import sys
import httpx
from pathlib import Path


def _sync_add(a: int, b: int) -> int:
    return a + b


async def _async_echo(value: str) -> str:
    return value


async def test_tool_call_supports_sync_and_async_functions():
    sync_tool = Tool('sync_add', _sync_add, 'add numbers', ['a', 'b'])
    async_tool = Tool('async_echo', _async_echo, 'echo value', ['value'])

    assert await sync_tool.call(a=2, b=3) == 5
    assert await async_tool.call(value='ok') == 'ok'


async def test_registry_call_validates_missing_required_args():
    registry = ToolRegistry()

    try:
        await registry.call('web_search')
        assert False, 'Expected missing required argument error'
    except ValueError as exc:
        assert 'Missing required argument: query' in str(exc)


def test_get_tool_schemas_can_be_restricted_and_filtered():
    registry = ToolRegistry()

    schemas = registry.get_tool_schemas(['web_search', 'nonexistent'])

    assert len(schemas) == 1
    assert schemas[0]['function']['name'] == 'web_search'


def test_get_tool_info_returns_empty_for_unknown_tool():
    registry = ToolRegistry()

    assert registry.get_tool_info('missing_tool') == {}


async def test_api_call_rejects_non_http_urls():
    registry = ToolRegistry()

    result = await registry._api_call(url='ftp://example.com', method='GET')

    assert result == {'error': 'URL must start with http:// or https://'}


async def test_file_operations_blocks_path_traversal(tmp_path):
    registry = ToolRegistry()

    result = await registry._file_operations(
        operation='read',
        path='../../etc/passwd',
        workspace=str(tmp_path),
    )

    assert result == 'Error: path traversal not allowed'


async def test_file_operations_blocks_sibling_directory_prefix_escape(tmp_path):
    """Regression: startswith(realpath(ws)) wrongly allowed /ws_evil when workspace was /ws."""
    sandbox = tmp_path / 'sandbox'
    sandbox.mkdir()
    evil = tmp_path / 'sandbox_evil'
    evil.mkdir()
    (evil / 'secret.txt').write_text('nope')

    registry = ToolRegistry()
    result = await registry._file_operations(
        operation='read',
        path='../sandbox_evil/secret.txt',
        workspace=str(sandbox),
    )

    assert result == 'Error: path traversal not allowed'


async def test_api_call_blocks_loopback_url():
    registry = ToolRegistry()

    result = await registry._api_call(url='http://127.0.0.1/', method='GET')

    assert 'error' in result
    assert 'non-public' in result['error'].lower() or 'not allowed' in result['error'].lower()


def test_list_tools_contains_expected_builtin_tools():
    """Builtin tools are always available to the orchestrator."""
    registry = ToolRegistry()
    names = registry.list_tools()

    assert 'web_search' in names
    assert 'browser_automation' in names
    assert 'file_operations' in names
    assert 'code_execution' in names
    assert 'api_call' in names
    assert 'search_documents' in names


async def test_registry_call_raises_for_unknown_tool():
    registry = ToolRegistry()

    try:
        await registry.call('not_a_tool', query='x')
        assert False, 'Expected unknown tool error'
    except ValueError as exc:
        assert 'Tool not found' in str(exc)


async def test_web_search_uses_primary_when_results_available(monkeypatch):
    registry = ToolRegistry()

    async def fake_primary(query, max_results=5):
        return {'query': query, 'results': [{'title': 'x'}], 'provider': 'searxng'}

    async def fake_fallback(query, max_results=5):
        return {'query': query, 'results': [], 'provider': 'brave'}

    monkeypatch.setattr(registry, '_searxng_search', fake_primary)
    monkeypatch.setattr(registry, '_brave_search', fake_fallback)

    result = await registry._web_search('latest ai')

    assert result['provider'] == 'searxng'
    assert len(result['results']) == 1


async def test_web_search_falls_back_when_primary_empty(monkeypatch):
    registry = ToolRegistry()

    async def fake_primary(query, max_results=5):
        return {'query': query, 'results': []}

    async def fake_fallback(query, max_results=5):
        return {'query': query, 'results': [{'title': 'fallback'}], 'provider': 'brave'}

    monkeypatch.setattr(registry, '_searxng_search', fake_primary)
    monkeypatch.setattr(registry, '_brave_search', fake_fallback)

    result = await registry._web_search('fallback')

    assert result['provider'] == 'brave'
    assert result['results'][0]['title'] == 'fallback'


async def test_brave_search_returns_error_when_key_missing(monkeypatch):
    registry = ToolRegistry()
    monkeypatch.setattr('app.config.settings.BRAVE_SEARCH_API_KEY', '')

    result = await registry._brave_search('no key')

    assert result['error'] == 'no_search_provider_available'


async def test_file_operations_write_read_list_delete_roundtrip(tmp_path):
    registry = ToolRegistry()
    workspace = str(tmp_path)

    write_result = await registry._file_operations(
        operation='write',
        path='notes/a.txt',
        content='hello tools',
        workspace=workspace,
    )
    assert 'Written' in write_result

    read_result = await registry._file_operations(
        operation='read',
        path='notes/a.txt',
        workspace=workspace,
    )
    assert read_result == 'hello tools'

    list_result = await registry._file_operations(
        operation='list',
        path='notes',
        workspace=workspace,
    )
    assert 'a.txt' in list_result

    delete_result = await registry._file_operations(
        operation='delete',
        path='notes/a.txt',
        workspace=workspace,
    )
    assert 'Deleted' in delete_result


async def test_code_execution_reports_disabled_without_key(monkeypatch):
    registry = ToolRegistry()
    monkeypatch.setattr('app.config.settings.E2B_API_KEY', '')

    result = await registry._code_execution('print(1)', language='python')

    assert 'Code execution not available' in result


async def test_search_documents_formats_results(monkeypatch):
    registry = ToolRegistry()

    async def fake_search(query, limit=5, document_id=None, user_id=None):
        return [
            {'filename': 'doc.txt', 'chunk_index': 0, 'content': 'alpha'},
            {'filename': 'doc2.txt', 'chunk_index': 2, 'content': 'beta'},
        ]

    monkeypatch.setattr('app.agent.documents.search_documents', fake_search)

    result = await registry._search_documents('topic', limit=2)

    assert 'doc.txt' in result
    assert 'chunk 0' in result
    assert 'doc2.txt' in result


async def test_search_documents_returns_no_results_message(monkeypatch):
    registry = ToolRegistry()

    async def fake_search(query, limit=5, document_id=None, user_id=None):
        return []

    monkeypatch.setattr('app.agent.documents.search_documents', fake_search)

    result = await registry._search_documents('none')

    assert 'No relevant content found' in result


async def test_searxng_search_handles_connect_error(monkeypatch):
    registry = ToolRegistry()

    class _FailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            raise httpx.ConnectError('no route')

    monkeypatch.setattr('app.tools.tool_registry.httpx.AsyncClient', lambda timeout=15.0: _FailClient())

    result = await registry._searxng_search('q')

    assert result['error'] == 'searxng_unreachable'


async def test_searxng_search_handles_generic_exception(monkeypatch):
    registry = ToolRegistry()

    class _FailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            raise RuntimeError('boom')

    monkeypatch.setattr('app.tools.tool_registry.httpx.AsyncClient', lambda timeout=15.0: _FailClient())

    result = await registry._searxng_search('q')

    assert result['error'] == 'boom'


async def test_brave_search_handles_generic_exception(monkeypatch):
    registry = ToolRegistry()
    monkeypatch.setattr('app.config.settings.BRAVE_SEARCH_API_KEY', 'token')

    class _FailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            raise RuntimeError('brave down')

    monkeypatch.setattr('app.tools.tool_registry.httpx.AsyncClient', lambda timeout=15.0: _FailClient())

    result = await registry._brave_search('q')

    assert result['error'] == 'brave down'


def _stub_outbound_url_checks(monkeypatch):
    """Tests mock httpx/Playwright; skip live DNS for hostname SSRF checks."""
    monkeypatch.setattr(
        'app.tools.tool_registry.validate_agent_outbound_url',
        lambda _url: (True, ''),
    )


async def test_api_call_handles_timeout(monkeypatch):
    registry = ToolRegistry()
    _stub_outbound_url_checks(monkeypatch)

    class _TimeoutClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, *args, **kwargs):
            raise httpx.TimeoutException('slow')

    monkeypatch.setattr('app.tools.tool_registry.httpx.AsyncClient', lambda timeout=15.0: _TimeoutClient())

    result = await registry._api_call(url='https://example.com', timeout=3.0)

    assert result['error'] == 'Request timed out after 3.0s'


async def test_api_call_handles_non_json_response(monkeypatch):
    registry = ToolRegistry()
    _stub_outbound_url_checks(monkeypatch)

    class _Resp:
        status_code = 200
        headers = {'x': 'y'}
        text = 'plain text body'

        def json(self):
            raise ValueError('no json')

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr('app.tools.tool_registry.httpx.AsyncClient', lambda timeout=15.0: _Client())

    result = await registry._api_call(url='https://example.com')

    assert result['status'] == 200
    assert result['data'] == 'plain text body'


async def test_file_operations_read_missing_and_unknown_op(tmp_path):
    registry = ToolRegistry()

    missing = await registry._file_operations(
        operation='read',
        path='missing.txt',
        workspace=str(tmp_path),
    )
    assert 'file not found' in missing

    unknown = await registry._file_operations(
        operation='rename',
        path='x.txt',
        workspace=str(tmp_path),
    )
    assert 'Unknown operation' in unknown


async def test_code_execution_import_and_runtime_error_branches(monkeypatch):
    registry = ToolRegistry()
    monkeypatch.setattr('app.config.settings.E2B_API_KEY', 'present')

    # ImportError path
    class _ImportGuard(dict):
        pass

    original = sys.modules.pop('e2b_code_interpreter', None)
    try:
        result_import = await registry._code_execution('print(1)')
    finally:
        if original is not None:
            sys.modules['e2b_code_interpreter'] = original

    assert 'install e2b-code-interpreter package' in result_import

    # Runtime error path via fake module
    class _BoomSandbox:
        async def __aenter__(self):
            raise RuntimeError('sandbox fail')

        async def __aexit__(self, *args):
            return False

    fake_module = types.SimpleNamespace(Sandbox=lambda: _BoomSandbox())
    monkeypatch.setitem(sys.modules, 'e2b_code_interpreter', fake_module)

    result_runtime = await registry._code_execution('print(1)')
    assert 'Code execution failed: sandbox fail' in result_runtime


async def test_searxng_search_success_path(monkeypatch):
    registry = ToolRegistry()

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                'results': [
                    {'title': 'A', 'url': 'https://a.test', 'content': 'alpha', 'engine': 'x'},
                    {'title': 'B', 'url': 'https://b.test', 'content': 'beta', 'engine': 'y'},
                ]
            }

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr('app.tools.tool_registry.httpx.AsyncClient', lambda timeout=15.0: _Client())

    result = await registry._searxng_search('query', max_results=1)
    assert result['provider'] == 'searxng'
    assert result['total'] == 1
    assert result['results'][0]['title'] == 'A'


async def test_brave_search_success_path(monkeypatch):
    registry = ToolRegistry()
    monkeypatch.setattr('app.config.settings.BRAVE_SEARCH_API_KEY', 'token')

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                'web': {
                    'results': [
                        {'title': 'News', 'url': 'https://news.test', 'description': 'desc'}
                    ]
                }
            }

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr('app.tools.tool_registry.httpx.AsyncClient', lambda timeout=15.0: _Client())

    result = await registry._brave_search('query', max_results=1)
    assert result['provider'] == 'brave'
    assert result['total'] == 1
    assert result['results'][0]['title'] == 'News'


async def test_code_execution_success_path(monkeypatch):
    registry = ToolRegistry()
    monkeypatch.setattr('app.config.settings.E2B_API_KEY', 'present')

    class _Result:
        results = ['ok']
        error = None

    class _Sandbox:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def run_code(self, code):
            return _Result()

    fake_module = types.SimpleNamespace(Sandbox=lambda: _Sandbox())
    monkeypatch.setitem(sys.modules, 'e2b_code_interpreter', fake_module)

    result = await registry._code_execution('print(1)')
    assert result == 'ok'


def _install_fake_playwright(monkeypatch, *, fail_on_goto: bool = False):
    class _Element:
        def __init__(self, text):
            self._text = text

        async def inner_text(self):
            return self._text

    class _Page:
        async def goto(self, url, timeout=None, wait_until=None):
            if fail_on_goto:
                raise RuntimeError('goto failed')

        async def wait_for_selector(self, selector, timeout=None):
            return None

        async def title(self):
            return 'Fake Title'

        async def evaluate(self, script):
            return 'Body text from page'

        async def query_selector_all(self, selector):
            return [_Element('one'), _Element('two')]

        async def screenshot(self, path=None, full_page=True):
            if path:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                Path(path).write_bytes(b'fake-image')

        async def click(self, selector, timeout=None):
            return None

        async def fill(self, selector, text):
            return None

    class _Browser:
        async def new_page(self):
            return _Page()

        async def close(self):
            return None

    class _Chromium:
        async def launch(self, headless=True):
            return _Browser()

    class _PW:
        chromium = _Chromium()

    class _Ctx:
        async def __aenter__(self):
            return _PW()

        async def __aexit__(self, *args):
            return False

    fake_module = types.SimpleNamespace(async_playwright=lambda: _Ctx())
    monkeypatch.setitem(sys.modules, 'playwright.async_api', fake_module)


async def test_browser_automation_success_actions(monkeypatch, tmp_path):
    registry = ToolRegistry()
    _stub_outbound_url_checks(monkeypatch)
    _install_fake_playwright(monkeypatch)

    nav = await registry._browser_automation(action='navigate', url='https://example.com')
    assert 'Title: Fake Title' in nav

    ext = await registry._browser_automation(action='extract', url='https://example.com', selector='.item')
    assert 'one' in ext and 'two' in ext

    shot_path = str(tmp_path / 'shot.png')
    shot = await registry._browser_automation(action='screenshot', url='https://example.com', screenshot_path=shot_path)
    assert 'Screenshot saved' in shot

    click = await registry._browser_automation(action='click', url='https://example.com', selector='#btn')
    assert 'Clicked: #btn' == click

    fill = await registry._browser_automation(action='fill', url='https://example.com', selector='#name', text='Ada')
    assert "Filled '#name' with text" == fill


async def test_browser_automation_validation_and_error_paths(monkeypatch):
    registry = ToolRegistry()
    _stub_outbound_url_checks(monkeypatch)
    _install_fake_playwright(monkeypatch)

    missing_url = await registry._browser_automation(action='navigate', url='')
    assert missing_url == 'Error: url is required'

    missing_selector = await registry._browser_automation(action='extract', url='https://example.com')
    assert missing_selector == 'Error: selector is required for extract/scrape'

    unknown = await registry._browser_automation(action='other', url='https://example.com')
    assert 'Unknown action' in unknown

    _install_fake_playwright(monkeypatch, fail_on_goto=True)
    err = await registry._browser_automation(action='navigate', url='https://example.com')
    assert 'Browser automation error: goto failed' in err