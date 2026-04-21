---
name: open
description: "Use to open the mdownreview desktop app on the current project folder for visual review of comments"
---

# Open mdownreview

Find, install, and launch the mdownreview desktop app to visually review markdown review sidecar files (`.review.yaml`).

## Usage

```bash
python skills/mdownreview.py open [--folder path] [--file file]
```

- `--folder`: project folder to open (default: current working directory)
- `--file`: specific file to open within the project
- If mdownreview is not installed, it will be installed automatically using the official install scripts
- Launches in the background (does not block the agent)
- Exit 0 on launch, exit 1 if app cannot be found or installed

### Manual install

macOS:
```bash
curl -LsSf https://dryotta.github.io/mdownreview/install.sh | sh
```

Windows:
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://dryotta.github.io/mdownreview/install.ps1 | iex"
```

## When to Use

Use this skill when the user wants to visually review or browse comments in the mdownreview desktop app. The app provides a rich UI for reading comments alongside rendered markdown.
