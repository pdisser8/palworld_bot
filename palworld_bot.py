"""
Palworld dedicated server companion bot.

Responsibilities:
1. Logger - launches the Palworld dedicated server with -log and streams its
   console output into a Discord channel.
2. Safe Lifecycle Manager - handles graceful world saves, in-game warnings,
   clean server-only restarts, and full host reboots.
3. Rich Presence & Status - dynamic Discord activity showing live players and
   connect address, with !status and !save commands.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Optional

import discord
from dotenv import load_dotenv

from network_utils import get_connect_address
from palworld_api import PalworldAPI

# Load .env relative to this file
load_dotenv(Path(__file__).with_name(".env"))

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))
CONTROL_CHANNEL_ID = int(os.getenv("CONTROL_CHANNEL_ID", "0"))
ALLOWED_USER_IDS = {
    int(uid) for uid in os.getenv("ALLOWED_USER_IDS", "").split(",") if uid.strip()
}
RESTART_COMMAND = os.getenv("RESTART_COMMAND", "!restart").strip().lower()
RESTART_DELAY_SECONDS = int(os.getenv("RESTART_DELAY_SECONDS", "30"))
SERVER_EXE_PATH = os.getenv("SERVER_EXE_PATH", "")

# Ensure -log is included in SERVER_ARGS so Unreal Engine emits console output
raw_args = os.getenv("SERVER_ARGS", "").split()
if "-log" not in raw_args:
    raw_args.append("-log")
SERVER_ARGS = raw_args

SERVER_CWD = os.getenv("SERVER_CWD") or (
    os.path.dirname(SERVER_EXE_PATH) if SERVER_EXE_PATH else None
)
SERVER_LOG_PATH = os.getenv("SERVER_LOG_PATH", "palworld_server.log")
UPDATE_STATUS_PATH = Path(__file__).with_name("palworld_update_status.txt")

# REST API & Address settings
PALWORLD_ADMIN_PASSWORD = os.getenv("PALWORLD_ADMIN_PASSWORD", "")
PALWORLD_REST_URL = os.getenv("PALWORLD_REST_URL", "http://127.0.0.1:8212")
SERVER_DISPLAY_ADDRESS = os.getenv("SERVER_DISPLAY_ADDRESS", "")
SERVER_PUBLIC_PORT = int(os.getenv("SERVER_PUBLIC_PORT", "8211"))

PLAYER_EVENT_PATTERN = os.getenv(
    "PLAYER_EVENT_PATTERN", r"login|logged in|joined|connected"
)
PLAYER_JOINED_PATTERN = re.compile(
    r"\[LOG\] (?P<name>.+?) joined the server\. \(User id: [^,)]+",
    re.IGNORECASE,
)
PLAYER_LEFT_PATTERN = re.compile(
    r"\[LOG\] (?P<name>.+?) left the server\. \(User id: [^,)]+",
    re.IGNORECASE,
)

MAX_MESSAGE_CHARS = 1900
FLUSH_INTERVAL_SECONDS = 2

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

api = PalworldAPI(base_url=PALWORLD_REST_URL, admin_password=PALWORLD_ADMIN_PASSWORD)

server_process: asyncio.subprocess.Process | None = None
is_restarting: bool = False
presence_task: asyncio.Task | None = None


async def _flush_buffer(channel: discord.abc.Messageable, buffer: list[str]) -> None:
    if not buffer:
        return
    text = "\n".join(buffer)
    buffer.clear()
    for start in range(0, len(text), MAX_MESSAGE_CHARS):
        chunk = text[start:start + MAX_MESSAGE_CHARS]
        await channel.send(f"```{chunk}```")


async def stream_server_output(channel: discord.abc.Messageable) -> None:
    """Read the server process's stdout and periodically flush it to Discord."""
    global server_process
    buffer: list[str] = []
    last_flush = asyncio.get_event_loop().time()
    log_path = Path(SERVER_LOG_PATH)
    if not log_path.is_absolute():
        log_path = Path(__file__).parent / log_path
    login_pattern = re.compile(PLAYER_EVENT_PATTERN, re.IGNORECASE)

    try:
        with log_path.open("a", encoding="utf-8", errors="replace") as log_file:
            while server_process and server_process.stdout is not None:
                try:
                    line = await asyncio.wait_for(
                        server_process.stdout.readline(), timeout=FLUSH_INTERVAL_SECONDS
                    )
                except asyncio.TimeoutError:
                    line = b""

                if line:
                    decoded_line = line.decode(errors="replace").rstrip()
                    buffer.append(decoded_line)
                    log_file.write(f"{datetime.now().isoformat(timespec='seconds')} {decoded_line}\n")
                    log_file.flush()
                    if login_pattern.search(decoded_line):
                        print(f"Possible player event: {decoded_line}")
                    joined_match = PLAYER_JOINED_PATTERN.search(decoded_line)
                    left_match = PLAYER_LEFT_PATTERN.search(decoded_line)
                    if joined_match:
                        await channel.send(f"✅ **{joined_match['name']}** joined the server.")
                    elif left_match:
                        await channel.send(f"🚪 **{left_match['name']}** left the server.")

                now = asyncio.get_event_loop().time()
                if buffer and (now - last_flush >= FLUSH_INTERVAL_SECONDS or len("\n".join(buffer)) > MAX_MESSAGE_CHARS):
                    await _flush_buffer(channel, buffer)
                    last_flush = now

                if line == b"" and server_process.stdout.at_eof():
                    break

        await _flush_buffer(channel, buffer)
    except Exception as exc:
        print(f"Error in stream_server_output: {exc}")

    if server_process and not is_restarting:
        return_code = await server_process.wait()
        await channel.send(f"🔴 Palworld server process exited (code {return_code}).")
        server_process = None


