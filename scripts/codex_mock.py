#!/usr/bin/env python3
"""Stand-in for the codex CLI, used by codex_review.py when CODEX_REVIEW_MOCK=1.

Accepts the same arguments the hook passes to codex, reads the prompt from stdin,
and writes a canned review to the -o file and stdout.

  CODEX_REVIEW_MOCK_SCENARIOS  comma list, one scenario per round (last one repeats),
                               e.g. "blocker,approved". Default: approved.
  CODEX_REVIEW_MOCK_LOG        optional JSONL file recording each call (argv, cwd,
                               prompt, staged files, diff, canary hits) for tests.
  CODEX_REVIEW_MOCK_CANARY     optional string; files in cwd containing it are logged.
  CODEX_REVIEW_MOCK_IGNORE_DECISIONS=1  re-raise findings even when the prompt's owner decisions
                               cover them (a non-compliant reviewer). By default the mock, like a
                               compliant reviewer, drops findings that re-raise a recorded title (Refs-only verification findings stay).
  CODEX_REVIEW_ROUND           set by the hook.
"""
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

SCENARIOS = {
    "approved": """No blocking issues. The work matches the assignment.

VERDICT: APPROVED""",

    "blocker": """### F1 [BLOCKER] Phase 2 deletes rows with no backup or rollback step
Status: NEW
Refs: -
Evidence: Phase 2 says "drop the legacy table" but no phase creates a backup or a down-migration.
Recommendation: Add a backup + reversible migration step before the drop.

### F2 [NIT] Phase titles are inconsistent
Status: NEW
Refs: -
Evidence: "Phase 1: Setup" vs "phase two - parser".
Recommendation: Use one style.

VERDICT: CHANGES_REQUESTED""",

    # A false claim: the fixture repo does define parse_config in src/config.py.
    "rejectable": """### F1 [MAJOR] Plan relies on parse_config(), which does not exist
Status: NEW
Refs: -
Evidence: Phase 1 calls parse_config() but I believe no such function is defined in src/config.py.
Recommendation: Add a phase that implements parse_config() first.

VERDICT: CHANGES_REQUESTED""",

    "concede": """### F1 [MAJOR] Plan relies on parse_config(), which does not exist
Status: CONCEDED
Refs: R1-F1
Evidence: Claude's response cites src/config.py:1 where parse_config is defined; I verified it. Withdrawn.
Recommendation: None.

VERDICT: APPROVED""",

    "maintain": """### F1 [BLOCKER] Phase 2 deletes rows with no backup or rollback step
Status: MAINTAINED
Refs: R1-F1
Evidence: The revised plan still has no down-migration.
New evidence: Section "Phase 2" step 3 runs the drop before the backup in step 4, so the backup is too late.
Recommendation: Reorder: backup, verify, then drop.

VERDICT: CHANGES_REQUESTED""",

    "repeat": """### F1 [BLOCKER] Phase 2 deletes rows with no backup or rollback step
Status: MAINTAINED
Refs: R1-F1
Evidence: As stated before, there is no rollback.
New evidence: none
Recommendation: Add a rollback.

VERDICT: CHANGES_REQUESTED""",

    "minor_only": """### F1 [MINOR] Consider naming the CLI flag --dry-run
Status: NEW
Refs: -
Evidence: Phase 3 calls it --preview, which is less conventional.
Recommendation: Rename.

VERDICT: CHANGES_REQUESTED""",

    "leaky": """### F1 [MAJOR] Hard-coded credential in config
Status: NEW
Refs: -
Evidence: src/settings.py:1 contains OPENAI_KEY = "sk-LEAKEDleaked1234567890abcd" and DB_PASSWORD=hunter2hunter2.
Recommendation: Load from the environment.

VERDICT: CHANGES_REQUESTED""",

    "garbage": "Sorry, I could not finish the review.",

    "secret_title": """### F1 [MAJOR] Leaked key sk-TITLEsecret1234567890abcd in config
Status: NEW
Refs: -
Evidence: src/settings.py:1.
Recommendation: Rotate it.

VERDICT: CHANGES_REQUESTED""",

    # Re-raises the disputed blocker as NEW, without refs or new evidence.
    "renew": """### F1 [BLOCKER] Phase 2 deletes rows with no backup or rollback step
Status: NEW
Refs: -
Evidence: There is still no rollback.
Recommendation: Add a rollback.

VERDICT: CHANGES_REQUESTED""",

    "bad_format": """### BLOCKER: Still broken
Evidence: the migration still drops the table first.

VERDICT: CHANGES_REQUESTED""",

    # A valid MINOR followed by a malformed BLOCKER inside its span.
    "mixed_format": """### F1 [MINOR] Naming
Status: NEW
Evidence: loader.py:1

- BLOCKER: loader.py:8 deletes stored records
Evidence: confirmed with an empty input

VERDICT: CHANGES_REQUESTED""",

    "mixed_format_id": """### F1 [MINOR] Naming
Status: NEW
Evidence: loader.py:1

- F2 BLOCKER: loader.py:8 deletes stored records
Evidence: confirmed with empty input

VERDICT: CHANGES_REQUESTED""",

    # Two tradeoffs that depend on the owner's priorities, not on verifiable facts.
    "preference": """### F1 [MAJOR] Store settings in TOML instead of JSON
Status: NEW
Refs: -
Evidence: Phase 1 picks JSON; TOML allows comments, which operators usually want.
Recommendation: Use TOML.

### F2 [MAJOR] Fail fast on unknown config keys instead of ignoring them
Status: NEW
Refs: -
Evidence: Phase 1 ignores unknown keys, so typos go unnoticed.
Recommendation: Raise on unknown keys.

VERDICT: CHANGES_REQUESTED""",

    "pref_blocker": """### F1 [BLOCKER] Drop Python 3.9 support to use match statements
Status: NEW
Refs: -
Evidence: Phase 1 targets 3.9; match needs 3.10.
Recommendation: Require Python 3.10.

VERDICT: CHANGES_REQUESTED""",

    # Codex pressing both preference findings again in round 2.
    "pref_reraise": """### F1 [MAJOR] Store settings in TOML instead of JSON
Status: MAINTAINED
Refs: R1-F1
Evidence: JSON still has no comments.
New evidence: The ops runbook expects commented config files.
Recommendation: Use TOML.

### F2 [MAJOR] Fail fast on unknown config keys instead of ignoring them
Status: MAINTAINED
Refs: R1-F2
Evidence: Unknown keys are still ignored.
New evidence: A typo in "timout" would silently use the default.
Recommendation: Raise on unknown keys.

VERDICT: CHANGES_REQUESTED""",

    # Owner sided with Codex on R1-F1 but the fix is incomplete: verification, not a re-raise.
    "pref_incomplete": """### F1 [MAJOR] TOML switch from R1-F1 is incomplete: the loader still parses JSON
Status: NEW
Refs: R1-F1
Evidence: src/config.py:1 still calls json.load; no TOML parser is used.
Recommendation: Finish the switch to tomllib.

VERDICT: CHANGES_REQUESTED""",

    # `codex exec review` plain-text output as seen live: absolute workspace paths, line moves each round
    "native_text": """Direct script execution fails before argument parsing.

Full review comments:

- [P1] Make the CLI import work when executed as a script \u2014 {cwd}/src/loader.py:{line}-{line}
  Running `python3 src/loader.py` from {cwd} fails with `ModuleNotFoundError: No module named 'src'`.
""",

    # `codex review` text answering a dispute with its fields inline, as seen live
    "inline_fields": """Direct script execution remains broken.

Full review comments:

- [P1] Provide the script invocation required by the plan \u2014 {cwd}/src/loader.py:4-4
  Status: MAINTAINED; Refs: R1-F1. New evidence: the assignment specifies `loader.py <id>`, and nothing provides it.
""",

    # the same title in two different files: separate findings
    "file_a": """### F1 [MAJOR] Handle empty input \u2014 src/a.py:4-4
Status: NEW
Refs: -
Evidence: src/a.py:4 indexes rows[0] without a check.
Recommendation: Guard the empty case.

VERDICT: CHANGES_REQUESTED""",

    "file_b": """### F1 [MAJOR] Handle empty input \u2014 src/b.py:2-2
Status: NEW
Refs: -
Evidence: src/b.py:2 indexes rows[0] without a check.
Recommendation: Guard the empty case.

VERDICT: CHANGES_REQUESTED""",

    # same title, distinct paths that differ only in punctuation
    "path_dash": """### F1 [MAJOR] Handle empty input \u2014 src/config-loader.py:4-4
Status: NEW
Refs: -
Evidence: src/config-loader.py:4 indexes rows[0] without a check.
Recommendation: Guard the empty case.

VERDICT: CHANGES_REQUESTED""",

    "path_dir": """### F1 [MAJOR] Handle empty input \u2014 src/config/loader.py:2-2
Status: NEW
Refs: -
Evidence: src/config/loader.py:2 indexes rows[0] without a check.
Recommendation: Guard the empty case.

VERDICT: CHANGES_REQUESTED""",

    # `codex review` text conceding a dispute in its summary, as seen live
    "prose_concede": """R3-F1: CONCEDED\u2014the backup runs in phase 1. Mentioning R1-F1: CONCEDED here only in passing.

Review comment:

- [P2] Rename the flag \u2014 {cwd}/src/loader.py:1-1
  Status: NEW; Refs: -. The flag name is unconventional.

VERDICT: APPROVED""",

    # the same, cut off before the VERDICT line: must not pass
    "prose_concede_truncated": """R3-F1: CONCEDED\u2014the backup runs in phase 1.

Review comment:

- [P2] Rename the flag \u2014 {cwd}/src/loader.py:1-1
  Status: NEW; Refs: -. The flag name is unconventional.
""",

    # MINOR findings only, cut off before the VERDICT line: must not pass
    "minor_truncated": """### F1 [MINOR] Consider naming the CLI flag --dry-run
Status: NEW
Refs: -
Evidence: The plan calls it --test.
""",

    # a bare concession with no findings and no VERDICT line, as seen live
    "bare_concede": "R3-F1: CONCEDED - Module invocation works; both accepted fixes are adequate.",

    # contradicts itself: an open BLOCKER next to APPROVED
    "approved_with_blocker": """### F1 [BLOCKER] Data loss
Status: NEW
Refs: -
Evidence: Phase 2 drops the table first.
Recommendation: Back up first.

VERDICT: APPROVED""",

    # a blocking finding in an unrecognized form next to APPROVED
    "approved_malformed": """### F1 BLOCKER: Data loss
Evidence: src/config.py:1 deletes data without a backup.

VERDICT: APPROVED""",

    "native_clean": json.dumps({"findings": [], "overall_correctness": "patch is correct",
                                "overall_explanation": "No actionable issues found.",
                                "overall_confidence_score": 0.99}),

    "native_blocking": json.dumps({
        "findings": [{"title": "[P1] Off-by-one in loader", "body": "Loop skips the last line.", "priority": 1,
                      "confidence_score": 0.8,
                      "code_location": {"absolute_file_path": "/x/src/loader.py", "line_range": {"start": 3, "end": 3}}}],
        "overall_correctness": "patch is incorrect", "overall_explanation": "One bug.",
        "overall_confidence_score": 0.8}),
}


