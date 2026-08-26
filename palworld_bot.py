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
import os
import platform
import subprocess

import discord
from dotenv import load_dotenv

load_dotenv()

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

    while server_process and server_process.stdout is not None:
        try:
            line = await asyncio.wait_for(server_process.stdout.readline(), timeout=FLUSH_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            line = b""

        if line:
            buffer.append(line.decode(errors="replace").rstrip())

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
    log_channel = client.get_channel(LOG_CHANNEL_ID)
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
    client.run(DISCORD_TOKEN)
