"""Tests for app/tools/connectors/github.py — GitHub API connector."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from app.tools.connectors.github import github_action


def _mock_response(status_code: int, body) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status_code
    r.json.return_value = body
    r.text = json.dumps(body) if isinstance(body, (dict, list)) else str(body)
    return r


def _make_client(*responses: MagicMock):
    """Return an async context-manager mock whose .get/.post return responses in order."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    response_iter = iter(responses)

    async def _get(url, **kwargs):
        return next(response_iter)

    async def _post(url, **kwargs):
        return next(response_iter)

    client.get = _get
    client.post = _post
    return client


# ── no token ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_token_returns_error():
    result = await github_action("search_repos", token="", query="flask")
    assert "error" in result
    assert "GITHUB_TOKEN" in result["error"]


# ── unknown action ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_action_returns_error():
    with patch("httpx.AsyncClient", return_value=_make_client()):
        result = await github_action("fly_to_moon", token="tok")
    assert "error" in result
    assert "Unknown action" in result["error"]


# ── search_repos ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_repos_missing_query():
    with patch("httpx.AsyncClient", return_value=_make_client()):
        result = await github_action("search_repos", token="tok")
    assert "error" in result


@pytest.mark.asyncio
async def test_search_repos_success():
    body = {
        "total_count": 1,
        "items": [
            {
                "full_name": "owner/repo",
                "description": "A repo",
                "stargazers_count": 42,
                "language": "Python",
                "html_url": "https://github.com/owner/repo",
                "updated_at": "2024-01-01",
            }
        ],
    }
    client = _make_client(_mock_response(200, body))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action("search_repos", token="tok", query="flask")
    assert result["total"] == 1
    assert result["repos"][0]["full_name"] == "owner/repo"


@pytest.mark.asyncio
async def test_search_repos_api_error():
    client = _make_client(_mock_response(403, {"message": "Forbidden"}))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action("search_repos", token="tok", query="test")
    assert "error" in result
    assert "403" in result["error"]


# ── get_repo ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_repo_missing_repo():
    with patch("httpx.AsyncClient", return_value=_make_client()):
        result = await github_action("get_repo", token="tok")
    assert "error" in result


@pytest.mark.asyncio
async def test_get_repo_not_found():
    client = _make_client(_mock_response(404, {}))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action("get_repo", token="tok", repo="owner/missing")
    assert "error" in result
    assert "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_repo_success():
    body = {
        "full_name": "owner/repo",
        "description": "desc",
        "stargazers_count": 10,
        "forks_count": 2,
        "open_issues_count": 1,
        "language": "Python",
        "topics": ["ml"],
        "default_branch": "main",
        "license": {"name": "MIT"},
        "html_url": "https://github.com/owner/repo",
        "created_at": "2020-01-01",
        "updated_at": "2024-01-01",
    }
    client = _make_client(_mock_response(200, body))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action("get_repo", token="tok", repo="owner/repo")
    assert result["full_name"] == "owner/repo"
    assert result["stars"] == 10
    assert result["license"] == "MIT"


# ── list_issues ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_issues_missing_repo():
    with patch("httpx.AsyncClient", return_value=_make_client()):
        result = await github_action("list_issues", token="tok")
    assert "error" in result


@pytest.mark.asyncio
async def test_list_issues_success():
    body = [
        {
            "number": 1,
            "title": "Bug",
            "state": "open",
            "labels": [{"name": "bug"}],
            "user": {"login": "alice"},
            "comments": 3,
            "created_at": "2024-01-01",
            "html_url": "https://github.com/owner/repo/issues/1",
        },
        # This one should be excluded (it's a PR)
        {
            "number": 2,
            "title": "PR",
            "state": "open",
            "labels": [],
            "user": {"login": "bob"},
            "comments": 0,
            "created_at": "2024-01-02",
            "html_url": "https://github.com/owner/repo/pull/2",
            "pull_request": {},
        },
    ]
    client = _make_client(_mock_response(200, body))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action("list_issues", token="tok", repo="owner/repo")
    assert result["count"] == 1
    assert result["issues"][0]["number"] == 1


