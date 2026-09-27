# 🛡️ ClineRemote

### Steer Cline from your phone. Sleep through the refactor. Wake up to a green build.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-41%20passing-brightgreen.svg)](#tests)

A Telegram bot that pipes whatever you type straight into the **Cline CLI** on
your Windows machine, streams the agent's progress back into the chat, and
installs itself into Windows autostart on first run.

> Send *"add type hints to src/api"* from the bus, wake up to a reviewed diff.

**Hardened by design.** Chat allowlist, secret-free config, process-tree
termination, output caps, and a session-ownership check so the bot can never
resume someone else's session. See [Security](#security).

---

## What it does

| | |
|---|---|
| 📨 **Any message is a prompt** | No syntax, no commands to learn |
| 📡 **Streams progress live** | Watch the agent work, not a black box |
| 🧠 **Keeps conversation context** | Follow-ups continue the same session |
| 🚀 **Self-installing autostart** | Registers a Task Scheduler entry by itself |
| 🪟 **Fully hidden** | Runs under `pythonw.exe`, no console window |
| 🛑 **Actually stops** | Kills the whole process tree, not just the parent |
| 🔒 **Allowlisted** | Unknown chats get silence |

## Quick start

```powershell
git clone https://github.com/<you>/cline-remote.git
cd cline-remote
pip install -r requirements.txt
npm install -g @cline/cli          # the agent backend
clite auth                          # authorize a provider
```

Put your BotFather token in `config.json`:

```json
"telegram_bot_token": "123456:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

Set a pairing code, then run it:

```json
"pairing_code": "pick-something-long"
```

```powershell
python run_bot.py
```

Send `/pair pick-something-long` to your bot. Done — it now survives reboots.

> Prefer not to store the token on disk? Set the `CLINE_BOT_TOKEN` environment
> variable instead. It takes priority over the file.

## Commands

| Command | Effect |
|---|---|
| *any text* | prompt for the Cline CLI |
| `/cd <path>` | change working directory (resets session) |
| `/mode plan\|act` | `plan` = analyze only, `act` = may edit files |
| `/new` | force a fresh session |
| `/status` | directory, mode, session id, busy flag |
| `/stop` | cancel the running task |
| `/history` | recent Cline sessions |
| `/shell <cmd>` | run a PowerShell command (60 s cap) |
| `/approve on\|off` | auto-approve agent tools |

## Architecture

```
run_bot.py                 entry point
cline_bot/
├── app.py                 composition root + autostart bootstrap
├── autostart.py           Task Scheduler registration
├── config.py              loading + validation
├── authorization.py       allowlist & pairing
├── session_registry.py    per-chat state
├── cline_client.py        process control (ClineRun)
├── handlers.py            Telegram handlers
├── text_utils.py          pure helpers
└── logging_setup.py       rotating logs
```

Two rules keep it maintainable:

1. **`ClineClient` owns every external process.** No other module spawns one.
2. **Handlers never touch `asyncio` process APIs.** They orchestrate; the
   client executes.

## Security

### What this bot is

A remote code execution bridge. It runs commands on your machine from a chat
app. That is the entire point, and it means the security model has to be
serious.

### Controls

| Control | Implementation |
|---|---|
| **Chat allowlist** | Only ids in `allowed_chat_ids` get a reply. Everything else is ignored. |
| **Pairing code** | First contact requires `/pair <code>`. Persisted, then the code should be removed. |
| **No secrets in repo** | `config.json` is git-ignored; token can come from the environment. |
| **Command injection** | Arguments are passed as an argv list, never a shell string. Verified against `&`, `\|`, `&&`, `%VAR%`, and quote-breakout payloads. |
| **Process termination** | `taskkill /T` kills the whole tree. Cancelling a task alone would leak the agent. |
| **Output cap** | 400 KB ceiling; a runaway agent cannot exhaust memory or flood the chat. |
| **Session ownership** | The bot only resumes sessions it created itself, so it cannot hijack a session you started in your own terminal. |

### Honest limitations

- `/shell` executes arbitrary PowerShell for allowlisted chats. It is gated by
  the allowlist, not sandboxed. Do not add strangers.
- Your Telegram token is a bearer credential. Revoke it via @BotFather if it leaks.
- The Cline agent runs with your Windows user privileges. `plan` mode is the
  safe choice for untrusted instructions.

## Tests

```powershell
python -m unittest discover -s tests -t .
```

41 tests, no network required. They cover the decoding path, process
termination, the output cap, allowlist and pairing logic, and config
validation.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Insufficient balance` | The `cline` provider has no credits. Run `clite auth <other-provider>`. |
| Bot silent | Check `logs/bot.log`. Unauthorized chats get no reply by design. |
| Not starting after reboot | `Get-ScheduledTask -TaskName ClineTelegramBot` |
| Nothing happens on `/pair` | `pairing_code` is `null`, or wrong code. |

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall_autostart.ps1
```

## License

MIT
