---
name: review
description: "Use when the user asks to address review comments, or when directed by another skill — reads .review.yaml feedback created by the mdownreview app and fixes the corresponding source files."
---

# Review and Address All Comments

## Step 1 — Read comments

```
mdownreview-cli read --folder . --json
```

Each entry has `reviewFile`, `sourceFile`, and `comments`. You'll pass `sourceFile` plus the comment `id` to `respond` in step 2.

## Step 2 — Fix each file

For each source file with unresolved comments:

1. Read the source file for full context.
2. For each comment:
   - If the feedback is ambiguous or unclear, ask the user a clarifying question before touching the code — wait for their answer.
   - Make the change; ensure it doesn't introduce regressions.
   - After the fix, mark the comment resolved with a brief response summarizing what was done:
     ```
     mdownreview-cli respond <sourceFile> <comment-id> --response "brief description of what was changed" --resolve
     ```
   - If a comment can't be addressed (out of scope, contradicts another comment, needs a decision), record a response explaining why — leave it unresolved so the reviewer can decide:
     ```
     mdownreview-cli respond <sourceFile> <comment-id> --response "why it couldn't be addressed"
     ```

## Step 3 — Wrap up

Summarize: files changed, comments resolved, any unresolved items with reason.

> See the `read` skill for fallback paths to locate `mdownreview-cli` if it isn't on `PATH`.
