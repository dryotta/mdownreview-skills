---
name: cleanup
description: "Use to clean up markdown review sidecar files after all review comments have been resolved"
---

# Clean Up Resolved Review Files

Delete markdown review sidecar files (`.review.yaml` and `.review.json`) where every comment has been resolved.

## Usage

```bash
python skills/mdownreview.py cleanup [path] [--dry-run]
```

- Default: scans current directory recursively
- `--dry-run`: preview which files would be deleted without deleting them
- Only deletes files where ALL comments are resolved