# ── get_issue ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_issue_missing_params():
    with patch("httpx.AsyncClient", return_value=_make_client()):
        result = await github_action("get_issue", token="tok", repo="owner/repo")
    assert "error" in result


@pytest.mark.asyncio
async def test_get_issue_not_found():
    client = _make_client(_mock_response(404, {}))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action(
            "get_issue", token="tok", repo="owner/repo", issue_number=99
        )
    assert "error" in result


@pytest.mark.asyncio
async def test_get_issue_success():
    issue_body = {
        "number": 5,
        "title": "Some issue",
        "state": "open",
        "user": {"login": "alice"},
        "labels": [{"name": "enhancement"}],
        "body": "Please fix this",
        "comments": 1,
        "created_at": "2024-01-01",
        "html_url": "https://github.com/owner/repo/issues/5",
    }
    comments_body = [{"user": {"login": "bob"}, "body": "Agreed"}]
    client = _make_client(
        _mock_response(200, issue_body), _mock_response(200, comments_body)
    )
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action(
            "get_issue", token="tok", repo="owner/repo", issue_number=5
        )
    assert result["number"] == 5
    assert result["comments"][0]["author"] == "bob"


# ── create_issue ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_issue_missing_params():
    with patch("httpx.AsyncClient", return_value=_make_client()):
        result = await github_action("create_issue", token="tok", repo="owner/repo")
    assert "error" in result


@pytest.mark.asyncio
async def test_create_issue_success():
    body = {
        "number": 10,
        "title": "New bug",
        "html_url": "https://github.com/owner/repo/issues/10",
    }
    client = _make_client(_mock_response(201, body))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action(
            "create_issue",
            token="tok",
            repo="owner/repo",
            title="New bug",
            body="details",
            labels="bug,help",
        )
    assert result["created"] is True
    assert result["number"] == 10


@pytest.mark.asyncio
async def test_create_issue_api_error():
    client = _make_client(_mock_response(422, {"message": "Unprocessable"}))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action(
            "create_issue", token="tok", repo="owner/repo", title="x"
        )
    assert "error" in result


# ── comment_issue ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_comment_issue_missing_params():
    with patch("httpx.AsyncClient", return_value=_make_client()):
        result = await github_action("comment_issue", token="tok", repo="owner/repo")
    assert "error" in result


@pytest.mark.asyncio
async def test_comment_issue_success():
    body = {"html_url": "https://github.com/owner/repo/issues/1#issuecomment-1"}
    client = _make_client(_mock_response(201, body))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action(
            "comment_issue", token="tok", repo="owner/repo", issue_number=1, body="LGTM"
        )
    assert result["commented"] is True


# ── list_prs ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_prs_missing_repo():
    with patch("httpx.AsyncClient", return_value=_make_client()):
        result = await github_action("list_prs", token="tok")
    assert "error" in result


@pytest.mark.asyncio
async def test_list_prs_success():
    body = [
        {
            "number": 3,
            "title": "Add feature",
            "state": "open",
            "user": {"login": "dev"},
            "base": {"ref": "main"},
            "head": {"ref": "feature/x"},
            "draft": False,
            "created_at": "2024-01-01",
            "html_url": "https://github.com/owner/repo/pull/3",
        }
    ]
    client = _make_client(_mock_response(200, body))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action("list_prs", token="tok", repo="owner/repo")
    assert len(result["prs"]) == 1
    assert result["prs"][0]["number"] == 3


# ── get_pr ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_pr_missing_params():
    with patch("httpx.AsyncClient", return_value=_make_client()):
        result = await github_action("get_pr", token="tok", repo="owner/repo")
    assert "error" in result


@pytest.mark.asyncio
async def test_get_pr_not_found():
    client = _make_client(_mock_response(404, {}))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action(
            "get_pr", token="tok", repo="owner/repo", pr_number=99
        )
    assert "error" in result


