# mdownreview-skills

Agent skills for working with `.review.json` sidecar comments from [mDown reView](https://github.com/dryotta/mDown-reView).

## Install

```
/plugin marketplace add dryotta/mdownreview-skills
/plugin install mdownreview@mdownreview-skills
```

## Skills

| Skill | Description |
|-------|-------------|
| `read` | Scan for `.review.json` files and list unresolved comments |
| `respond` | Record an agent response after addressing a comment |
| `resolve` | Mark comments as resolved |
| `cleanup` | Delete `.review.json` files where all comments are resolved |
| `review` | Orchestrate the full cycle: read, fix, respond, resolve, clean up |
| `open` | Find and launch the mDown reView desktop app |

## CLI

```bash
python skills/mdownreview.py read [path] [--format json|text] [--all]
python skills/mdownreview.py respond <file> <comment-id> "<text>"
python skills/mdownreview.py resolve <file> <comment-id> [--all]
python skills/mdownreview.py cleanup [path] [--dry-run]
python skills/mdownreview.py open [path]
```

## License

MIT