async def announce_pending_update(channel: discord.abc.Messageable) -> None:
    if not UPDATE_STATUS_PATH.exists():
        return

    try:
        message = UPDATE_STATUS_PATH.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return

    if message:
        await channel.send(f"📦 {message}")

    try:
        UPDATE_STATUS_PATH.unlink()
    except OSError:
        pass


async def launch_server(channel: discord.abc.Messageable) -> None:
    global server_process

    if not SERVER_EXE_PATH:
        await channel.send("⚠️ SERVER_EXE_PATH is not configured, skipping server launch.")
        return

    if server_process is not None and server_process.returncode is None:
        await channel.send("⚠️ Server process already appears to be running.")
        return

    await channel.send("🟢 Starting Palworld dedicated server...")

    server_process = await asyncio.create_subprocess_exec(
        SERVER_EXE_PATH,
        *SERVER_ARGS,
        cwd=SERVER_CWD,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    asyncio.create_task(stream_server_output(channel))


def kill_process_tree(pid: int) -> None:
    """Terminate a process and all of its child processes on Windows."""
    if platform.system() == "Windows":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        # Also clean up any lingering engine processes
        subprocess.run(
            ["taskkill", "/F", "/IM", "PalServer-Win64-Shipping-Cmd.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            subprocess.run(["pkill", "-f", "PalServer"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            os.kill(pid, 9)
        except OSError:
            pass


async def stop_server_process(wait_seconds: int = 15) -> None:
    """Gracefully stop the Palworld server process and ensure it is cleaned up."""
    global server_process

    if server_process is None:
        return

    pid = server_process.pid

    # Attempt shutdown via REST API first
    if api.is_configured:
        await api.shutdown(wait_seconds=3, message="Server stopping...")
        await asyncio.sleep(4)

    # If the process is still running, send terminate
    if server_process.returncode is None:
        try:
            server_process.terminate()
            await asyncio.wait_for(server_process.wait(), timeout=wait_seconds)
        except (asyncio.TimeoutError, Exception):
            if pid:
                kill_process_tree(pid)

    server_process = None


async def run_updater_async() -> str:
    """Run palworld_updater.py asynchronously and return its status message."""
    updater_script = Path(__file__).with_name("palworld_updater.py")
    python_exe = Path(os.sys.executable)

    try:
        proc = await asyncio.create_subprocess_exec(
            str(python_exe),
            str(updater_script),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode(errors="replace").strip()
        if UPDATE_STATUS_PATH.exists():
            try:
                status = UPDATE_STATUS_PATH.read_text(encoding="utf-8").strip()
                UPDATE_STATUS_PATH.unlink()
                return status
            except OSError:
                pass
        return output
    except Exception as exc:
        return f"Failed to run updater: {exc}"


async def execute_server_restart(channel: discord.abc.Messageable, delay_seconds: int) -> None:
    """Graceful server-only restart: warn -> save -> stop -> update -> relaunch."""
    global is_restarting
    is_restarting = True

    try:
        await channel.send(
            f"🔁 Initiating graceful server restart in **{delay_seconds}** seconds..."
        )

        if api.is_configured:
            await api.announce(f"Server restarting in {delay_seconds} seconds! Saving world...")
            saved, save_msg = await api.save_world()
            if saved:
                await channel.send("💾 In-game world save completed.")
            else:
                await channel.send(f"⚠️ World save returned: {save_msg}")

        # Wait with a midway warning if delay is substantial
        if delay_seconds > 10:
            await asyncio.sleep(delay_seconds - 10)
            if api.is_configured:
                await api.announce("Server restarting in 10 seconds!")
            await asyncio.sleep(10)
        else:
            await asyncio.sleep(delay_seconds)

        if api.is_configured:
            await api.save_world()

        await channel.send("⏹️ Stopping Palworld server process...")
        await stop_server_process(wait_seconds=10)

        await channel.send("📦 Checking for Steam updates...")
        update_result = await run_updater_async()
        if update_result:
            await channel.send(f"📦 {update_result}")

        await launch_server(channel)
        await channel.send("✅ Palworld server restart routine completed!")
    finally:
        is_restarting = False


async def update_presence_loop() -> None:
    """Continuously update the bot's Rich Presence with player count and connect address."""
    await client.wait_until_ready()

    while not client.is_closed():
        try:
            connect_str = await get_connect_address(SERVER_DISPLAY_ADDRESS, SERVER_PUBLIC_PORT)

            if server_process is not None and server_process.returncode is None:
                # Try getting live metrics from REST API
                metrics = await api.get_metrics()
                if metrics:
                    cur = metrics.get("currentplayernum", 0)
                    max_p = metrics.get("maxplayernum", 10)
                    activity_text = f"{cur}/{max_p} Players | join at {connect_str}"
                else:
                    players = await api.get_players()
                    if api.is_configured and await api.is_online():
                        activity_text = f"{len(players)} Players | join at {connect_str}"
                    else:
                        activity_text = f"Starting Server... | {connect_str}"

                await client.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.playing,
                        name=activity_text,
                    )
                )
            else:
                await client.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.playing,
                        name="Palworld: Offline 🔴",
                    )
                )
        except Exception as exc:
            print(f"Presence loop exception: {exc}")

        await asyncio.sleep(30)


