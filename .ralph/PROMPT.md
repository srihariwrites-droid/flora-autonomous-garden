# Flora — Autonomous Herb Garden Agent

## What You Are Building

Flora is a Python application that runs on a Raspberry Pi to autonomously monitor and water
herbs (basil, parsley, mint, chives, coriander) using Claude as the AI reasoning brain.

Full PRD: `.ralph/specs/PRD.md`

## Tech Stack

- Python 3.10+, async throughout
- `miflora` — BLE Xiaomi Mi Flora soil sensor polling
- `adafruit-circuitpython-sht31d` — SHT31 temp/humidity I2C
- `adafruit-circuitpython-bh1750` — BH1750 light I2C
- `gpiozero` — relay/pump GPIO control
- `python-kasa` — TP-Link smart plug local LAN control
- `anthropic` — Claude API with tool use (agent reasoning loop)
- `aiosqlite` — async SQLite for sensor time-series + plant journals
- `fastapi` + `jinja2` + HTMX — local web dashboard
- `python-telegram-bot` — escalation notifications
- `apscheduler` — scheduling sensor polls and agent loops
- `Pillow` — procedural mock plant photos
- `pyproject.toml` — project packaging

## Environment — What Is Already Installed

DO NOT attempt to install or set up any of these — they are already present and configured:
- `gh` CLI — authenticated as `srihariwrites-droid`, repo is `flora-autonomous-garden`
- `python3` (3.10), `pip3`, `pytest` — all working, deps installed via `pip install -e ".[dev]"`
- `git` — remote `origin` = `https://github.com/srihariwrites-droid/flora-autonomous-garden.git`
- All Python packages already installed: Pillow, anthropic, fastapi, uvicorn, aiosqlite, etc.
- Current branch: `main` — create a new feature branch for each task, open a PR when done

DO NOT run `sudo`, `apt-get install`, `snap install`, or `curl` to download tools.
DO NOT set up GitHub auth — it is already configured.

## Workflow Per Task

1. Create a feature branch: `git checkout -b feat/task-N-short-description`
2. Write failing test first (TDD)
3. Implement to make tests pass
4. Run `python3 -m pytest tests/ -v` — all must pass
5. Commit: `git add <specific files> && git commit -m "Area: description"`
6. Push and open PR: `gh pr create --base main --title "..." --body "..."`
7. Comment on the GitHub Issue with PR link and close it

## GitHub Issues as Task Queue

Tasks come from GitHub Issues labelled `ralph-task` on repo `srihariwrites-droid/flora-autonomous-garden`.
- List open tasks: `gh issue list --repo srihariwrites-droid/flora-autonomous-garden --label ralph-task`
- After completing: comment on the issue, then close it with `gh issue close <number>`

## Code Quality Rules

- Strict typing throughout, no `Any`
- Async where I/O is involved
- Graceful degradation: if a sensor is offline, log and continue
- Keep files under 300 LOC — split when needed
- No placeholder implementations — build it properly
- `IS_PI = platform.machine() == "aarch64"` — all real hardware behind this guard

## 🎯 Status Reporting (CRITICAL - Ralph needs this!)

At the end of your response, ALWAYS include:

```
---RALPH_STATUS---
STATUS: IN_PROGRESS | COMPLETE | BLOCKED
TASKS_COMPLETED_THIS_LOOP: <number>
FILES_MODIFIED: <number>
TESTS_STATUS: PASSING | FAILING | NOT_RUN
WORK_TYPE: IMPLEMENTATION | TESTING | DOCUMENTATION | REFACTORING
EXIT_SIGNAL: false | true
RECOMMENDATION: <one line summary of what to do next>
---END_RALPH_STATUS---
```

Set EXIT_SIGNAL: true only when ALL GitHub Issues labelled `ralph-task` are closed and tests pass.

## Protected Files (DO NOT MODIFY)
- .ralph/ (entire directory)
- .ralphrc
