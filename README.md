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
   - `SERVER_LOG_PATH` - optional local path for a copy of the server console output
   - `PLAYER_EVENT_PATTERN` - optional case-insensitive regex for possible player login lines
5. Add the bot to the server. In the Discord Developer Portal, open **OAuth2 > URL
   Generator**, select the **bot** scope, select these bot permissions, and open the
   generated URL in a browser. Choose the target server and authorize the install.
   You need **Manage Server** permission (or server ownership) to do this. Afterward,
   the bot should appear in the server's member list, possibly as offline until the
   Python process is running.
   Select these permissions in the generated URL and in the log/control channel
   permissions:
   - **View Channel**
   - **Send Messages**
   - **Read Message History**
   For a private channel, open **Edit Channel > Permissions**, add the bot (or its
   role), and explicitly allow **View Channel**, **Send Messages**, and **Read Message
   History** there. A private-channel overwrite can deny access even when the bot has
   these permissions at the server level. Use the channel's numeric ID, not its name.
6. In the Discord Developer Portal, open **Bot > Privileged Gateway Intents** and enable
   **Message Content Intent**. This is required for the bot to read the plain-text
   `!restart` command; it is separate from channel permissions.
7. Copy `start_palworld_bot.bat` into `shell:startup` so it launches on boot alongside
   the server.

## Notes

- Restart is guarded by an allow-list; anyone else typing `!restart` in the control
  channel gets told they're not authorized.
- On non-Windows machines, the restart trigger just prints a dry-run message instead of
  calling `shutdown`, so the bot can be tested on macOS/Linux.
- Console output is batched and flushed every couple seconds (or once close to Discord's
  2000-char message limit) to avoid rate limits.
- The same server output is also appended to `SERVER_LOG_PATH` (by default,
   `palworld_server.log` beside the bot). Lines matching `PLAYER_EVENT_PATTERN` are printed
   to the bot console as possible player events; adjust the pattern after inspecting the
   actual Palworld connection messages in the log.
- Palworld `joined the server` and `left the server` lines produce concise Discord
   notifications. The earlier `connected the server` line is retained in the raw log but
   does not generate a second notification. Discord notifications include the player name
   only; raw log lines retain the full server output for troubleshooting.
