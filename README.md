# 🐦 Pigeon

> Carrier pigeon for your coding agent. Drive the Cline CLI from Telegram on
> Windows, in the background, and let it survive reboots.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-51%20passing-brightgreen.svg)](#tests)
[![Windows](https://img.shields.io/badge/Windows-0078D4?logo=windows&logoColor=white)](https://learn.microsoft.com/)

Send a task from your phone. Pigeon hands it to the **Cline CLI** running on
your own Windows machine, streams the agent's progress back into the chat, and
registers itself into autostart on first run — no console window, no setup
script, no cloud bill.

> 📱 You: *"add type hints to src/api and run the tests"*
> 😴 You: *closes the laptop*
> 🐦 Pigeon: *"✅ Done — exit code 0. 14 files changed."*

📄 **[Full description →](DESCRIPTION.md)** — the problem it solves, how it
works end to end, and the reasoning behind the design.

---

## Why people share it

| | |
|---|---|
| 🏠 **Survives reboots** | Installs its own Task Scheduler entry, restarts on crash |
| 🪟 **Truly invisible** | Runs under `pythonw.exe` — no window, no tray icon, no noise |
| 🧠 **Remembers the thread** | Follow-up messages continue the same agent session |
| 🛑 **Actually stops** | Kills the whole process tree, not just the parent |
| 🔒 **Allowlisted** | Unknown chats get silence, not access |
| 🪶 **Zero lock-in** | Delete the folder and nothing else breaks |

## Setup

### 1. Install the agent

```powershell
npm install -g @cline/cli
clite auth
```

Pick a provider. The `cline` provider needs a credit balance; without one the
agent returns `Insufficient balance`.

### 2. Install Pigeon

```powershell
git clone https://github.com/<you>/pigeon.git
cd pigeon
pip install -r requirements.txt
```

Requires Python 3.10+ on Windows.

### 3. Create the bot

Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token into
`config.json`:

```json
"telegram_bot_token": "123456:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

Or keep the token off disk entirely by setting the `CLINE_BOT_TOKEN`
environment variable, which takes priority over the file.

### 4. Lock it down

```json
"pairing_code": "pick-something-long",
"default_cwd": "C:\\Users\\You\\Projects\\my-app",
"default_mode": "act"
```

`plan` only reads and analyses. `act` lets the agent edit files.

### 5. Run

```powershell
python run_bot.py
```

Send `/pair pick-something-long` to your bot. **Pigeon installs itself into
autostart at this moment** — nothing else to configure.

## Commands

| Command | Effect |
|---|---|
| *any text* | prompt for the agent |
| `/cd <path>` | change working directory (resets the session) |
| `/mode plan\|act` | `plan` analyses only, `act` may edit files |
| `/new` | force a fresh session |
| `/status` | directory, mode, session id, busy state |
| `/stop` | cancel the running task |
| `/history` | recent agent sessions |
| `/sessions` | list sessions you can continue, with their ids |
| `/use <id>` | continue an existing session from this machine |
| `/screen` | send a screenshot of your desktop |
| `/type <text>` | type into the focused window |
| `/key <ENTER\|TAB\|ESC>` | send a keystroke |
| `/shell <cmd>` | run a PowerShell command (60 s cap) |
| `/approve on\|off` | toggle automatic tool approval |
| `/new` | forget the remembered conversation turns |

## How it works

```
   📱 Telegram                    🖥️ Your Windows machine
   ┌──────────────┐              ┌─────────────────────────────────────┐
   │  "add type   │              │  Pigeon (pythonw, no window)       │
   │   hints and  │ ──polling──► │        │                            │
   │   run tests" │              │        ▼                            │
   └──────────────┘              │  ClineClient                        │
        ▲                        │        │                            │
        │   streamed output      │        ▼                            │
        └────────────────────────│  clite --cwd <dir> "<prompt>"       │
                                 │        │                            │
                                 │        ▼                            │
                                 │  Cline agent edits files,          │
                                 │  runs tests, reports               │
                                 └─────────────────────────────────────┘
```

Long polling means no public port, no tunnel and no inbound firewall rule.
The prompt is passed to the CLI's Node entry point as an argument list, never
a shell string, so emoji and non-Latin text survive intact.

Pigeon remembers the whole conversation of each chat, on disk, so it survives a
restart. The CLI cannot resume a session without a TTY, and a bot is always
pipes, so each run is a fresh CLI session with the previous exchanges replayed
into the prompt. `/sessions` and `/use <id>` do the same for a session that
already exists on the machine.

`/screen`, `/type` and `/key` expose the desktop: a screenshot of the virtual
screen, typing into the focused window, and sending keystrokes.

## Security

Pigeon runs commands on your machine — that is the product. Treat the token
like a password.

**Controls**

- **Chat allowlist.** Only ids in `allowed_chat_ids` get a reply. Everyone else
  is ignored silently.
- **Pairing code.** A new chat must present it once. Remove `pairing_code`
  from the config afterwards.
- **No secrets in the repo.** `config.json` is git-ignored; the token can live
  in an environment variable.
- **No shell injection.** Prompts go in as an argument list, never a command
  string. Tested against `&`, `|`, `&&`, `%VARIABLE%` and quote-breakout.
- **Real termination.** `/stop` kills the process tree. Cancelling the task
  alone would leave the agent running.
- **Bounded output.** A runaway agent cannot exhaust memory or flood the chat.
- **Session ownership.** The bot resumes only sessions it created, so it
  cannot hijack one you started in your own terminal.

**Limits**

- `/shell` runs arbitrary PowerShell, gated by the allowlist but **not
  sandboxed**. Do not add strangers.
- The agent runs with your Windows user privileges — no container, no VM.
- The token is a bearer credential. Revoke it via @BotFather if it leaks.

## Configuration

| Key | Meaning |
|---|---|
| `telegram_bot_token` | Token from BotFather, or use `CLINE_BOT_TOKEN` |
| `allowed_chat_ids` | Only these chats get a reply |
| `pairing_code` | Code for `/pair`, `null` disables pairing |
| `default_cwd` | Directory the agent works in |
| `default_mode` | `act` or `plan` |
| `auto_approve` | Let the agent approve its own tools |
| `timeout_seconds` | Maximum length of a single task |
| `shell_timeout_seconds` | Limit for `/shell` |
| `thinking_level` | `none`, `low`, `medium`, `high`, `xhigh` |
| `clite_command` | Path to the Cline CLI |
| `max_message_length` | Chunk size for outgoing messages |
| `log_file` | Where to write logs |

## Architecture

```
run_bot.py                  entry point
config.json                 settings
cline_bot/
├── app.py                  composition root, starts polling
├── autostart.py            Task Scheduler registration
├── config.py               loading and validation
├── authorization.py        allowlist and pairing
├── session_registry.py     per-chat state
├── conversation_log.py    durable chat history
├── cline_client.py         process control
├── polling.py              polling lifecycle (Python 3.12+ compatible)
├── handlers.py             Telegram handlers
├── text_utils.py           pure text helpers
└── logging_setup.py        rotating logs
tests/                      105 unit tests
```

Two rules keep it maintainable: `ClineClient` is the only module that spawns a
process, and handlers never touch process APIs directly — they orchestrate,
the client executes.

Autostart uses `Register-ScheduledTask` rather than `schtasks`, because
`schtasks /Create` requires elevation even for a per-user logon task.

`polling.py` drives the polling lifecycle through the async API instead of
`Application.run_polling`, which calls `asyncio.get_event_loop()` and fails on
Python 3.12 and newer with `RuntimeError: There is no current event loop`.

## Tests

```powershell
python -m unittest discover -s tests -t .
```

105 tests, no network required. They cover output decoding, process
termination, the output cap, allowlist and pairing logic, autostart script
generation, the polling lifecycle, and config validation.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `Insufficient balance` | The `cline` provider has no credits. Run `clite auth <other>`. |
| Bot never answers | Check `logs/bot.log`. Unauthorized chats are ignored by design. |
| Nothing after `/pair` | `pairing_code` is `null`, or the code is wrong. |
| Not starting after reboot | `Get-ScheduledTask -TaskName PigeonTelegramBot` |
| Agent refuses to work | Provider not authenticated. Run `clite auth`. |

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall_autostart.ps1
```

Removes the scheduled task and stops the process. Remove the agent itself with
`npm uninstall -g @cline/cli`.

## License

MIT

