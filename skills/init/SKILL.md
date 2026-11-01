---
name: init
description: Opt the current project into the codex-loop review workflow. Checks git and codex login, creates .codex-loop.json, docs/plans/ and the .reviews/ .gitignore entry, then runs the mock test suite.
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/init.py)
---

Run this command from the project root and show the user its output:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/init.py
```

- If a check fails, tell the user how to fix it (the output says), and stop. Do not create the files by hand.
- If it succeeds, tell the user to start a new session or run `/clear` so the SessionStart hook loads the
  workflow protocol, and that `.codex-loop.json` can be deleted to opt out again.
