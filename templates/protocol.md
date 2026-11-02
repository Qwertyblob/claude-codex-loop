# Workflow: plan → review → code, with Codex as reviewer

This project uses the codex-loop plugin (opted in via `.codex-loop.json`). Its Stop hook runs an OpenAI Codex
review whenever `.reviews/ready.json` changes, then hands you the findings with exact instructions for the next
step: follow them. Codex reviews a sanitized, read-only copy of the repo; you are the only one who edits files.
A hook also records the user's prompts and AskUserQuestion answers in `.reviews/prompts.jsonl` (never edit it),
and Codex checks your work against those words, not only against your plan's Assignment.

## 1. Planning

- For a feature request, write the plan to `docs/plans/YYYY-MM-DD-<slug>.md` (today's date, kebab-case slug).
  No code until the user approves the final plan.
- The plan has `## Assignment` (the user's request quoted verbatim, plus later messages that change it and
  answers to your clarifying questions), `## Phases` (`### Phase N: ...`, each independently implementable,
  reviewable and testable: files, approach, tests), and risks and open questions.
- Put guidance about secrets under a heading (`### Secret handling`), never nested under a `- Secrets:` bullet:
  anything nested under a credential-like key is redacted before Codex sees it.
- When the draft is complete, request a review (section 4) with `"type": "plan"`. If you stop with an unreviewed
  plan, the hook reminds you once per version; ignore that while it is still a draft.
- If the user says a plan or phase should not be reviewed, don't request one: record
  `## DECISION [SKIP] No Codex review for plan` (or `phase-N`) in the decisions file (section 6) and tell them.

## 2. Coding (only after the user approves the plan)

- One phase at a time. Before writing any code for phase N, record its diff base:
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_review.py" phase-start docs/plans/<plan>.md N`
  A code review without it fails. When resuming a phase (after `/clear` or in a new session), don't run it again.
  Use `--reset` only when the user wants the phase's diff to start over.
- When the phase is complete and its tests pass, request a review with `"type": "code"`, `"phase": N`.
- After consensus, summarize for the user and wait for their go-ahead before phase N+1 (the phase gate).
- If `phase-start` refuses (changes made after the last review, open deadlock items, unconfirmed assumptions),
  show the user what it lists; they choose. Use `--owner-approved` only on their explicit say-so.
- Codex never sees withheld files (secrets, data, unsupported types). When the hook lists changed files Codex did
  not review, tell the user and check them yourself.

## 3. Never trigger on work in progress

Write `.reviews/ready.json` only when a plan draft or a whole phase is ready, never mid-task or to "check" work.

## 4. Requesting a review

Write `.reviews/ready.json`, then end your turn (a review takes up to ~15 min):

```json
{"type": "plan", "plan_path": "docs/plans/2026-10-27-example.md", "phase": null, "round": 1}
{"type": "code", "plan_path": "docs/plans/2026-10-27-example.md", "phase": 2, "round": 1}
```

Optional: `"base"` (a git ref to diff a code review against instead of the phase-start base) and `"attempt"`
(increment it to retry after an error, only when the user asks).

## 5. Each round

- Evaluate every finding on its merits: verify the claim against the actual code or plan (open the file, check the
  line, run the test). Do not defer to Codex by default, and do not reject by default.
- Write the response file the hook names, answering every BLOCKER/MAJOR finding with a heading like
  `### F1: REJECT [FACT]` and the evidence you checked; apply only what you accept; write `ready.json` exactly as
  the hook says.
- On consensus, deadlock, owner questions or an error, do exactly what the hook's message says. Never retry a
  failed review on your own.

## 6. Owner input

Tag every REJECT/PARTIAL with its class (untagged means `[FACT]`):

- `[FACT]`: verifiable in the code or plan. Settle it yourself with evidence; never ask the user about facts.
- `[PREFERENCE]`: a tradeoff that depends on the owner's priorities. The owner decides on BLOCKER/MAJOR;
  MINOR/NIT is your call.
- `[SCOPE]`: on any finding you would ACCEPT or PARTIAL whose change goes beyond the approved plan. **Never apply
  a scope expansion without asking the user first**, in any mode, including MINOR/NIT fixes after consensus.
- `[INTENT]`: on an `Intent:` finding (Codex says you misread the user) that you dispute. Only the user knows what
  they meant, so it always goes to them. If Codex is plainly right, just ACCEPT.

The hook batches owner questions into one block: ask them all in one message and record each answer in
`docs/plans/<plan-file-name>-decisions.md` under the heading it gives. Codex treats that file as final
requirements. Decisions the user volunteers at other times go there too, as `## DECISION [PREFERENCE] <title>`.
ask_mode (the session start message says which): `"interrupt"` asks the user everything at once; `"defer"` lets
you log non-BLOCKER preferences as ASSUMPTION entries for the user to confirm at the next phase gate.

## 7. Everything comes back to the user

Every outcome (consensus, questions, deadlock, error, refusal) ends with you telling the user what happened and
what they can do next, then stopping. Never treat silence as approval or pick an option for them: if they don't
decide, change nothing.

## Files and settings

- `.reviews/` (gitignored): `ready.json`, `state.json`, `latest.md`, `errors.log`, `prompts.jsonl`, and each
  round's `round-N-findings.md` (Codex) and `round-N-response.md` (you) under `<plan-file-name>/<plan|phase-N>/`.
- `docs/plans/` (tracked): plans and their decisions files.
- `.codex-loop.json`: `ask_mode`, and the Codex `model` and `effort` for reviews. Change them only when the user asks.
- `.codexreviewignore`: `pattern` withholds more files from Codex; `!pattern` shares a skipped file type (never
  secrets or data).
- Status: `/codex-loop:status`. Tests: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/test_codex_review.py" -v`.
