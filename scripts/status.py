#!/usr/bin/env python3
"""Print codex-loop review status from .reviews/ (used by /codex-loop:status)."""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codex_review import CodexError, decisions_path, gate_check, project_root, review_settings  # noqa: E402


def main() -> int:
    root = project_root()
    if not (root / ".codex-loop.json").is_file():
        print(f"codex-loop is not enabled in {root} (run /codex-loop:init).")
        return 0
    reviews = root / ".reviews"
    try:
        state = json.loads((reviews / "state.json").read_text())
    except (OSError, ValueError):
        print("No reviews yet (.reviews/state.json not found).")
        return 0
    stages = state.get("stages", {})
    if not stages:
        print("No reviews yet.")
        return 0
    last = lambda st: (st.get("history") or [{}])[-1].get("at", "")
    key, st = max(stages.items(), key=lambda kv: last(kv[1]))
    pid, stage = key.rsplit("/", 1)
    rnd = st.get("rounds_done", 0)
    verdict = "(unknown)"
    findings = reviews / pid / stage / f"round-{rnd}-findings.md"
    if findings.exists():
        m = re.search(r"^- Verdict: (.+?);", findings.read_text(), re.M)
        verdict = m.group(1) if m else verdict
    entry = (st.get("history") or [{}])[-1]
    print(f"Plan:    docs/plans/{pid}.md")
    print(f"Stage:   {stage}")
    start = st.get("cycle_start", 1)
    if start > rnd:  # a new cycle was requested, but none of its rounds has completed (e.g. Codex failed)
        print(f"Round:   {rnd} (a new review cycle was requested; its first round, {start}, has not run yet)")
    else:
        print(f"Round:   {rnd} (cycle started at round {start})")
    pending = st.get("owner_pending")
    if pending:
        print(f"Status:  WAITING_FOR_OWNER since {pending.get('at', '?')} (before round {pending.get('round', 0) + 1})")
    else:
        print(f"Status:  {entry.get('status', st.get('status', '?'))} at {entry.get('at', '?')}")
    print(f"Verdict: {verdict}")
    try:
        cfg = json.loads((root / ".codex-loop.json").read_text())
    except (OSError, ValueError):
        cfg = {}
    print(f"Ask mode: {cfg.get('ask_mode', 'interrupt') if isinstance(cfg, dict) else 'interrupt'}")
    for kind in ("plan", "code"):
        try:
            rs = review_settings(root, kind)
            print(f"Codex ({kind}): model {rs.get('model', 'Codex default')}, effort {rs.get('effort', 'Codex default')}")
        except CodexError as e:
            print(f"Codex ({kind}): INVALID: {e}")
    dec = root / "docs" / "plans" / f"{pid}-decisions.md"
    if dec.is_file():
        text = dec.read_text(errors="replace")
        heads = [h for h in re.findall(r"^##[ \t]+(.*\b(DECISION|OVERRIDE|ASSUMPTION)\b.*)$", text, re.M)
                 if "[GATE]" not in h[0]]  # owner-approved phase starts are not review decisions
        print(f"\nOwner decisions ({dec.relative_to(root)}): "
              f"{sum(k != 'ASSUMPTION' for _, k in heads)} decided, {sum(k == 'ASSUMPTION' for _, k in heads)} "
              "assumption(s) awaiting confirmation")
        for h, k in heads:
            if k == "ASSUMPTION":
                print(f"  {h.strip()}")
    if state.get("pending_limit", {}).get("key") == key:
        print("Note:    round limit reached; extension allowed only with an accepted BLOCKER/MAJOR")
    if pending:
        print("\nOwner questions waiting for your answer:")
        for q in pending.get("questions", []):
            print(f"  {q['key']} [{q['severity']}] [{q['cls']}] {q['title']}")
        if not pending.get("questions"):
            print("  none")
        for a in pending.get("assumptions", []):
            print(f"  (assumption for Claude to log) {a['key']} [{a['severity']}] {a['title']}")
    latest = reviews / "latest.md"
    rows = dict(re.findall(r"^\| (\w[\w /]*?) \| (.*?) \|$", latest.read_text(), re.M)) if latest.exists() else {}
    if rows.get("Status") == "ERROR":
        print(f"Last attempt: ERROR at {rows.get('Updated', '?')} ({rows.get('Stage', '?')}): "
              f"{rows.get('Error', '?')} (see .reviews/errors.log)")
    nxt = 1 if stage == "plan" else int(stage.split("-")[1]) + 1
    problems = gate_check(root, state, pid, nxt)
    dec = decisions_path(root, pid)
    approvals = re.findall(rf"^## DECISION \[GATE\] Start phase {nxt} with open gate items$(?:\n- .*)*?"
                           r"\n- Approved by the owner: (.+)$", dec.read_text() if dec.is_file() else "", re.M)
    if problems and approvals:  # phase-start --owner-approved: started, but the items are still open
        print(f"Gate:    phase {nxt} started with the owner's approval ({approvals[-1].strip()}); still open:")
        for problem in problems:
            print(f"  - {problem}")
    for problem in [] if approvals else problems:
        print(f"Gate:    phase {nxt} blocked: {problem}")
    print("\nUnresolved disputes:")
    any_open = False
    for k, s in stages.items():
        for dk, d in (s.get("disputes") or {}).items():
            any_open = True
            print(f"  {k} {dk} [{d.get('severity')}] {d.get('title')} (Claude: {d.get('decision')})")
    if not any_open:
        print("  none")
    others = [k for k in stages if k != key]
    if others:
        print("\nOther stages: " + ", ".join(f"{k} ({stages[k].get('status')})" for k in others))
    return 0


if __name__ == "__main__":
    sys.exit(main())
