---
name: read
description: "Use when .review.yaml sidecar files exist in the workspace — reads unresolved review comments for the agent to address. Trigger automatically whenever .review.yaml files are detected."
---

# Read Review Comments

```bash
python skills/mdownreview.py read [path] [--format json|text] [--all]
```

- Scans current directory recursively; shows unresolved comments by default
- `--format json` for machine-parseable output (use this when processing programmatically)
- `--all` to include already-resolved comments

Each comment includes: id, file, line, type, text, resolved status.
