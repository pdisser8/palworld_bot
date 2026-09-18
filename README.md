# palworld_bot

Discord companion and lifecycle manager for a Palworld dedicated server (supports both **Windows** and **Linux / Pop!_OS**).

---

## Features

1. **Logger & Console Streaming**:
   - Launches `PalServer` with `-log` enabled and streams console output into a Discord channel while writing timestamped entries to disk.
   - Detects player join and leave events.
2. **Safe Server Lifecycle Manager**:
   - `!restart`: Graceful server-only restart (~10–15 seconds):
     - Broadcasts in-game countdown warnings to active players.
     - Performs a safe world save (`/v1/api/save`) via Palworld's native REST API to prevent world save corruption.
     - Gracefully stops the server process and terminates child engine binaries cleanly.
     - Automatically checks Steam for server updates using SteamCMD (`+force_install_dir`).
     - Relaunches the server and resumes log streaming without rebooting the host machine.
   - `!restart host`: Warns players, performs a safe world save, and reboots the host machine (`shutdown /r` on Windows or `systemctl reboot` on Linux).
   - `!save`: Triggers an immediate world save on demand directly from Discord.
3. **Live Rich Presence & Status**:
   - Continuously updates the bot's Discord activity status in the server member list:
     `Playing: 3/10 Players | join at <ip>:<port>`
   - Automatically detects the host's public IPv4 address (or uses your custom domain override from `.env`).
   - `!status`: Displays a clean embed showing server state (🟢 Online / 🔴 Offline), connect address, clickable Steam join link (`steam://connect/...`), server FPS, version, and connected player roster (names, levels, ping).
4. **Reliable SteamCMD Updater**:
   - `palworld_updater.py` automatically resolves the active server directory and applies updates directly via SteamCMD with `+force_install_dir`.
   - Supports SteamCMD on both Windows and Linux.

---

## Commands (Control Channel)

| Command | Permission | Description |
|---|---|---|
| `!status` | Everyone in Control Channel | Shows live server status, player roster, and connection address |
| `!save` | Allowed User IDs | Triggers an immediate world save to disk |
| `!restart` | Allowed User IDs | Fast, safe server-only restart with in-game countdown & world save (~15s) |
| `!restart host` | Allowed User IDs | Host machine reboot with in-game warning & safe world save |

---

## Configuration (`.env`)

Copy `.env.example` to `.env` and configure:

| Variable | Default | Description |
|---|---|---|
| `DISCORD_TOKEN` | *(required)* | Bot token from the Discord Developer Portal |
| `LOG_CHANNEL_ID` | `0` | Discord channel ID where server console output is streamed |
| `CONTROL_CHANNEL_ID` | `0` | Discord channel ID where management commands are accepted |
| `ALLOWED_USER_IDS` | *(required)* | Comma-separated Discord user IDs allowed to run `!save` and `!restart` |
| `SERVER_EXE_PATH` | *(required)* | Path to `PalServer.exe` (Windows) or `PalServer.sh` (Linux) |
| `SERVER_ARGS` | `-log` | Arguments passed to the server executable (keep `-log` for stdout logging) |
| `PALWORLD_ADMIN_PASSWORD` | *(required)* | Matches `AdminPassword` in `PalWorldSettings.ini` for REST API auth |
| `PALWORLD_REST_URL` | `http://127.0.0.1:8212` | Palworld REST API base URL |
| `SERVER_DISPLAY_ADDRESS` | *(optional)* | Custom domain/IP (e.g. `pal.mydomain.com`). If empty, auto-detects public IP |
| `SERVER_PUBLIC_PORT` | `8211` | Public UDP game port used for connection strings |
| `RESTART_COMMAND` | `!restart` | Prefix for the restart command |
| `RESTART_DELAY_SECONDS` | `30` | Countdown seconds warned in-game before restarting |

---

## Palworld Server Settings (`PalWorldSettings.ini`)

Ensure the following options are set in your `PalWorldSettings.ini` (typically located in `Pal/Saved/Config/WindowsServer/` or `LinuxServer/`):

* `AdminPassword="<your_secure_password>"` *(used internally by the bot for REST API authentication)*
* `RESTAPIEnabled=True`
* `RESTAPIPort=8212`
* `ServerPassword=""` *(keep blank so regular players connect without needing a password)*

---

## Discord Developer Portal Setup

1. In **OAuth2 > URL Generator**:
   - Select the **bot** scope.
   - Select permissions: **View Channel**, **Send Messages**, **Embed Links**, **Read Message History**.
   - Open the generated URL in your browser to invite the bot to your Discord server.
2. In **Bot > Privileged Gateway Intents**:
   - Enable **Message Content Intent** (required to read text commands).

---

## Running on Windows

1. Run `start_palworld_bot.bat`. It will:
   - Create and activate `palworld_env` virtual environment if needed.
   - Install required dependencies from `requirements.pip`.
   - Run the updater check.
   - Launch the bot and the Palworld dedicated server.
2. **Auto-start on boot**:
   - Press `Win + R`, type `shell:startup`, and press Enter.
   - Place a shortcut to `start_palworld_bot.bat` inside that folder.

---

## Running on Linux / Pop!_OS

1. Install prerequisites:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-venv python3-pip steamcmd
   ```
2. Set execute permissions and run:
   ```bash
   chmod +x start_palworld_bot.sh
   ./start_palworld_bot.sh
   ```
3. **Run as a systemd background service (Recommended)**:
   Create `/etc/systemd/system/palworld-bot.service`:
   ```ini
   [Unit]
   Description=Palworld Dedicated Server and Discord Bot
   After=network.target

   [Service]
   Type=simple
   User=yourusername
   WorkingDirectory=/home/yourusername/palworld_bot
   ExecStart=/home/yourusername/palworld_bot/start_palworld_bot.sh
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```
   Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now palworld-bot
   ```
   View logs anytime with:
   ```bash
   journalctl -u palworld-bot -f
   ```
