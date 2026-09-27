# 🐦 Pigeon

### The carrier pigeon for your coding agent. Send it from the bus. Collect a green build on the way home.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-51%20passing-brightgreen.svg)](#tests)
[![Windows](https://img.shields.io/badge/Windows- supported-0078D4?logo=windows)](https://learn.microsoft.com/)

**Telegram ↔ [Cline CLI](https://github.com/cline/cline) bridge for Windows.**
Type a message, the agent works on your machine in the background, and the
progress streams back into the chat. Pigeon registers itself into Windows
autostart on first run, so it is always home before you are.

> 📱 You: *"add type hints to src/api and run the tests"*
> 😴 You: *sleeps*
> 🐦 Pigeon: *"Done — exit code 0. 14 files changed."*

**No console window. No syntax to learn. No cloud bill.** Just a chat window
and a coding agent that keeps working after you close the laptop.

---

## Why people are sharing it

| | |
|---|---|
| 🏠 **Survives reboots** | Installs its own Task Scheduler entry, restarts on crash |
| 🪟 **Truly invisible** | Runs under `pythonw.exe` — no window, no tray icon, no noise |
| 🧠 **Remembers the thread** | Follow-up messages continue the same agent session |
| 🛑 **Actually stops** | Kills the whole process tree, not just the parent |
| 🔒 **Allowlisted** | Unknown chats get silence, not access |
| 🪶 **Zero lock-in** | Pure stdlib bridge. Delete the folder, nothing else breaks |

## Install

```powershell
git clone https://github.com/<you>/pigeon.git
cd pigeon
pip install -r requirements.txt
npm install -g @cline/cli          # the agent brain
clite auth                          # pick a provider
```

Put your [BotFather](https://t.me/BotFather) token in `config.json`:

```json
"telegram_bot_token": "123456:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

Add a pairing code, then launch:

```json
"pairing_code": "pick-something-long"
```

```powershell
python run_bot.py
```

Send `/pair pick-something-long` to your bot. **Pigeon installs itself into
autostart at this moment** — nothing else to configure.

> Prefer not to keep the token on disk? Set the `CLINE_BOT_TOKEN` environment
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
├── autostart.py           Task Scheduler registration (PowerShell)
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

### Why PowerShell and not `schtasks`

`schtasks /Create` demands elevation even for a per-user logon task, so the bot
could not install itself on a standard account. `Register-ScheduledTask`
succeeds with the rights a normal user already has. Tests assert the generated
script, including that Windows path separators are not escaped.

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
| **Output cap** | 400 KB ceiling; a runaway agent cannot exhaust memory or flood the chat. Truncating also stops the process, otherwise a full pipe would block forever. |
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

51 tests, no network required. They cover the decoding path, process
termination, the output cap, allowlist and pairing logic, autostart script
generation, and config validation.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Insufficient balance` | The `cline` provider has no credits. Run `clite auth <other-provider>`. |
| Bot silent | Check `logs/bot.log`. Unauthorized chats get no reply by design. |
| Not starting after reboot | `Get-ScheduledTask -TaskName PigeonTelegramBot` |
| Nothing happens on `/pair` | `pairing_code` is `null`, or wrong code. |

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall_autostart.ps1
```

## Publishing

### About (short description, 80 chars visible)

```
🐦 Carrier pigeon for your coding agent. Cline CLI over Telegram, on Windows.
```

Alternates if you want a different angle:

| Angle | Caption |
|---|---|
| Benefit | `Send it a task from your phone. Wake up to a finished build.` |
| Technical | `Telegram ↔ Cline CLI bridge for Windows. Installs its own autostart.` |
| Bold | `Your coding agent, delivered. No console window, no cloud bill.` |
| Playful | `A bird that carries your refactors. Telegram + Cline CLI on Windows.` |

### Repository topics

```
telegram-bot  cline  cline-cli  ai-agent  coding-agent
ai-coding-assistant  automation  remote-execution  windows  python
chatops  devtools  self-hosted
```

### Launch post

> **Pigeon 🐦 — I stopped babysitting my coding agent.**
>
> I wanted to kick off a refactor from my phone, close the laptop, and find a
> finished build waiting for me. So I built a bridge: you message a Telegram
> bot, it drives the Cline CLI on your Windows machine, and the progress
> streams back into the chat.
>
> - 📱 Any message is a prompt — no syntax to learn
> - 🏠 Installs itself into Windows autostart on first run
> - 🪟 Runs under `pythonw.exe` — no console window, no tray icon
> - 🧠 Follow-up messages continue the same agent session
> - 🛑 `/stop` kills the whole process tree, not just the parent
> - 🔒 Chat allowlist + pairing code; unknown chats get silence
>
> Windows, Python 3.10+, MIT. 51 tests, no cloud bill.
> [github.com/&lt;you&gt;/pigeon](https://github.com/&lt;you&gt;/pigeon)

---

## License

MIT