@pytest.mark.asyncio
async def test_get_pr_success():
    body = {
        "number": 7,
        "title": "Fix bug",
        "state": "open",
        "user": {"login": "alice"},
        "base": {"ref": "main"},
        "head": {"ref": "fix/bug"},
        "draft": False,
        "mergeable": True,
        "additions": 10,
        "deletions": 2,
        "changed_files": 3,
        "body": "Fixes the crash",
        "created_at": "2024-01-01",
        "html_url": "https://github.com/owner/repo/pull/7",
    }
    client = _make_client(_mock_response(200, body))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action(
            "get_pr", token="tok", repo="owner/repo", pr_number=7
        )
    assert result["number"] == 7
    assert result["additions"] == 10


# ── get_file ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_file_missing_params():
    with patch("httpx.AsyncClient", return_value=_make_client()):
        result = await github_action("get_file", token="tok", repo="owner/repo")
    assert "error" in result


@pytest.mark.asyncio
async def test_get_file_not_found():
    client = _make_client(_mock_response(404, {}))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action(
            "get_file", token="tok", repo="owner/repo", path="missing.txt"
        )
    assert "error" in result


@pytest.mark.asyncio
async def test_get_file_success():
    content = base64.b64encode(b"print('hello')").decode()
    body = {
        "path": "hello.py",
        "size": 14,
        "sha": "abc123",
        "content": content + "\n",
        "html_url": "https://github.com/owner/repo/blob/main/hello.py",
    }
    client = _make_client(_mock_response(200, body))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action(
            "get_file", token="tok", repo="owner/repo", path="hello.py", branch="main"
        )
    assert result["content"] == "print('hello')"
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_get_file_directory():
    body = [
        {"name": "README.md", "type": "file"},
        {"name": "src", "type": "dir"},
    ]
    client = _make_client(_mock_response(200, body))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action(
            "get_file", token="tok", repo="owner/repo", path="/src"
        )
    assert result["type"] == "directory"
    assert len(result["entries"]) == 2


# ── list_commits ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_commits_missing_repo():
    with patch("httpx.AsyncClient", return_value=_make_client()):
        result = await github_action("list_commits", token="tok")
    assert "error" in result


@pytest.mark.asyncio
async def test_list_commits_success():
    body = [
        {
            "sha": "abcdef1234567890",
            "commit": {
                "message": "Initial commit\n\nMore details",
                "author": {"name": "Alice", "date": "2024-01-01T00:00:00Z"},
            },
            "html_url": "https://github.com/owner/repo/commit/abcdef1",
        }
    ]
    client = _make_client(_mock_response(200, body))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action(
            "list_commits", token="tok", repo="owner/repo", branch="main"
        )
    assert len(result["commits"]) == 1
    assert result["commits"][0]["sha"] == "abcdef12"
    assert result["commits"][0]["message"] == "Initial commit"


# ── get_user ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_user_not_found():
    client = _make_client(_mock_response(404, {}))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action("get_user", token="tok", username="ghost404")
    assert "error" in result


@pytest.mark.asyncio
async def test_get_user_success():
    body = {
        "login": "octocat",
        "name": "The Octocat",
        "bio": "GitHub mascot",
        "company": "GitHub",
        "location": "San Francisco",
        "public_repos": 8,
        "followers": 9999,
        "html_url": "https://github.com/octocat",
    }
    client = _make_client(_mock_response(200, body))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action("get_user", token="tok", username="octocat")
    assert result["login"] == "octocat"
    assert result["followers"] == 9999


@pytest.mark.asyncio
async def test_get_user_me_uses_user_endpoint():
    body = {
        "login": "me",
        "name": "Me",
        "bio": "",
        "company": "",
        "location": "",
        "public_repos": 1,
        "followers": 0,
        "html_url": "https://github.com/me",
    }
    client = _make_client(_mock_response(200, body))
    with patch("httpx.AsyncClient", return_value=client):
        result = await github_action("get_user", token="tok")
    assert result["login"] == "me"
