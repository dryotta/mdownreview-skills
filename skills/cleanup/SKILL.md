---
name: cleanup
description: "Use to clean up markdown review sidecar files after all review comments have been resolved. Run after the review skill completes, or when .review.yaml files exist and the user wants to remove resolved ones."
---

# Clean Up Resolved Review Files

Delete `.review.yaml` sidecar files where every comment is resolved.

```
mdownreview-cli cleanup [--folder <dir>] [--dry-run] [--include-unresolved]
```

- `--folder <dir>` — root to scan (default: current working directory)
- `--dry-run` — preview deletions without removing files
- `--include-unresolved` — also delete sidecars containing unresolved comments (destructive — only use if the user explicitly confirms they want to discard pending feedback)

By default only sidecars where **every** comment is resolved are deleted.

> See the `read` skill for fallback paths to locate `mdownreview-cli` if it isn't on `PATH`.
