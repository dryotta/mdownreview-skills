# mdownreview-skills

Agent skills for working with `.review.json` sidecar comments from [mDown reView](https://github.com/dryotta/mDown-reView).

## Install

```
/plugin marketplace add dryotta/mdownreview-skills
/plugin install mdownreview-skills@mdownreview-skills
```

## Skills

| Skill | Description |
|-------|-------------|
| `mdownreview-read` | Scan for `.review.json` files and list unresolved comments |
| `mdownreview-respond` | Record an agent response after addressing a comment |
| `mdownreview-resolve` | Mark comments as resolved |
| `mdownreview-cleanup` | Delete `.review.json` files where all comments are resolved |
| `mdownreview-review` | Orchestrate the full cycle: read, fix, respond, resolve, clean up |
| `mdownreview-open` | Find and launch the mDown reView desktop app |

## CLI

```bash
python scripts/mdownreview.py read [path] [--format json|text] [--all]
python scripts/mdownreview.py respond <file> <comment-id> "<text>"
python scripts/mdownreview.py resolve <file> <comment-id> [--all]
python scripts/mdownreview.py cleanup [path] [--dry-run]
python scripts/mdownreview.py open [path]
```

## License

MIT
