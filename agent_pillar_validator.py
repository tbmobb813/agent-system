#!/usr/bin/env python3
"""
Compatibility entrypoint for the 8-pillar validator.

This keeps a space-free script path for local use and CI:
    python agent_pillar_validator.py --check-code
"""

from pathlib import Path
import runpy


if __name__ == "__main__":
    legacy_path = Path(__file__).with_name("python agent_pillar_validator.py")
    runpy.run_path(str(legacy_path), run_name="__main__")
