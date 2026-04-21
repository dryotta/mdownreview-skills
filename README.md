# mdownreview-skills

Agent skills for working with markdown review sidecar files (`.review.yaml`) from [mdownreview](https://github.com/dryotta/mdownreview).


## Skills

| Skill | Description |
|-------|-------------|
| `open` | Launch the mdownreview desktop app |
| `read` | Scan for markdown review sidecar files and list unresolved comments |
| `review` | Read comments and fix the corresponding source files |
| `cleanup` | Delete sidecar files where all comments are resolved |

## CLI

```bash
python skills/mdownreview.py open [--folder path] [--file file]
python skills/mdownreview.py read [path] [--format json|text] [--all]
python skills/mdownreview.py resolve <review-file> <comment-id> [--response text]
python skills/mdownreview.py respond <review-file> <comment-id> --response text
python skills/mdownreview.py cleanup [path] [--dry-run]
```

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
