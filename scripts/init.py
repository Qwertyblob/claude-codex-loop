#!/usr/bin/env python3
"""Opt the current project into codex-loop (used by /codex-loop:init).

Checks that git is installed (a repository is optional) and codex login, runs the mock test suite,
and only if all of that passes creates .codex-loop.json, docs/plans/ and the .reviews/ .gitignore entry. Safe to re-run.
CODEX_LOOP_TEST_SCRIPT overrides the suite (used by the tests).
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUITE_TIMEOUT = 300  # the suite takes about a minute; fail clearly instead of hanging


def check(label, ok, detail):
    print(f"[{'ok' if ok else 'FAIL'}] {label}: {detail}")
    return ok


def run(cmd, cwd):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def main() -> int:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
    print(f"Project: {root}\n")

    # The git program is needed (each review builds a throwaway repo); a repository is not.
    if shutil.which("git"):
        git_ok = True
        code, out = run(["git", "rev-parse", "--show-toplevel"], root)
        check("git", True, out if code == 0 else
              "not a repository; phase diffs will use file snapshots in .reviews/ (no git init needed)")
    else:
        git_ok = check("git", False, "git not found on PATH (install it, e.g. `xcode-select --install` or "
                                     "your package manager; no repository is needed)")
    codex = shutil.which("codex")
    if codex:
        code, out = run([codex, "login", "status"], root)
        codex_ok = check("codex login", code == 0, out.splitlines()[-1] if out else f"exit {code}")
    else:
        codex_ok = check("codex login", False, "codex CLI not found on PATH (npm i -g @openai/codex)")
    if not (git_ok and codex_ok):
        print("\nNot opted in: fix the failed checks above and run /codex-loop:init again.")
        return 1

    # Run the suite before anything is created, so a failed setup never leaves the project opted in.
    print("\nRunning the mock test suite...")
    suite = os.environ.get("CODEX_LOOP_TEST_SCRIPT") or str(HERE / "test_codex_review.py")
    try:
        p = subprocess.run([sys.executable, suite], capture_output=True, text=True, timeout=SUITE_TIMEOUT,
                           env={k: v for k, v in os.environ.items() if k != "CODEX_LOOP_LIVE_TEST"})
    except subprocess.TimeoutExpired:
        print(f"\nThe test suite did not finish within {SUITE_TIMEOUT}s. Nothing was changed"
              + (" (the existing .codex-loop.json was kept)." if (root / ".codex-loop.json").exists() else
                 "; the project is NOT opted in."))
        return 1
    tail = (p.stderr or p.stdout).strip().splitlines()
    print("\n".join(tail[-3:]) if p.returncode == 0 else (p.stderr or p.stdout))
    if p.returncode != 0:
        print("\nThe test suite FAILED (see above). Nothing was changed"
              + (" (the existing .codex-loop.json was kept)." if (root / ".codex-loop.json").exists() else
                 "; the project is NOT opted in."))
        return 1

    cfg = root / ".codex-loop.json"
    if cfg.exists():
        print(f"\n[keep] {cfg.name} already exists")
    else:
        cfg.write_text(json.dumps({"version": 1, "ask_mode": "interrupt"}, indent=2) + "\n")
        print(f"\n[new]  {cfg.name}")
    plans = root / "docs" / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    keep = plans / ".gitkeep"
    if not any(plans.iterdir()):
        keep.touch()
    print("[ok]   docs/plans/")
    gi = root / ".gitignore"
    lines = gi.read_text().splitlines() if gi.exists() else []
    if any(l.strip() in (".reviews", ".reviews/", "/.reviews", "/.reviews/") for l in lines):
        print("[keep] .gitignore already ignores .reviews/")
    else:
        text = gi.read_text() if gi.exists() else ""
        gi.write_text(text + ("" if not text or text.endswith("\n") else "\n") + ".reviews/\n")
        print("[new]  .gitignore entry: .reviews/")
    print("\ncodex-loop is set up. Start a new session (or /clear) so the SessionStart hook loads the protocol.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
