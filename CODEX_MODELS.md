# Codex models and reasoning efforts

Set these in your project's `.codex-loop.json`:

```json
{
  "version": 1,
  "ask_mode": "interrupt",
  "model": "gpt-6.1-sol",
  "effort": "high"
}
```

Or set plan and code reviews separately:

```json
{
  "version": 1,
  "ask_mode": "interrupt",
  "model": { "plan": "gpt-6-astra", "code": "gpt-6.1-sol" },
  "effort": { "plan": "xhigh", "code": "medium" }
}
```

- `/codex-loop:init` fills in `model` and `effort` when it creates `.codex-loop.json`, using `model` and
  `model_reasoning_effort` from `~/.codex/config.toml` (or `$CODEX_HOME/config.toml`). They are then fixed for
  the project: a later change to the Codex config does not affect them. An existing `.codex-loop.json` is kept
  as is; delete it and re-run init to pick up the current defaults.
- If you leave out `model` or `effort`, Codex uses its default from `~/.codex/config.toml` (currently
  `gpt-6-astra` at `xhigh`).
- The environment variable `CODEX_REVIEW_MODEL=<model>` overrides `model` for every review.
- An invalid value stops the review with an error. Codex does not fall back to a default.
- Changes take effect on the next review. You don't need to restart.

## Models

Taken from `~/.codex/models_cache.json` (codex-cli 0.164.0, fetched 2026-11-02). Run `codex` and use `/model`
to see the current list.

| Model (`"model"` value) | Description                                        | Default effort | Efforts            |
|-------------------------|----------------------------------------------------|----------------|--------------------|
| `gpt-6.1-sol`           | Latest workhorse model for coding and everyday work | medium         | low – max          |
| `gpt-6.1-terra`         | GPT-6.1 Terra Codex model                          | low            | low – max          |
| `gpt-6-astra`           | Frontier intelligence for the most demanding work  | low            | low – max          |
| `gpt-6-sol`             | Previous generation workhorse model                | medium         | low – max          |
| `gpt-6-luna`            | Fast and affordable model for easier tasks         | medium         | low – max          |
| `gpt-5.6-sol`           | Older generation workhorse model                   | medium         | low – max          |
| `gpt-5.6-terra`         | Older balanced model for straightforward work      | medium         | low – max          |
| `gpt-5.6-luna`          | Older fast and efficient model                     | medium         | low – max          |

## Efforts

| `"effort"` value | Meaning                                              |
|------------------|------------------------------------------------------|
| `low`            | Fast responses with lighter reasoning                |
| `medium`         | Balances speed and reasoning depth for everyday tasks |
| `high`           | Greater reasoning depth for complex problems         |
| `xhigh`          | Extra high reasoning depth for complex problems      |
| `max`            | Maximum reasoning depth for the hardest problems     |

codex-loop also accepts `none` and `minimal`, but none of the models above support them, so Codex would reject
the run.

Some models also list `ultra` (maximum reasoning with automatic task delegation). codex-loop does **not** accept
`ultra`: it isn't in the plugin's allowed list (`EFFORTS` in `scripts/codex_review.py`).
