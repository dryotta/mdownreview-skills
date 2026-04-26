---
name: read
description: "Use when .review.yaml sidecar files exist in the workspace — reads unresolved review comments for the agent to address. Trigger automatically whenever .review.yaml files are detected."
---

# Read Review Comments

Run the `mdownreview-cli` tool to list unresolved review comments in the current workspace.

```
mdownreview-cli read [--folder <dir>] [--file <path>] [--json | --format text|json] [--include-resolved]
```

- `--folder <dir>` — root to scan (default: current working directory)
- `--file <path>` — read a single source file or `.review.yaml` sidecar (relative to `--folder`/cwd, or absolute) instead of scanning
- `--json` — shorthand for `--format json`; use this when processing programmatically
- `--format text|json` — explicit output format (default: `text`)
- `--include-resolved` — include already-resolved comments in addition to unresolved ones

JSON output is an array of `{ reviewFile, sourceFile, comments }` objects. Each comment includes `id`, `file`, `line`, `type`, `text`, and `resolved` status.

## Locating `mdownreview-cli`

`mdownreview-cli` is normally on `PATH` after install. If `mdownreview-cli` is not found, fall back to one of these locations:

- **macOS**: `/usr/local/bin/mdownreview-cli`, `~/.local/bin/mdownreview-cli`, or `~/Applications/mdownreview.app/Contents/MacOS/mdownreview-cli`
- **Windows**: `%LOCALAPPDATA%\Programs\mdownreview\mdownreview-cli.exe` or `%LOCALAPPDATA%\mdownreview\mdownreview-cli.exe`

If it cannot be found anywhere, ask the user to install mdownreview from <https://dryotta.github.io/mdownreview/>.
