---
name: status
description: Show codex-loop review status for this project - current plan, stage, round, last Codex verdict, and unresolved disputes from .reviews/.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/status.py)
---

Run this command from the project root and show the user its output verbatim:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/status.py
```

Do not modify anything under `.reviews/`.