async def resolve_channel(channel_id: int) -> discord.abc.Messageable | None:
    channel = client.get_channel(channel_id)
    if channel is not None:
        return channel

    try:
        return await client.fetch_channel(channel_id)
    except discord.Forbidden:
        print(
            f"Cannot access channel {channel_id}: the bot needs View Channel permission "
            "in the private channel."
        )
    except discord.NotFound:
        print(f"Channel {channel_id} does not exist, or the ID is incorrect.")
    except discord.HTTPException as exc:
        print(f"Discord rejected channel lookup for {channel_id}: {exc}")
    return None


def trigger_host_restart(delay_seconds: int) -> None:
    if platform.system() == "Windows":
        subprocess.run(
            ["shutdown", "/r", "/t", str(delay_seconds), "/c", "Palworld bot requested restart"],
            check=True,
        )
    else:
        try:
            subprocess.run(["systemctl", "reboot"], check=True)
        except Exception:
            subprocess.run(["shutdown", "-r", "now"], check=True)


@client.event
async def on_ready():
    global presence_task
    print(f"Logged in as {client.user}")

    if presence_task is None or presence_task.done():
        presence_task = asyncio.create_task(update_presence_loop())

    log_channel = await resolve_channel(LOG_CHANNEL_ID)
    if log_channel is None:
        print(f"Could not find LOG_CHANNEL_ID={LOG_CHANNEL_ID}")
        return
    await announce_pending_update(log_channel)
    await launch_server(log_channel)


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    # Check if message is in the control channel
    if message.channel.id != CONTROL_CHANNEL_ID:
        return

    content = message.content.strip()
    cmd = content.lower()

    # --- !status Command ---
    if cmd == "!status":
        connect_str = await get_connect_address(SERVER_DISPLAY_ADDRESS, SERVER_PUBLIC_PORT)
        is_running = server_process is not None and server_process.returncode is None

        embed = discord.Embed(
            title="🎮 Palworld Server Status",
            color=discord.Color.green() if is_running else discord.Color.red(),
            timestamp=datetime.now(),
        )

        if not is_running:
            embed.description = "🔴 **Server is currently offline.**"
            await message.channel.send(embed=embed)
            return

        embed.add_field(name="Status", value="🟢 **Online**", inline=True)
        embed.add_field(name="Connect Address", value=f"`{connect_str}`", inline=True)
        embed.add_field(
            name="Direct Join Link",
            value=f"[Join via Steam](steam://connect/{connect_str})",
            inline=True,
        )

        metrics = await api.get_metrics()
        players = await api.get_players()
        info = await api.get_info()

        cur_players = metrics.get("currentplayernum", len(players)) if metrics else len(players)
        max_players = metrics.get("maxplayernum", 10) if metrics else 10
        embed.add_field(name="Active Players", value=f"**{cur_players} / {max_players}**", inline=True)

        if metrics and "serverfps" in metrics:
            embed.add_field(name="Server FPS", value=f"{metrics['serverfps']:.1f}", inline=True)

        if info and "version" in info:
            embed.add_field(name="Version", value=f"{info['version']}", inline=True)

        if players:
            player_lines = [
                f"• **{p.get('name', 'Unknown')}** (Lvl {p.get('level', '?')}) - Ping: {int(p.get('ping', 0))}ms"
                for p in players[:15]
            ]
            embed.add_field(name="Player Roster", value="\n".join(player_lines), inline=False)
        else:
            embed.add_field(name="Player Roster", value="*No players currently online.*", inline=False)

        await message.channel.send(embed=embed)
        return

    # --- !save Command ---
    if cmd == "!save":
        if message.author.id not in ALLOWED_USER_IDS:
            await message.channel.send(f"🚫 {message.author.mention} you are not authorized to do that.")
            return

        if not api.is_configured:
            await message.channel.send("⚠️ Palworld REST API is not configured in `.env`.")
            return

        saved, save_msg = await api.save_world()
        if saved:
            await message.channel.send("💾 **World save completed successfully!**")
        else:
            await message.channel.send(f"❌ World save failed: {save_msg}")
        return

    # --- !restart Command ---
    if cmd == RESTART_COMMAND or cmd.startswith(f"{RESTART_COMMAND} "):
        if message.author.id not in ALLOWED_USER_IDS:
            await message.channel.send(f"🚫 {message.author.mention} you are not authorized to do that.")
            return

        # Check for !restart host or !restart machine
        parts = cmd.split()
        if len(parts) > 1 and parts[1] in ("host", "machine", "pc", "windows"):
            await message.channel.send(
                f"🖥️ **Host reboot requested** by {message.author.mention}. Saving world and rebooting in {RESTART_DELAY_SECONDS}s..."
            )
            if api.is_configured:
                await api.announce(f"Host machine rebooting in {RESTART_DELAY_SECONDS} seconds! Saving world...")
                await api.save_world()
            try:
                trigger_host_restart(RESTART_DELAY_SECONDS)
            except Exception as exc:
                await message.channel.send(f"❌ Failed to trigger host restart: {exc}")
            return

        # Default: Fast, graceful Palworld server-only restart
        log_channel = await resolve_channel(LOG_CHANNEL_ID) or message.channel
        asyncio.create_task(execute_server_restart(log_channel, RESTART_DELAY_SECONDS))
        return


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set, check your .env file")
    try:
        client.run(DISCORD_TOKEN)
    except discord.LoginFailure as exc:
        raise SystemExit(
            "Discord rejected DISCORD_TOKEN. Copy the current Bot Token from "
            "Developer Portal > Bot, not the Application ID, Public Key, or Client Secret."
        ) from exc