def drop_decided(text, prompt):
    """Act like a compliant reviewer: leave out findings the owner already decided."""
    m = re.search(r"^## Owner decisions[^\n]*\n(.*?)(?=^## (?!plan |phase-|DECISION|ASSUMPTION)|\Z)", prompt, re.M | re.S)
    if not m:
        return text
    decided = m.group(1)
    titles = {t.strip().lower() for t in re.findall(r"^##[^\n]*?(?:DECISION|ASSUMPTION)[ \t]*(?:\[[A-Z]+\])?[ \t]*(.*)$",
                                                     decided, re.M)}
    blocks = re.split(r"(?=^### F\d+ )", text.split("VERDICT:")[0], flags=re.M)
    kept = [b for b in blocks if b.strip() and not (
        re.match(r"### F\d+ \[\w+\] (.*)", b) and re.match(r"### F\d+ \[\w+\] (.*)", b).group(1).strip().lower() in titles)]
    if len(kept) == len([b for b in blocks if b.strip()]):
        return text
    blocking = any(re.match(r"### F\d+ \[(BLOCKER|MAJOR)\]", b) for b in kept)
    return "".join(kept) + ("VERDICT: CHANGES_REQUESTED" if blocking else "No remaining issues.\n\nVERDICT: APPROVED")


