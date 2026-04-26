---
name: open
description: "Use to open the mdownreview desktop app so the human can visually review source files. After the agent modifies files, pass the most recently changed source file via --file so the app opens directly to it."
---

# Open mdownreview

Launch the `mdownreview` desktop app on the current project. The app accepts:

```
mdownreview --folder <path> [--file <source-file>]
```

- `--folder` — project folder to open (use the absolute path of the current workspace)
- `--file` — source filename to jump to directly (e.g. `README.md`, **not** the `.review.yaml` sidecar)

Launch it as a **background / detached process** — never block the agent on the GUI:

- **bash / zsh (macOS, Linux)**:
  ```bash
  ("$BIN" --folder "$PWD" --file "README.md" >/dev/null 2>&1 &) disown
  ```
- **PowerShell (Windows)**:
  ```powershell
  Start-Process -FilePath $bin -ArgumentList @('--folder', $PWD.Path, '--file', 'README.md')
  ```

## Locating the `mdownreview` binary

Search in this order; use the first that exists:

**macOS** — installed by `install.sh` to `~/Applications`:
1. `~/Applications/mdownreview.app/Contents/MacOS/mdownreview`
2. `/Applications/mdownreview.app/Contents/MacOS/mdownreview`
3. `mdownreview` on `PATH`

**Windows** — installed by NSIS (`install.ps1`) per-user:
1. `%LOCALAPPDATA%\Programs\mdownreview\mdownreview.exe`
2. `%LOCALAPPDATA%\mdownreview\mdownreview.exe`
3. `%PROGRAMFILES%\mdownreview\mdownreview.exe`
4. `mdownreview.exe` on `PATH`

On macOS you can also use `open -a mdownreview --args --folder "$PWD" --file README.md` if the app is registered with Launch Services.

If the binary cannot be found anywhere, tell the user to install it from <https://dryotta.github.io/mdownreview/>.

## Picking `--file`

If you modified any text files in this session (source code, scripts, markdown, skill files, config — anything), pass the most recently changed one as `--file`. This opens the app directly to that file so the human can leave review comments on your changes. If no files were modified, omit `--file`.
