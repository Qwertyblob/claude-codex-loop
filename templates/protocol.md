# Workflow: plan → review → code, with Codex as reviewer

This project uses the codex-loop plugin (opted in via `.codex-loop.json`). Its Stop hook
(`${CLAUDE_PLUGIN_ROOT}/scripts/codex_review.py`) runs an
OpenAI Codex review whenever `.reviews/ready.json` changes, and feeds the findings back to you.
Codex reviews a sanitized copy of the repo in a temp directory. Its permission profile can read only that
copy and system paths, is denied `$HOME` and this checkout, and can write nowhere. You are the only one who
edits files.

## 1. Planning

- When the user asks for a feature, write the plan to `docs/plans/YYYY-MM-DD-<slug>.md` (today's date,
  short kebab-case slug). Do not write any code until the user approves the final plan.
- The plan must have:
  - `## Assignment`: the user's request, quoted verbatim (Codex reviews the plan against it).
  - `## Phases`: numbered phases (`### Phase 1: ...`), each independently implementable and reviewable,
    with its files, approach, and how it will be tested.
  - Risks and open questions.
- Put guidance about secrets under a heading (`### Secret handling` followed by bullets), not as a
  `- Secrets:` bullet with sub-bullets: anything nested under a credential-like key is redacted before
  Codex sees it.
- Ask the user any clarifying questions you need before or while drafting, as usual.
- When the draft is complete, request a review (section 4) with `"type": "plan"`. If you stop with a plan that
  was never sent for review, the hook reminds you once per version of the plan; ignore the reminder while the
  plan is still a draft.
- If the user explicitly says a plan or a phase should not be reviewed, do not request a review. Record
  `## DECISION [SKIP] No Codex review for plan` (or `phase-N`) in the plan's decisions file (section 6) and
  tell them. `phase-start` then treats that stage as passed.

## 2. Coding (only after the user approves the plan)

