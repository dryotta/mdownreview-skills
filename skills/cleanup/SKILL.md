---
name: cleanup
description: "Use to clean up markdown review sidecar files after all review comments have been resolved. Run after the review skill completes, or when .review.yaml files exist and the user wants to remove resolved ones."
---

# Clean Up Resolved Review Files

Delete `.review.yaml` / `.review.json` sidecar files where every comment is resolved.

```bash
python skills/mdownreview.py cleanup [path] [--dry-run]
```

- Scans current directory recursively
- `--dry-run`: preview deletions without executing
- Only deletes files where ALL comments are resolved
