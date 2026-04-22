---
name: open
description: "Use to open the mdownreview desktop app so the human can visually review source files. After the agent modifies files, pass the most recently changed source file via --file so the app opens directly to it."
---

# Open mdownreview

Launch the mdownreview desktop app on the current project.

```bash
python skills/mdownreview.py open --folder $PWD [--file file]
```

- `--folder`: project folder to open — always pass `$PWD` or the absolute path of the current workspace
- `--file`: source filename to jump to directly (e.g. `README.md`, not the `.review.yaml`)
- Launches in background; exit 0 on success, exit 1 if app not found

## Picking --file

If you modified any text files in this session (source code, scripts, markdown, skill files, config — anything), pass the most recently changed one as `--file`. This opens the app directly to that file so the human can leave review comments on your changes. If no files were modified, omit `--file`.

If mdownreview is not installed, download it from: https://dryotta.github.io/mdownreview/