- Implement one phase at a time.
- Before writing any code for phase N, record its diff base:
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/codex_review.py" phase-start docs/plans/<plan>.md N`
  (Codex then reviews only this phase's changes, even if nothing was committed in between.)
  Outside a git repository it stores a file snapshot in `.reviews/snapshots/` instead. A code review without a
  phase-start base fails (in git repositories too), so never skip this step. When resuming a phase (after
  `/clear` or in a new session), do not run it again: it refuses, because a new base would hide the changes made so
  far. Use `--reset` only when the user explicitly wants the phase's diff to start over from the current state.
- Changes made after a stage's last Codex review (including MINOR/NIT fixes applied after consensus) are never
  reviewed by it. The next `phase-start` lists them and refuses: tell the user, who chooses between a new review of
  that stage (rewrite `.reviews/ready.json` for it) and starting anyway (`--owner-approved`, on their say-so).
- Codex never sees withheld files (secrets, data, unsupported types). If the phase changed any, the review result
  lists them as not reviewed: tell the user, and check them yourself. A phase whose only changes are in withheld
  files, or that has no changes, is not reviewed at all.
- When phase N is complete and its tests pass, request a review with `"type": "code"`, `"phase": N`.
- After review consensus, summarize for the user and wait for their go-ahead before starting phase N+1.
  `phase-start N` refuses unless the previous stage (the plan, or phase N-1) reached consensus or the user decided
  every item its deadlock left open; only on the user's explicit say-so, use `--owner-approved` (recorded).
  This is the **phase gate**: also list every pending ASSUMPTION for the user to confirm (section 6).

## 3. Never trigger on work in progress

Only `.reviews/ready.json` triggers a review. Write it only when a plan draft or a whole phase is ready.
Never write it mid-task, and never write it to "check" partial work.

## 4. Requesting a review

Write `.reviews/ready.json`:

```json
{"type": "plan", "plan_path": "docs/plans/2026-10-27-example.md", "phase": null, "round": 1}
{"type": "code", "plan_path": "docs/plans/2026-10-27-example.md", "phase": 2, "round": 1}
```

Optional fields: `"base"` (a git ref to diff against for code reviews, which overrides the phase-start
snapshot; git repositories only), and `"attempt"` (increment it to retry after an error, but only when the user asks).
Then end your turn. The hook runs Codex (up to ~15 min) and continues you with the findings.

## 5. Handling findings (each round)

The hook's message tells you exactly which files to write. For every finding:

- Evaluate it on its merits. Verify the claim against the actual code or plan: open the file, check the
  line, run the test. Do not defer to Codex by default, and do not reject by default either.
- Write `.reviews/<plan-file-name>/<plan|phase-N>/round-N-response.md` (e.g. `.reviews/2026-10-27-example/plan/`),
  one section per finding. Every BLOCKER/MAJOR finding must get an ACCEPT/REJECT/PARTIAL heading, or the
  next round is refused:

  ```markdown
  ### F1: ACCEPT
  Verified at src/foo.py:42: the None case is unhandled. Added a guard and a test (tests/test_foo.py::test_none).

  ### F2: REJECT [FACT]
  parse_config is defined at src/config.py:12 (`def parse_config(path)`); the claim is wrong.

  ### F3: PARTIAL [FACT]
  Agree the error message is unclear (changed it); disagree a retry is needed: the call is idempotent (see ...).

  ### F4: REJECT [PREFERENCE]
  JSON vs TOML is a tradeoff: JSON needs no new dependency; TOML allows comments. My recommendation: JSON.
  ```

- Tag every REJECT/PARTIAL with its class (section 6). Untagged means `[FACT]`.

- Apply only the changes you accept (fully or partly).
- Write `.reviews/ready.json` exactly as the hook says (next round number) and end your turn.

A REJECT or PARTIAL on a BLOCKER/MAJOR finding opens a dispute (key `R<round>-F<n>`). It stays unresolved
until Codex explicitly concedes it, or counters it with new evidence that you then accept. If Codex skips a
dispute, it stays open and Codex is asked again; you don't need to respond to it.

**Consensus** means no unresolved BLOCKER/MAJOR findings remain (these are the "bugs"). MINOR and NIT findings
are your call and never force another round, but they are always reported to the user. On consensus, do not touch
`ready.json`, and tell the user:
- after a **plan** review: first the final plan in full (as revised by the review), reproduced verbatim in your
  reply (the user does not see tool output, so a path, a file read, or a summary does not count), then a summary
  of the review;
- after a **code** review: a summary of what the phase built and what the review found and fixed;
- in both cases: what you rejected and why (and whether Codex conceded), and every MINOR/NIT finding from all
  rounds, each with whether you fixed it (fixes after consensus are not re-reviewed) or left it, and why.

**Round limits**: 3 rounds for a plan, 2 for each code phase. After the last regular round, one extension
round is allowed only if you ACCEPT at least one BLOCKER/MAJOR finding, so Codex can verify the fix. If you
accept none (only disputes remain), don't write `ready.json`; it's a deadlock. The hook refuses an extension
round with no accepted finding. After the extension round (plan round 4, code round 3), it's a deadlock
regardless.

**Deadlock**: do not touch `ready.json`. Present each unresolved dispute to the user with both sides' arguments
and evidence, then wait for their decision. Record each decision in the decisions file (section 6) and apply it.
If they then ask for another review, write `ready.json` again; that starts a new cycle with the same limits.
Every dispute the user has not decided carries into that cycle, and Codex must concede or counter each one,
so a new cycle cannot reach consensus by Codex simply not mentioning it.
Until the user decides every dispute, and every finding from a final (extension) round that no review verified,
`phase-start` for the next phase refuses (section 7).

**Errors** (Codex failed or timed out): explain briefly to the user and stop. Do not retry unless they ask.

## 6. Owner input: FACT vs PREFERENCE, scope, decisions

Classify every disputed finding (one you REJECT or PARTIAL) in its response heading:

- `[FACT]`: verifiable in the code or plan (does the function exist, does the test fail, is the line reachable).
  Resolve it yourself with evidence; Codex concedes or counters as usual. Never ask the user about facts.
- `[PREFERENCE]`: a tradeoff whose answer depends on the owner's priorities (format, strictness, dependencies,
  naming conventions, performance vs simplicity). On a BLOCKER/MAJOR finding the owner decides, not you or Codex.
  On a MINOR/NIT finding it is your call (it never goes to the owner); mention it in your summary.
- `[SCOPE]`: put this on any finding you would ACCEPT or PARTIAL whose change expands scope beyond the
  approved plan. **Never apply a scope expansion without asking the user first**, in any mode, including
  MINOR/NIT suggestions after consensus.

**Asking.** Write your response and `ready.json` as usual. If PREFERENCE/SCOPE items have no recorded
answer, the hook does not run Codex. Instead it returns one batched question block with Codex's position and
yours for each item. Ask the user all of them **once, in one message** (one AskUserQuestion call with one
question per item if there are 4 or fewer, otherwise one plain message). Present both sides fairly and label
your recommendation as yours. Never ask more than once per round.

**Recording.** Record every answer in `docs/plans/<plan-file-name>-decisions.md` (tracked, next to the plan),
one entry per item, using the heading the hook gives you:

```markdown
# Owner decisions: 2026-10-27-example

## plan R1-F4: DECISION [PREFERENCE] Store settings in TOML instead of JSON
- Question: JSON (no new dependency) or TOML (comments)?
- Answer: JSON. Comments are not needed.
- Recorded: 2026-10-27
```

