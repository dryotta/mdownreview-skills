# mdownreview-skills

Agent skills for working with markdown review sidecar files (`.review.yaml`) from [mdownreview](https://github.com/dryotta/mdownreview).

These skills wrap the official `mdownreview-cli` binary and the `mdownreview` desktop app — no Python or other runtime is required, and they work on macOS and Windows from both bash (Claude Code) and PowerShell (GitHub Copilot CLI).

## Skills

| Skill | Description |
|-------|-------------|
| `open` | Launch the mdownreview desktop app on the current project |
| `read` | List unresolved review comments via `mdownreview-cli read` |
| `review` | Read comments and fix the corresponding source files (`mdownreview-cli respond`) |
| `cleanup` | Delete sidecar files where all comments are resolved (`mdownreview-cli cleanup`) |

## Prerequisites

Install `mdownreview` (which ships the `mdownreview-cli` binary alongside the desktop app):

- **macOS**: `curl -LsSf https://dryotta.github.io/mdownreview/install.sh | sh`
- **Windows**: download the latest `.zip` from [Releases](https://github.com/dryotta/mdownreview/releases/latest) and run the installer, or `powershell -ExecutionPolicy ByPass -c "irm https://dryotta.github.io/mdownreview/install.ps1 | iex"`

After install, `mdownreview-cli` is normally on `PATH`. Each skill also documents fallback locations to find the binary if it isn't.

## Local Development & Testing

To test changes without publishing to a remote marketplace:

**Step 1 — Validate the plugin structure:**
```
! claude plugin validate ./
```

**Step 2 — Register the local directory as a marketplace (project-scoped):**
```
! claude plugin marketplace add ./ --scope project
```

**Step 3 — Install from it (project-scoped):**
```
! claude plugin install mdownreview --scope project
```

> Note: `plugin install` has no `--path` flag. Installing from a local path requires registering the directory as a marketplace first. Use `--scope project` on both commands to keep everything local to this project.

## License

MIT