def log_call(argv, prompt, rnd, scenario):
    log = os.environ.get("CODEX_REVIEW_MOCK_LOG")
    if not log:
        return
    cwd = Path.cwd()
    staged = sorted(p.relative_to(cwd).as_posix() for p in cwd.rglob("*")
                    if p.is_file() and ".git" not in p.relative_to(cwd).parts)
    canary = os.environ.get("CODEX_REVIEW_MOCK_CANARY")
    contents = {s: (cwd / s).read_text(errors="ignore") for s in staged if (cwd / s).stat().st_size < 20_000}
    hits = [s for s in staged if canary in (cwd / s).read_text(errors="ignore")] if canary else []
    diff = ""
    if (cwd / ".git").exists():
        diff = subprocess.run(["git", "diff", "HEAD", "--name-status"], cwd=cwd,
                              capture_output=True, text=True).stdout
    with open(log, "a") as f:
        f.write(json.dumps({"round": rnd, "scenario": scenario, "argv": argv, "cwd": str(cwd),
                            "prompt": prompt, "staged": staged, "contents": contents, "canary_hits": hits,
                            "diff": diff, "env_keys": sorted(os.environ)}) + "\n")


def emit(argv, text):
    """Print Codex's answer like the real CLI: plain text, or `--json` events (session start, answer, token usage)."""
    if "--json" not in argv:
        print(text)
        return
    print(json.dumps({"type": "thread.started", "thread_id": str(uuid.uuid4())}))
    print(json.dumps({"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": text}}))
    print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": len(text), "output_tokens": len(text)}}))


