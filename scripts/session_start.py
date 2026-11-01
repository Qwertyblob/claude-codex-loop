#!/usr/bin/env python3
"""SessionStart hook: puts the codex-loop workflow rules in context for opted-in projects.

Exits 0 silently unless .codex-loop.json exists in the project root. Otherwise prints
templates/protocol.md (stdout is added to Claude's context), with ${CLAUDE_PLUGIN_ROOT}
replaced by this plugin's real path so the commands in it work from the Bash tool.
"""
import json
import os
import sys
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        payload = {}
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()).resolve()
    if not (root / ".codex-loop.json").is_file():
        return 0
    try:
        text = (PLUGIN_ROOT / "templates" / "protocol.md").read_text()
    except OSError as e:  # never crash the session
        print(f"codex-loop: could not read protocol template: {e}", file=sys.stderr)
        return 0
    try:
        cfg = json.loads((root / ".codex-loop.json").read_text())
    except (OSError, ValueError):
        cfg = {}
    mode = cfg.get("ask_mode", "interrupt") if isinstance(cfg, dict) else "interrupt"
    if mode not in ("interrupt", "defer"):
        mode = f'interrupt (the configured value {mode!r} is not valid; use "interrupt" or "defer")'
    print(text.replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN_ROOT)))
    print(f"\n**This project's ask_mode: {mode}.**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
