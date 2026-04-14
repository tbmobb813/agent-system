from app.tools.tool_registry import Tool, ToolRegistry


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