#!/usr/bin/env python3
"""Notification hook: macOS notification when Claude is waiting for the user's input.

Exits 0 silently unless .codex-loop.json exists in the project root. Uses the same
notify() as the review hook (osascript; CODEX_REVIEW_NOTIFY_LOG / CODEX_REVIEW_NOTIFY=0
for tests), so it never fails the session.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codex_review import notify, opted_in  # noqa: E402

WAITING_TYPES = {"permission_prompt", "idle_prompt", "elicitation_dialog", "elicitation_url_dialog",
                 "agent_needs_input"}


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        payload = {}
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()).resolve()
    if not opted_in(root) or payload.get("notification_type") not in WAITING_TYPES:
        return 0
    message = payload.get("message") or "Claude is waiting for your input"
    notify(f"Claude Code: {root.name}", message[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
