# palworld_bot

Discord companion for a Windows-hosted Palworld dedicated server. Two pieces in one bot:

1. **Logger** - on startup, launches `PalServer.exe` (or a `.bat` wrapping it) as a subprocess
   and streams its console output into a Discord channel.
2. **Listener** - watches a control channel for a plain-text `!restart` command (real slash
   commands require Discord app verification/registration, so this uses a normal message
   instead) from an allow-listed user ID and reboots the Windows host with `shutdown /r`.

## Setup

1. Create a virtual environment (`python -m venv palworld_env`)
2. Activate it (`palworld_env\Scripts\activate` on Windows)
3. Install dependencies (`python -m pip install -r requirements.pip`)
4. Copy `.env.example` to `.env` and fill in:
   - `DISCORD_TOKEN` - bot token from the Discord Developer Portal
   - `LOG_CHANNEL_ID` / `CONTROL_CHANNEL_ID` - right-click a channel with Developer Mode on
   - `ALLOWED_USER_IDS` - comma-separated Discord user IDs allowed to restart the machine
   - `SERVER_EXE_PATH` - full path to `PalServer.exe`
5. In the Discord Developer Portal, enable the **Message Content Intent** for the bot.
6. Copy `start_palworld_bot.bat` into `shell:startup` so it launches on boot alongside
   the server.

## Notes

- Restart is guarded by an allow-list; anyone else typing `!restart` in the control
  channel gets told they're not authorized.
- On non-Windows machines, the restart trigger just prints a dry-run message instead of
  calling `shutdown`, so the bot can be tested on macOS/Linux.
- Console output is batched and flushed every couple seconds (or once close to Discord's
  2000-char message limit) to avoid rate limits.
