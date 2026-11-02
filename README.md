# codex-loop

A [Claude Code](https://claude.com/claude-code) plugin that has OpenAI Codex review Claude's work. Claude writes
a plan, Codex reviews it, and once you approve the plan Claude builds it one phase at a time, with each phase
reviewed by Codex too. Claude and Codex argue disagreements out with evidence. Tradeoffs that are yours to decide
come to you, and nothing moves to the next phase without your go-ahead.

Codex only reviews. It works on a sanitized, read-only copy of your project and never edits your files.

> **macOS only.** codex-loop has been built and tested only on macOS. Its review sandbox setup and desktop
> notifications rely on macOS. It may not work on Linux or Windows (including WSL), and those platforms are not
> supported.

## How it works

1. **Plan.** When you ask for a feature, Claude writes a plan to `docs/plans/YYYY-MM-DD-<slug>.md`. The plan
   quotes your request and splits the work into phases.
2. **Plan review.** Claude writes `.reviews/ready.json`. When Claude's turn ends, the plugin's Stop hook runs
   `codex exec` on the plan and hands the findings back to Claude.
3. **Rounds.** Claude checks each finding against the actual code or plan, then accepts it, rejects it or
   partly accepts it, giving its reasons. Codex reviews again. This repeats until no BLOCKER or MAJOR finding
   is left (consensus) or the round limit is reached: 3 rounds for a plan and 2 per code phase, plus one
   extension round to verify accepted fixes.
4. **You decide.** Claude shows you the final plan. You approve it or ask for changes.
5. **Code, phase by phase.** Before each phase, Claude records a diff base. When the phase is done and its tests
   pass, Codex reviews only that phase's changes. After consensus, Claude summarizes the phase and waits for
   you before starting the next one.

Codex also gets your own words. Every prompt you send and every answer you give to Claude's questions is
recorded verbatim (secrets redacted) in `.reviews/prompts.jsonl`, and each plan and code review includes the
ones since work on that plan began. Codex checks Claude's plan and code against what you actually said, not
only against Claude's summary of it, and flags anything Claude misread, narrowed, dropped or added (an
`Intent:` finding). If Claude disagrees with one, the question comes to you, because only you know what you meant.

Questions about preferences, such as JSON vs TOML or strict vs lenient, and changes that would expand the plan's
scope, always come to you, batched into one message per round. Your answers are recorded in
`docs/plans/<plan>-decisions.md`, and Codex is told not to raise them again. If Claude and Codex still disagree
when the rounds run out, you get both sides and make the call.

Codex reviews in a throwaway copy of the project in a temp directory. Secrets such as keys, tokens, `.env` files
and credential-like values are removed or redacted, and data files are left out. Codex's sandbox can read only
that copy and system paths. It is denied your home directory and the real checkout, and it can't write anywhere.

## Requirements

