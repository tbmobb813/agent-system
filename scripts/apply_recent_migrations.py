#!/usr/bin/env python3
"""
Apply selected SQL migrations using DATABASE_URL (same as backend).

Use when `supabase db push` is unavailable or the linked CLI is not installed:

  cd backend && source venv/bin/activate && export $(grep -v '^#' .env | xargs)
  python3 ../scripts/apply_recent_migrations.py

Or from repo root with backend venv activated:

  python3 scripts/apply_recent_migrations.py

Requires: pip install asyncpg python-dotenv (already in backend/requirements.txt)

Supabase hosted DB must be reachable; pooler errors usually mean wrong URL,
paused project, or invalid credentials — fix DATABASE_URL first.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

MIGRATIONS_DEFAULT = [
    REPO / "supabase/migrations/016_scheduled_tasks.sql",
    REPO / "supabase/migrations/017_latency_metrics.sql",
    REPO / "supabase/migrations/018_projects.sql",
]


def main() -> None:
    try:
        import asyncpg
        from dotenv import load_dotenv
    except ImportError as e:
        print("Missing dependency:", e, file=sys.stderr)
        print("Run: pip install asyncpg python-dotenv", file=sys.stderr)
        sys.exit(1)

    env_path = REPO / "backend" / ".env"
    if env_path.is_file():
        load_dotenv(env_path)

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL not set (try backend/.env)", file=sys.stderr)
        sys.exit(1)

    async def run() -> None:
        conn = await asyncpg.connect(url)
        try:
            for path in MIGRATIONS_DEFAULT:
                if not path.is_file():
                    print(f"Skip missing: {path}", file=sys.stderr)
                    continue
                sql = path.read_text(encoding="utf-8")
                await conn.execute(sql)
                print(f"Applied {path.name}")
        finally:
            await conn.close()

    asyncio.run(run())


if __name__ == "__main__":
    main()
