---
name: open
description: "Use to open the mdownreview desktop app so the human can visually review source files. After the agent modifies files, pass the most recently changed source file via --file so the app opens directly to it."
---

# Open mdownreview

Launch the `mdownreview` desktop app on the current project. The app accepts:

```
mdownreview [--folder <path> ...] [--file <source-file> ...] [<positional path> ...]
```

- `--folder` — project folder to open (use the absolute path of the current workspace). Repeatable; the **first** `--folder` becomes the base for resolving relative `--file` and positional paths.
- `--file` — source file to jump to (e.g. `README.md`, **not** the `.review.yaml` sidecar). **Repeatable** — pass `--file` multiple times to open several files in tabs.
- Positional paths also work: directories are treated as folders, files as files. Absolute paths bypass the folder base.

Examples:

```
mdownreview --folder D:\work\proj --file README.md --file src/lib.rs
mdownreview --folder D:\work\proj docs/spec.md notes.md
```

Launch it as a **background / detached process** — never block the agent on the GUI:

- **bash / zsh (macOS, Linux)**:
  ```bash
  ("$BIN" --folder "$PWD" --file README.md --file src/lib.rs >/dev/null 2>&1 &) disown
  ```
- **PowerShell (Windows)**:
  ```powershell
  Start-Process -FilePath $bin -ArgumentList @('--folder', $PWD.Path, '--file', 'README.md', '--file', 'src/lib.rs')
  ```

The app is single-instance: re-running it while it's already open sends the new args to the existing window instead of starting a second copy.

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

If you modified any text files in this session (source code, scripts, markdown, skill files, config — anything), pass each modified file as a separate `--file` argument so the human can review every change. If no files were modified, omit `--file`.
