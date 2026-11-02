#!/usr/bin/env python3
"""UserPromptSubmit / PostToolUse(AskUserQuestion) hook: records the user's own words for Codex.

In opted-in projects, appends every prompt the user submits, and every answer they give to one of
Claude's AskUserQuestion questions, verbatim (secrets redacted) to .reviews/prompts.jsonl. The review
hook puts them in every Codex prompt, so Codex checks the plan and code against what the user actually
said, not only against Claude's own account of it in the plan's Assignment.

Never blocks and prints nothing: UserPromptSubmit output would be added to Claude's context.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codex_review import PROMPT_LOG, now_iso, redact  # noqa: E402

MAX_ENTRY_CHARS = 20_000


def answer_text(payload: dict) -> str:
    """The questions Claude asked and the user's answers, as plain text."""
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    response = payload.get("tool_response")
    answers, notes = None, {}
    for src in (response, tool_input):
        if isinstance(src, dict) and isinstance(src.get("answers"), dict) and src["answers"]:
            answers = src["answers"]
            if isinstance(src.get("annotations"), dict):
                notes = src["annotations"]
            break
    if answers:
        lines = []
        for q, a in answers.items():
            lines.append(f"Q: {q}\nA: {a}")
            note = notes.get(q, {}).get("notes") if isinstance(notes.get(q), dict) else None
            if note:
                lines.append(f"Note: {note}")
        return "\n".join(lines)
    questions = [q.get("question", "") for q in tool_input.get("questions", []) if isinstance(q, dict)]
    if not questions or response in (None, "", {}, []):
        return ""
    shown = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
    return "\n".join(f"Q: {q}" for q in questions) + f"\nA: {shown}"


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()).resolve()
    if not (root / ".codex-loop.json").is_file():
        return 0
    event = payload.get("hook_event_name")
    if event == "UserPromptSubmit":
        kind, text = "prompt", payload.get("prompt")
        if isinstance(text, str) and text.lstrip().startswith("/codex-loop:"):
            return 0  # the plugin's own commands say nothing about the work
    elif event == "PostToolUse" and payload.get("tool_name") == "AskUserQuestion":
        kind, text = "answer", answer_text(payload)
    else:
        return 0
    if not isinstance(text, str) or not text.strip():
        return 0
    text = text.strip()
    if len(text) > MAX_ENTRY_CHARS:
        text = text[:MAX_ENTRY_CHARS] + f"\n[... {len(text) - MAX_ENTRY_CHARS} more characters not recorded]"
    entry = {"at": now_iso(), "ts": time.time(), "session": str(payload.get("session_id") or ""),
             "kind": kind, "text": redact(text)}
    try:
        path = root / PROMPT_LOG
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:  # never get in the user's way
        print(f"codex-loop: could not record the prompt for Codex: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 - a logging hook must never break the session
        print(f"codex-loop: prompt log failed: {e}", file=sys.stderr)
        sys.exit(0)
