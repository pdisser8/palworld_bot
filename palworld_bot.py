"""
Palworld dedicated server companion bot.

Two responsibilities:
1. Logger - launches the Palworld dedicated server exe and streams its
   console output into a Discord channel.
2. Listener - watches a control channel for a plain-text "!restart" command
   (not a slash command) from an allow-listed user and reboots the Windows
   host it's running on.
"""

import asyncio
from datetime import datetime
import os
import platform
import re
import subprocess
from pathlib import Path

import discord
from dotenv import load_dotenv

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
SERVER_ARGS = os.getenv("SERVER_ARGS", "").split()
SERVER_CWD = os.getenv("SERVER_CWD") or (
    os.path.dirname(SERVER_EXE_PATH) if SERVER_EXE_PATH else None
)
SERVER_LOG_PATH = os.getenv("SERVER_LOG_PATH", "palworld_server.log")
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

MAX_MESSAGE_CHARS = 1900  # leave headroom for the ``` code fence
FLUSH_INTERVAL_SECONDS = 2

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

server_process: asyncio.subprocess.Process | None = None


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

    if server_process:
        return_code = await server_process.wait()
        await channel.send(f"🔴 Palworld server process exited (code {return_code}).")
        server_process = None


async def launch_server(channel: discord.abc.Messageable) -> None:
    global server_process

    if not SERVER_EXE_PATH:
        await channel.send("⚠️ SERVER_EXE_PATH is not configured, skipping server launch.")
        return

    if server_process is not None:
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


def trigger_windows_restart(delay_seconds: int) -> None:
    if platform.system() != "Windows":
        print(f"[dry-run] would run: shutdown /r /t {delay_seconds}")
        return
    subprocess.run(
        ["shutdown", "/r", "/t", str(delay_seconds), "/c", "Palworld bot requested restart"],
        check=True,
    )


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    log_channel = await resolve_channel(LOG_CHANNEL_ID)
    if log_channel is None:
        print(f"Could not find LOG_CHANNEL_ID={LOG_CHANNEL_ID}")
        return
    await launch_server(log_channel)


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return
    if message.channel.id != CONTROL_CHANNEL_ID:
        return
    if message.content.strip().lower() != RESTART_COMMAND:
        return

    if message.author.id not in ALLOWED_USER_IDS:
        await message.channel.send(f"🚫 {message.author.mention} you are not authorized to do that.")
        return

    await message.channel.send(
        f"🔁 Restarting the host in {RESTART_DELAY_SECONDS} seconds, requested by {message.author.mention}."
    )
    try:
        trigger_windows_restart(RESTART_DELAY_SECONDS)
    except Exception as exc:  # noqa: BLE001 - surface any failure to Discord
        await message.channel.send(f"❌ Failed to trigger restart: {exc}")


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
