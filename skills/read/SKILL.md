---
name: read
description: "Use when .review.yaml sidecar files exist in the workspace — reads unresolved review comments for the agent to address. Trigger automatically whenever .review.yaml files are detected."
---

# Read Review Comments

```bash
python skills/mdownreview.py read --folder $PWD [--format json|text] [--all]
```

- `--folder`: project folder to scan (always pass `$PWD` or the absolute path of the current workspace)
- `--format json` for machine-parseable output (use this when processing programmatically)
- `--all` to include already-resolved comments

Each comment includes: id, file, line, type, text, resolved status.
