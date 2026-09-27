# Pigeon 🐦

**Control your Cline CLI coding agent from Telegram. Send a task from your
phone, Pigeon runs it on your Windows machine in the background, streams the
progress back into the chat, and installs itself into autostart on first run.**

---

## The problem

Modern coding agents are powerful, but they are tied to the machine they run
on. You start a refactor, wait for it, watch the terminal. If you close the
laptop the work stops. If you want to check on it you have to be at the desk.

That breaks the way people actually work. The interesting part of a long agent
run — the twenty minutes where it is grepping, editing and running tests — is
exactly the part where you are doing something else.

## The idea

Pigeon is a small bridge between a chat app and your local coding agent.

You send a message. Pigeon hands that text to the Cline CLI running on your
own machine, in the directory you chose, and streams what the agent does back
into the conversation. Then it gets out of the way: the process keeps running
under `pythonw.exe` with no window, survives reboots, and starts again if it
crashes.

You no longer babysit the agent. You dispatch it.

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

**Receiving.** Pigeon uses Telegram long polling, so it needs no public port,
no tunnel and no inbound firewall rule. A single chat message is a prompt.

**Running.** The prompt is passed to `clite` as an argument list — never a
shell string — so message text cannot escape into the command interpreter. The
process runs with your Windows user privileges, in the directory you set with
`/cd`.

**Streaming.** The output of the agent is read line by line and posted back to
the chat. A status message refreshes every three seconds while the agent is
busy, and the final result is sent when it exits.

**Remembering.** After each run Pigeon records the session id the CLI created.
Your next message resumes that same session, so the agent remembers what it
was doing and you can say *"now do the same for the tests"* without repeating
context.

## Setup

### 1. Install the agent

```powershell
npm install -g @cline/cli
clite auth
```

Pick a provider. The `cline` provider requires a credit balance; without one
the agent returns `Insufficient balance`.

### 2. Install Pigeon

```powershell
git clone https://github.com/<you>/pigeon.git
cd pigeon
pip install -r requirements.txt
```

Requires Python 3.10+ on Windows.

### 3. Create the Telegram bot

Open [@BotFather](https://t.me/BotFather) in Telegram, send `/newbot`, and copy
the token you receive. Put it in `config.json`:

```json
"telegram_bot_token": "123456:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

To keep the token out of the file entirely, set the `CLINE_BOT_TOKEN`
environment variable instead. It takes priority over `config.json`.

### 4. Lock it down

Add a pairing code and choose where the agent should work:

```json
"pairing_code": "pick-something-long",
"default_cwd": "C:\\Users\\You\\Projects\\my-app",
"default_mode": "act"
```

`plan` only reads and analyses. `act` allows the agent to edit files. Start
with `plan` if you want to see how it behaves.

### 5. Run it

```powershell
python run_bot.py
```

Send `/pair pick-something-long` to your bot. That is the whole setup.

**At this moment Pigeon registers itself into Windows Task Scheduler** as a
logon task, running `pythonw.exe` with no console window, restarting
automatically on failure. You never run an installer and never touch Task
Scheduler yourself.

## Commands

| Command | Effect |
|---|---|
| *any text* | Send this as a prompt to the agent |
| `/cd <path>` | Change the working directory, resets the session |
| `/mode plan\|act` | `plan` analyses only, `act` may edit files |
| `/new` | Force a fresh session on the next prompt |
| `/status` | Show directory, mode, session id, busy state |
| `/stop` | Cancel the running task |
| `/history` | List recent agent sessions |
| `/shell <cmd>` | Run a PowerShell command, 60 second limit |
| `/approve on\|off` | Toggle automatic tool approval |

## Configuration

Everything lives in `config.json`.

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

## Security

Pigeon executes commands on your machine because that is the product. Treat
the token like a password.

**What it does**

- **Chat allowlist.** Only ids in `allowed_chat_ids` receive a response.
  Everyone else is ignored silently.
- **Pairing code.** A new chat must present the code once before it is added.
  Remove `pairing_code` from the config after pairing.
- **No secrets in the repository.** `config.json` is git-ignored, and the
  token can live in an environment variable instead.
- **No shell injection.** Prompts are passed as an argument list, never
  interpolated into a command string. This was tested against `&`, `|`, `&&`,
  `%VARIABLE%` and quote-breakout payloads.
- **Real termination.** `/stop` kills the entire process tree. Cancelling the
  awaiting task alone would leave the agent running.
- **Bounded output.** A runaway agent cannot exhaust memory or flood the chat;
  output is capped and the process is stopped when the cap is reached.
- **Session ownership.** The bot only resumes sessions it created itself, so
  it cannot attach to a session you started in your own terminal.

**What it does not do**

- `/shell` runs arbitrary PowerShell. It is gated by the allowlist, not
  sandboxed. Do not add strangers to the bot.
- The agent runs with your Windows user privileges. There is no container, no
  VM and no permission reduction.
- The Telegram token is a bearer credential. Revoke it through @BotFather if
  it ever leaks.

## How it is built

```
run_bot.py                  entry point
config.json                 settings
cline_bot/
├── app.py                  composition root, starts polling
├── autostart.py            Task Scheduler registration
├── config.py               loading and validation
├── authorization.py        allowlist and pairing
├── session_registry.py     per-chat state
├── cline_client.py         process control
├── handlers.py             Telegram handlers
├── text_utils.py           pure text helpers
└── logging_setup.py        rotating logs
tests/                      87 unit tests
```

Two rules keep it maintainable: `ClineClient` is the only module that spawns a
process, and handlers never touch process APIs directly — they orchestrate,
the client executes.

Autostart uses PowerShell's `Register-ScheduledTask` rather than `schtasks`,
because `schtasks /Create` requires elevation even for a per-user logon task,
while the cmdlet works with the rights an ordinary account already has.

## Tests

```powershell
python -m unittest discover -s tests -t .
```

87 tests, no network access required. They cover output decoding, process
termination, the output cap, allowlist and pairing logic, autostart script
generation, and configuration validation.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `Insufficient balance` | The `cline` provider has no credits. Run `clite auth <other>`. |
| Bot never answers | Check `logs/bot.log`. Unauthorized chats are ignored by design. |
| Nothing after `/pair` | `pairing_code` is `null`, or the code is wrong. |
| Does not start after reboot | `Get-ScheduledTask -TaskName PigeonTelegramBot` |
| Agent refuses to work | The provider is not authenticated. Run `clite auth`. |

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall_autostart.ps1
```

Removes the scheduled task and stops the running process. The agent itself
stays installed; remove it with `npm uninstall -g @cline/cli`.

## License

MIT

| `log_file` | Where to write logs |

