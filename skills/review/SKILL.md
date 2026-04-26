---
name: review
description: "Use when the user asks to address review comments, or when directed by another skill — reads .review.yaml feedback created by the mdownreview app and fixes the corresponding source files."
---

# Review and Address All Comments

## Step 1 — Read comments

```
mdownreview-cli read --folder . --json
```

Each entry has `reviewFile`, `sourceFile`, and `comments`. You'll pass `sourceFile` plus the comment `id` to `respond` in step 2. To focus on a single file's comments, add `--file <path>`.

## Step 2 — Fix each file

For each source file with unresolved comments:

1. Read the source file for full context.
2. For each comment:
   - If the feedback is ambiguous or unclear, ask the user a clarifying question before touching the code — wait for their answer.
   - Make the change; ensure it doesn't introduce regressions.
   - After the fix, mark the comment resolved with a brief response:
     ```
     mdownreview-cli respond [--folder <dir>] <sourceFile> <comment-id> --response "brief description of what was changed" --resolve
     ```
   - To only record a response without resolving (e.g. when out of scope, contradictory, or needs a reviewer decision):
     ```
     mdownreview-cli respond [--folder <dir>] <sourceFile> <comment-id> --response "why it couldn't be addressed"
     ```
   - To resolve without adding a response, omit `--response` and pass `--resolve` alone.

`<sourceFile>` may be a path to the source file **or** to its `.review.yaml` sidecar; relative paths resolve against `--folder` (or cwd if omitted).

## Step 3 — Wrap up

Summarize: files changed, comments resolved, any unresolved items with reason.

> See the `read` skill for fallback paths to locate `mdownreview-cli` if it isn't on `PATH`.
