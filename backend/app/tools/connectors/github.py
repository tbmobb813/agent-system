"""
GitHub connector — gives the agent read/write access to GitHub via a Personal Access Token.

Supported actions:
  search_repos   — search public/private repos
  get_repo       — repo metadata (stars, description, language, topics)
  list_issues    — open/closed issues in a repo
  get_issue      — single issue + first page of comments
  create_issue   — open a new issue
  comment_issue  — add a comment to an existing issue
  list_prs       — open/closed pull requests
  get_pr         — single PR + review summary
  get_file       — read a file from a branch (raw content)
  list_commits   — recent commits on a branch
  get_user       — public profile of any GitHub user
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_TIMEOUT = 15.0


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _err(msg: str) -> dict[str, Any]:
    return {"error": msg}


async def github_action(
    action: str,
    token: str,
    *,
    # common
    repo: str = "",  # "owner/repo"
    query: str = "",
    # issues / PRs
    issue_number: int = 0,
    pr_number: int = 0,
    title: str = "",
    body: str = "",
    state: str = "open",
    labels: str = "",  # comma-separated
    limit: int = 20,
    # file / commits
    path: str = "",
    branch: str = "",
    # user
    username: str = "",
) -> Any:
    """Dispatch a GitHub API action and return a concise result dict."""

    if not token:
        return _err(
            "GITHUB_TOKEN is not configured. Add it to backend/.env to use GitHub connector."
        )

    headers = _headers(token)

    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=headers) as gh:

        # ── search_repos ───────────────────────────────────────────────────
        if action == "search_repos":
            if not query:
                return _err("query is required for search_repos")
            r = await gh.get(
                f"{_GITHUB_API}/search/repositories",
                params={"q": query, "per_page": min(limit, 30), "sort": "stars"},
            )
            if r.status_code != 200:
                return _err(f"GitHub API error {r.status_code}: {r.text[:300]}")
            items = r.json().get("items", [])
            return {
                "total": r.json().get("total_count", 0),
                "repos": [
                    {
                        "full_name": i["full_name"],
                        "description": i.get("description", ""),
                        "stars": i.get("stargazers_count", 0),
                        "language": i.get("language", ""),
                        "url": i["html_url"],
                        "updated_at": i.get("updated_at", ""),
                    }
                    for i in items
                ],
            }

        # ── get_repo ───────────────────────────────────────────────────────
        if action == "get_repo":
            if not repo:
                return _err("repo (owner/repo) is required")
            r = await gh.get(f"{_GITHUB_API}/repos/{repo}")
            if r.status_code == 404:
                return _err(f"Repo not found: {repo}")
            if r.status_code != 200:
                return _err(f"GitHub API error {r.status_code}: {r.text[:300]}")
            d = r.json()
            return {
                "full_name": d["full_name"],
                "description": d.get("description", ""),
                "stars": d.get("stargazers_count", 0),
                "forks": d.get("forks_count", 0),
                "open_issues": d.get("open_issues_count", 0),
                "language": d.get("language", ""),
                "topics": d.get("topics", []),
                "default_branch": d.get("default_branch", "main"),
                "license": (d.get("license") or {}).get("name", ""),
                "url": d["html_url"],
                "created_at": d.get("created_at", ""),
                "updated_at": d.get("updated_at", ""),
            }

        # ── list_issues ────────────────────────────────────────────────────
        if action == "list_issues":
            if not repo:
                return _err("repo (owner/repo) is required")
            params: dict[str, Any] = {
                "state": state,
                "per_page": min(limit, 50),
            }
            if labels:
                params["labels"] = labels
            r = await gh.get(f"{_GITHUB_API}/repos/{repo}/issues", params=params)
            if r.status_code != 200:
                return _err(f"GitHub API error {r.status_code}: {r.text[:300]}")
            issues = [i for i in r.json() if "pull_request" not in i]  # exclude PRs
            return {
                "repo": repo,
                "state": state,
                "count": len(issues),
                "issues": [
                    {
                        "number": i["number"],
                        "title": i["title"],
                        "state": i["state"],
                        "labels": [l["name"] for l in i.get("labels", [])],
                        "author": i["user"]["login"],
                        "comments": i.get("comments", 0),
                        "created_at": i.get("created_at", ""),
                        "url": i["html_url"],
                    }
                    for i in issues
                ],
            }

        # ── get_issue ──────────────────────────────────────────────────────
        if action == "get_issue":
            if not repo or not issue_number:
                return _err("repo and issue_number are required")
            r = await gh.get(f"{_GITHUB_API}/repos/{repo}/issues/{issue_number}")
            if r.status_code == 404:
                return _err(f"Issue #{issue_number} not found in {repo}")
            if r.status_code != 200:
                return _err(f"GitHub API error {r.status_code}: {r.text[:300]}")
            d = r.json()
            # Fetch first page of comments
            cr = await gh.get(
                f"{_GITHUB_API}/repos/{repo}/issues/{issue_number}/comments",
                params={"per_page": 10},
            )
            comments = []
            if cr.status_code == 200:
                comments = [
                    {"author": c["user"]["login"], "body": c["body"][:500]}
                    for c in cr.json()
                ]
            return {
                "number": d["number"],
                "title": d["title"],
                "state": d["state"],
                "author": d["user"]["login"],
                "labels": [l["name"] for l in d.get("labels", [])],
                "body": (d.get("body") or "")[:1500],
                "comments_count": d.get("comments", 0),
                "comments": comments,
                "created_at": d.get("created_at", ""),
                "url": d["html_url"],
            }

        # ── create_issue ───────────────────────────────────────────────────
        if action == "create_issue":
            if not repo or not title:
                return _err("repo and title are required")
            payload: dict[str, Any] = {"title": title}
            if body:
                payload["body"] = body
            if labels:
                payload["labels"] = [l.strip() for l in labels.split(",") if l.strip()]
            r = await gh.post(f"{_GITHUB_API}/repos/{repo}/issues", json=payload)
            if r.status_code not in (200, 201):
                return _err(f"GitHub API error {r.status_code}: {r.text[:300]}")
            d = r.json()
            return {
                "created": True,
                "number": d["number"],
                "title": d["title"],
                "url": d["html_url"],
            }

        # ── comment_issue ──────────────────────────────────────────────────
        if action == "comment_issue":
            if not repo or not issue_number or not body:
                return _err("repo, issue_number, and body are required")
            r = await gh.post(
                f"{_GITHUB_API}/repos/{repo}/issues/{issue_number}/comments",
                json={"body": body},
            )
            if r.status_code not in (200, 201):
                return _err(f"GitHub API error {r.status_code}: {r.text[:300]}")
            d = r.json()
            return {"commented": True, "url": d["html_url"]}

        # ── list_prs ───────────────────────────────────────────────────────
        if action == "list_prs":
            if not repo:
                return _err("repo (owner/repo) is required")
            r = await gh.get(
                f"{_GITHUB_API}/repos/{repo}/pulls",
                params={"state": state, "per_page": min(limit, 50)},
            )
            if r.status_code != 200:
                return _err(f"GitHub API error {r.status_code}: {r.text[:300]}")
            return {
                "repo": repo,
                "state": state,
                "prs": [
                    {
                        "number": p["number"],
                        "title": p["title"],
                        "state": p["state"],
                        "author": p["user"]["login"],
                        "base": p["base"]["ref"],
                        "head": p["head"]["ref"],
                        "draft": p.get("draft", False),
                        "created_at": p.get("created_at", ""),
                        "url": p["html_url"],
                    }
                    for p in r.json()
                ],
            }

        # ── get_pr ─────────────────────────────────────────────────────────
        if action == "get_pr":
            if not repo or not pr_number:
                return _err("repo and pr_number are required")
            r = await gh.get(f"{_GITHUB_API}/repos/{repo}/pulls/{pr_number}")
            if r.status_code == 404:
                return _err(f"PR #{pr_number} not found in {repo}")
            if r.status_code != 200:
                return _err(f"GitHub API error {r.status_code}: {r.text[:300]}")
            d = r.json()
            return {
                "number": d["number"],
                "title": d["title"],
                "state": d["state"],
                "author": d["user"]["login"],
                "base": d["base"]["ref"],
                "head": d["head"]["ref"],
                "draft": d.get("draft", False),
                "mergeable": d.get("mergeable"),
                "additions": d.get("additions", 0),
                "deletions": d.get("deletions", 0),
                "changed_files": d.get("changed_files", 0),
                "body": (d.get("body") or "")[:1000],
                "created_at": d.get("created_at", ""),
                "url": d["html_url"],
            }

        # ── get_file ───────────────────────────────────────────────────────
        if action == "get_file":
            if not repo or not path:
                return _err("repo and path are required")
            params = {}
            if branch:
                params["ref"] = branch
            r = await gh.get(
                f"{_GITHUB_API}/repos/{repo}/contents/{path.lstrip('/')}",
                params=params,
            )
            if r.status_code == 404:
                return _err(f"File not found: {path} in {repo}")
            if r.status_code != 200:
                return _err(f"GitHub API error {r.status_code}: {r.text[:300]}")
            d = r.json()
            if isinstance(d, list):
                return {
                    "type": "directory",
                    "path": path,
                    "entries": [{"name": e["name"], "type": e["type"]} for e in d],
                }
            import base64

            try:
                content = base64.b64decode(d.get("content", "")).decode(
                    "utf-8", errors="replace"
                )
            except Exception:
                content = "(binary file — cannot display)"
            return {
                "path": d["path"],
                "size": d.get("size", 0),
                "sha": d.get("sha", ""),
                "content": content[:4000],
                "truncated": len(content) > 4000,
                "url": d["html_url"],
            }

        # ── list_commits ───────────────────────────────────────────────────
        if action == "list_commits":
            if not repo:
                return _err("repo (owner/repo) is required")
            params = {"per_page": min(limit, 30)}
            if branch:
                params["sha"] = branch
            r = await gh.get(f"{_GITHUB_API}/repos/{repo}/commits", params=params)
            if r.status_code != 200:
                return _err(f"GitHub API error {r.status_code}: {r.text[:300]}")
            return {
                "repo": repo,
                "branch": branch or "default",
                "commits": [
                    {
                        "sha": c["sha"][:8],
                        "message": c["commit"]["message"].split("\n")[0][:120],
                        "author": c["commit"]["author"]["name"],
                        "date": c["commit"]["author"]["date"],
                        "url": c["html_url"],
                    }
                    for c in r.json()
                ],
            }

        # ── get_user ───────────────────────────────────────────────────────
        if action == "get_user":
            target = username or "me"
            endpoint = (
                f"{_GITHUB_API}/user"
                if target == "me"
                else f"{_GITHUB_API}/users/{target}"
            )
            r = await gh.get(endpoint)
            if r.status_code == 404:
                return _err(f"User not found: {target}")
            if r.status_code != 200:
                return _err(f"GitHub API error {r.status_code}: {r.text[:300]}")
            d = r.json()
            return {
                "login": d["login"],
                "name": d.get("name", ""),
                "bio": d.get("bio", ""),
                "company": d.get("company", ""),
                "location": d.get("location", ""),
                "public_repos": d.get("public_repos", 0),
                "followers": d.get("followers", 0),
                "url": d["html_url"],
            }

        return _err(
            f"Unknown action: {action!r}. Valid actions: search_repos, get_repo, "
            "list_issues, get_issue, create_issue, comment_issue, list_prs, "
            "get_pr, get_file, list_commits, get_user"
        )
