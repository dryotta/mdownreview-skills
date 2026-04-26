---
name: cleanup
description: "Use to clean up markdown review sidecar files after all review comments have been resolved. Run after the review skill completes, or when .review.yaml files exist and the user wants to remove resolved ones."
---

# Clean Up Resolved Review Files

Delete `.review.yaml` sidecar files where every comment is resolved.

```
mdownreview-cli cleanup --folder . [--dry-run]
```

- `--folder .` — scan the current workspace (use `.` or an absolute path)
- `--dry-run` — preview deletions without executing
- Only deletes files where ALL comments are resolved (use `--include-unresolved` to delete sidecars regardless — generally not recommended)

> See the `read` skill for fallback paths to locate `mdownreview-cli` if it isn't on `PATH`.