def main():
    argv = sys.argv[1:]
    out_file = argv[argv.index("-o") + 1] if "-o" in argv else None
    prompt = sys.stdin.read() if argv and argv[-1] == "-" else ""
    rnd = int(os.environ.get("CODEX_REVIEW_ROUND", "1"))
    names = [s.strip() for s in os.environ.get("CODEX_REVIEW_MOCK_SCENARIOS", "approved").split(",") if s.strip()]
    scenario = names[min(rnd, len(names)) - 1]
    log_call(argv, prompt, rnd, scenario)

    if scenario == "error":
        print("mock codex: simulated API failure (HTTP 500)", file=sys.stderr)
        return 3
    if scenario == "quota":
        print("ERROR: You hit your spend cap set by the owner of your workspace.", file=sys.stderr)
        return 1
    if scenario == "timeout":
        time.sleep(120)
        return 0
    if scenario == "concede_disputes":  # explicitly concede every outstanding dispute, then approve
        section = prompt.split("## Outstanding disputes", 1)[-1].split("\n## ", 1)[0] if "## Outstanding disputes" in prompt else ""
        keys = list(dict.fromkeys(re.findall(r"^- (R\d+-F\d+) \[", section, re.M)))
        text = "".join(f"{k}: CONCEDED - Claude's evidence holds; verified.\n" for k in keys) + "\nVERDICT: APPROVED"
        if out_file:
            Path(out_file).write_text(text)
        emit(argv, text)
        return 0
    text = SCENARIOS[scenario].replace("{cwd}", str(Path.cwd())).replace("{line}", str(rnd + 3))
    if os.environ.get("CODEX_REVIEW_MOCK_IGNORE_DECISIONS") != "1" and not text.lstrip().startswith("{"):
        text = drop_decided(text, prompt)
    if out_file:
        Path(out_file).write_text(text)
    emit(argv, text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
