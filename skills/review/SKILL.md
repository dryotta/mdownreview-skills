---
name: review
description: "Use when .review.json sidecar files exist alongside source files — orchestrates the full review cycle: read comments, fix code, respond, and resolve"
---

# Review and Address All Comments

Orchestrate the full review cycle: read all unresolved comments, fix the code, respond, and resolve.

## Workflow

### Step 1 — Read all unresolved comments

```bash
python skills/mdownreview.py read --format json
```

Parse the JSON output. Each entry has `reviewFile`, `sourceFile`, and `comments` array.

### Step 2 — Process comments grouped by file

For each source file with unresolved comments:

1. **Read** the source file to understand the full context
2. **For each comment** on that file:
   - Understand what the reviewer is asking for
   - If the feedback is ambiguous or unclear, ask the user clarifying questions before making changes
   - Make the code change to address the feedback — ensure the change does not introduce any regressions in existing behavior
   - Record what you did in a professional, concise tone:
     ```bash
     python skills/mdownreview.py respond <review-json-file> <comment-id> "<what you did>"
     ```
   - If the change fully and correctly addresses the comment, mark it resolved:
     ```bash
     python skills/mdownreview.py resolve <review-json-file> <comment-id>
     ```
   - If the change only partially addresses the comment, or you are unsure it is correct, do **not** resolve it — respond explaining what was done and what remains

### Step 3 — Prompt for cleanup

After all comments have been processed, display a message to the user:

> "To remove fully-resolved .review.json sidecar files, run the **cleanup** skill."

Do **not** run cleanup automatically.

### Step 4 — Summary

Report what was done:
- How many files were changed
- How many comments were addressed
- Any comments that could not be resolved (explain why)

## Guidelines

- Use `--format json` for reliable parsing of comment data
- Group work by file — read a file once, address all its comments, then move on
- If a comment is ambiguous, ask the user for clarification before making the change
- If a comment cannot be addressed (e.g., out of scope, contradicts another comment), respond explaining why and leave it unresolved for the reviewer to decide