- **macOS**
- **[Claude Code](https://docs.claude.com/en/docs/claude-code/setup)**
- **Python 3.11 or later**, as `python3` on your `PATH`. Apple's Command Line Tools ship Python 3.9, which
  isn't enough: with it, init doesn't pick up your Codex defaults and the check of your Codex config can fail.
  Check with `python3 --version`. If it's older than 3.11, install a newer one with `brew install python`.
- **git**, for example from `xcode-select --install` or `brew install git`. Your project does not need to be a
  git repository.
- **Codex CLI**, logged in. Tested with `codex-cli 0.165.0`. See the next section.

## Install

### 1. Install and log in to the Codex CLI

Install it with Homebrew:

```sh
brew install --cask codex
```

or with npm (needs Node.js 18 or later):

```sh
npm install -g @openai/codex
```

Then log in with your ChatGPT account, or with an OpenAI API key:

```sh
codex login
codex login status   # should say you are logged in
```

Check that `codex --version` works in the same shell you start Claude Code from.

Don't set `sandbox_mode` at the top level of `~/.codex/config.toml`, or in the profile Codex uses by default.
It would replace the review's read-only sandbox, so codex-loop refuses to run while it is set. A `sandbox_mode`
inside a named profile you don't use by default is fine.

### 2. Install the plugin

Clone this repository, then add it to Claude Code as a local plugin marketplace:

```sh
git clone <this-repo-url> ~/codex-loop
```

Then, inside Claude Code:

```
/plugin marketplace add ~/codex-loop
/plugin install codex-loop@codex-loop-local
```

Restart Claude Code if it asks you to.

### 3. Turn it on in a project

The plugin does nothing in a project until you opt that project in. Start Claude Code in the project's root
folder and run:

```
/codex-loop:init
```

`init` checks that git and a logged-in `codex` are available and runs the plugin's own test suite against a
mock reviewer, which takes about a minute. Only if every check passes does it create:

- `.codex-loop.json`, which marks the project as opted in and holds its settings
- `docs/plans/`, where plans and decision logs go (commit these)
- a `.reviews/` entry in `.gitignore`, because review rounds, state and logs go there

Then **start a new session or run `/clear`** so the workflow rules load. From then on, ask Claude for features
as usual.

To opt out, delete `.codex-loop.json`.

## Usage

- Ask for a feature. Claude writes a plan, and the review runs when Claude ends its turn. A Codex review can take
  up to about 15 minutes.
- Each round's findings file (`.reviews/<plan>/<stage>/round-N-findings.md`) records the tokens Codex used for
  it. The `effort` setting is the biggest lever on that cost.
- `/codex-loop:status` shows the current plan, stage, round, last verdict and any open questions or disputes.
- You get a macOS notification when a review reaches consensus or deadlock, fails, or needs your answers, and
  whenever Claude is waiting for your input. Set `CODEX_REVIEW_NOTIFY=0` to turn notifications off.
- To skip review for a plan or a phase, tell Claude so. Your choice is recorded in the decisions file.

## Configuration

### `.codex-loop.json`

```json
{
  "version": 1,
  "ask_mode": "interrupt",
  "model": "gpt-6-astra",
  "effort": "xhigh"
}
```

- `ask_mode`:
  - `"interrupt"` (default): every preference and scope question comes to you straight away.
  - `"defer"`: for non-critical preferences, Claude picks a sensible default, logs it as an assumption, and asks
    you to confirm all its assumptions at the next phase gate. BLOCKER preferences and scope changes still
    interrupt.
- `model` and `effort`: the Codex model and reasoning effort for reviews. `init` fills these in from the
  defaults in your `~/.codex/config.toml` (`model` and `model_reasoning_effort`). You can set separate values
  for plan and code reviews:

  ```json
  "model": { "plan": "gpt-6-astra", "code": "gpt-6.1-sol" },
  "effort": { "plan": "xhigh", "code": "medium" }
  ```

  Leave either one out to use Codex's current default. [`CODEX_MODELS.md`](CODEX_MODELS.md) lists the models
  and efforts. Edits take effect from the next review.

### `.codexreviewignore` (optional)

This file goes in the project root and uses one pattern per line:

- `pattern` withholds more files from Codex.
- `!pattern` shares a file type that the built-in allowlist skips.

Secret and data files are never shared, even with `!pattern`. Claude tells you about any changed files that
Codex didn't see, so you can check them yourself.

### Environment variables

| Variable | Default | Effect |
|---|---|---|
| `CODEX_REVIEW_MODEL` | — | Model for every review. Overrides `.codex-loop.json`. |
| `CODEX_REVIEW_TIMEOUT` | `840` | Seconds before a Codex run is stopped |
| `CODEX_REVIEW_PLAN_ROUNDS` | `3` | Regular rounds per plan review |
| `CODEX_REVIEW_CODE_ROUNDS` | `2` | Regular rounds per code phase review |
| `CODEX_REVIEW_EXTRA_ROUNDS` | `1` | Extension rounds, only to verify accepted BLOCKER or MAJOR fixes |
| `CODEX_REVIEW_CODEX_BIN` | `codex` on `PATH` | Path to the Codex CLI |
| `CODEX_REVIEW_NOTIFY` | `1` | `0` turns off macOS notifications |

## Files in your project

| Path | Tracked | Contents |
|---|---|---|
| `.codex-loop.json` | yes | Opt-in marker and settings |
| `docs/plans/*.md` | yes | Plans and `<plan>-decisions.md` decision logs |
| `.reviews/` | no (gitignored) | `ready.json`, `state.json`, `latest.md`, `errors.log`, `prompts.jsonl` (your messages, for Codex), and each round's findings and responses |
| `.codexreviewignore` | yes | Optional extra rules for which files Codex sees |

## Troubleshooting

- **`init` fails at "codex login"**: run `codex login`, then `codex login status`, and try again. If it says
  `codex` isn't found, the Codex CLI isn't on the `PATH` of the shell Claude Code was started from.
- **"sets sandbox_mode, which replaces the review's read-only permission profile"**: remove `sandbox_mode` from
  the top level of `~/.codex/config.toml`, or from the profile Codex uses by default, as described in step 1.
- **"model ... is not valid" or "effort ... is not valid"**: fix the value in `.codex-loop.json`. See
  [`CODEX_MODELS.md`](CODEX_MODELS.md).
- **Codex timed out or failed**: Claude tells you and stops. Ask Claude to retry once the cause is fixed. Details
  are in `.reviews/errors.log`.
- **Nothing happens after `init`**: start a new session or run `/clear`, because the workflow rules load at
  session start.

## Development

Run the test suite, which uses a mock Codex and makes no model calls:

```sh
python3 scripts/test_codex_review.py -v
```

`CODEX_LOOP_LIVE_TEST=1` also runs a test of the real `codex sandbox`, which still makes no model call.

| Path | Purpose |
|---|---|
| `scripts/codex_review.py` | Stop hook: stages the sanitized copy, runs Codex, tracks rounds and disputes. Also has the `phase-start` command. |
| `scripts/session_start.py` | SessionStart hook: loads `templates/protocol.md` (the workflow rules) in opted-in projects |
| `scripts/notify_input.py` | Notification hook: macOS notification when Claude is waiting for you |
| `scripts/log_prompt.py` | UserPromptSubmit and PostToolUse (AskUserQuestion) hook: records your messages for Codex |
| `scripts/init.py`, `scripts/status.py` | `/codex-loop:init` and `/codex-loop:status` |
| `scripts/codex_mock.py` | Mock Codex used by the tests |