Then apply the outcome. If the user sided with Codex, change that response heading to ACCEPT (keep the tag)
and make the change. If the user sided with you, leave it. A SCOPE change the user declines becomes REJECT. Then
write `ready.json` as the hook says (it adds an `"owner_input"` counter). Recorded entries settle those
disputes, so Codex is not asked about them again. The hook includes this file in every Codex prompt as final
owner decisions that must not be re-raised, and as **requirements**: Codex should still report it when the
plan or code does not implement a decision's chosen outcome correctly. The hook never discards such findings. It
flags any finding that touches a decision. If the finding reopens the decided tradeoff, REJECT it as `[FACT]`,
citing the decision entry (Codex must concede). If it shows the chosen outcome is missing or incomplete,
evaluate and fix it like any other finding. Decisions the user
volunteers at any other time go in the same file, under a heading without a key: `## DECISION [PREFERENCE] <title>`.

**ask_mode** (in `.codex-loop.json`; the session start message says which mode is active):

- `"interrupt"` (default): every PREFERENCE and SCOPE item goes to the user at once, as above.
- `"defer"`: for a non-critical preference (a MAJOR, not a BLOCKER), pick a reasonable default, do not
  ask, and log it as an assumption:

  ```markdown
  ## plan R1-F4: ASSUMPTION [PREFERENCE] Store settings in TOML instead of JSON
  - Default chosen: JSON
  - Alternative: TOML (Codex)
  - Why: no new dependency; can be switched in one place later.
  ```

  BLOCKER preferences and all SCOPE items still interrupt. At the next phase gate (consensus on the plan or
  a phase), list **all** pending assumptions in one message for the user to confirm or override:
  - confirmed: change the entry's ASSUMPTION to DECISION.
  - overridden: record the answer, change ASSUMPTION to OVERRIDE, apply the change, and run the tests. Then
    request a re-review of that stage with the `ready.json` the consensus message gives you. This is the only
    time you write `ready.json` after consensus. Changes made for an override must be reviewed before the next
    phase starts.

  `phase-start N` refuses while any assumption listed at the previous stage's consensus is still unconfirmed, or
  was overridden without that re-review reaching consensus.

## Files

- `.reviews/` (gitignored): `ready.json`, `state.json`, `latest.md` (current status), `errors.log`,
  `<plan-file-name>/<stage>/round-N-findings.md` (Codex) and `round-N-response.md` (you).
- `docs/plans/` (tracked): plans and their `<plan-file-name>-decisions.md` owner decisions.
- `.codex-loop.json`: opt-in marker and settings (`{"version": 1, "ask_mode": "interrupt"}`). Optional `"model"` and
  `"effort"` (Codex reasoning effort: none, minimal, low, medium, high, xhigh, max) set Codex for reviews, either
  for both kinds (`"effort": "high"`) or per kind (`"effort": {"plan": "xhigh", "code": "medium"}`). Init writes
  the Codex defaults from `~/.codex/config.toml` at that time; unset means Codex's own current default. Change
  them only when the user asks. An invalid value stops the review with an error for the user.
- `.codexreviewignore` (optional): `pattern` withholds more files from Codex. `!pattern` shares a file type the
  built-in allowlist skips, but can never share secret or data files.
- Tests: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/test_codex_review.py" -v` (uses the mock reviewer).
- Status: `/codex-loop:status`.

## 7. Everything comes back to the user

The loop never ends silently and never decides for the user. Every outcome ends with you telling the user
what happened and what they can do next, then stopping:

| Outcome | You tell the user | Ways forward (their choice) |
|---|---|---|
| Consensus | plan: the final plan and a review summary; code: what was built and fixed. Always: every MINOR/NIT and what was done, pending assumptions | approve, or ask for changes or another review |
| Owner questions | the batched questions | answer (recorded), or leave them open |
| Deadlock / round limit | each dispute, both sides, your recommendation | decide (recorded), another cycle, move on, leave open |
| Codex error / timeout | that the review did not run, and why | retry (`"attempt"`), or fix the cause first |
| Hook failure, review already running | what happened | retry later; nothing is lost |
| Invalid `ready.json` you cannot fix | what is wrong | fix it together |
| No phase-start base | that the phase base was never recorded, so the phase's changes cannot be isolated | they decide: never run `phase-start` after the fact on your own, it would hide the changes |
| Nothing to review | that the phase has no changes, or only changes in withheld files (listed) | review those files themselves, share a file type with `!pattern` in `.codexreviewignore`, or retry once the work is in place |
| `phase-start` refused | the open items it lists (unreviewed stage, a requested re-review that has not run yet, open deadlock items, assumptions) | resolve them, or start anyway with `--owner-approved` |

If the user makes no decision, for any reason, change nothing: leave `ready.json` and the decisions file
alone, say where things stand and which options are open, and stop. Never treat silence as approval, and never
pick an option for them. Exception: defer-mode assumptions, which are always listed for confirmation at the
next gate. Use `--owner-approved` only after the user has seen the refusal and explicitly said to proceed. It is
recorded in the decisions file.

