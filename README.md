# mdownreview-skills

Agent skills for working with markdown review sidecar files (`.review.yaml`) from [mdownreview](https://github.com/dryotta/mdownreview).

Both `.review.yaml` (preferred) and `.review.json` (legacy) formats are supported.

## Install

```
/plugin marketplace add dryotta/mdownreview-skills
/plugin install mdownreview@mdownreview-skills
```

## Skills

| Skill | Description |
|-------|-------------|
| `open` | Find, install, and launch the mdownreview desktop app |
| `read` | Scan for markdown review sidecar files and list unresolved comments |
| `review` | Orchestrate the full cycle: read, fix, and clean up |
| `cleanup` | Delete sidecar files where all comments are resolved |

## CLI

```bash
python skills/mdownreview.py open [--folder path] [--file file]
python skills/mdownreview.py read [path] [--format json|text] [--all]
python skills/mdownreview.py cleanup [path] [--dry-run]
```

## License

MIT
