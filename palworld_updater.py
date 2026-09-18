"""Check for Palworld updates and write a Discord-friendly status message."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
STATUS_PATH = ROOT / "palworld_update_status.txt"
LOG_PATH = ROOT / "palworld_update_output.log"


def load_env() -> None:
    load_dotenv(ROOT / ".env", override=False)


def get_server_install_dir() -> Path | None:
    load_env()
    server_exe = os.getenv("SERVER_EXE_PATH", "").strip()
    if server_exe:
        path = Path(server_exe)
        folder = path.parent if path.suffix.lower() in (".exe", ".sh") or "palserver" in path.name.lower() else path
        if folder.exists():
            return folder

    candidates = [
        os.getenv("SERVER_EXE_PATH", ""),
        r"C:\Program Files (x86)\Steam\steamapps\common\PalServer\PalServer.exe",
        r"C:\PalServer\PalServer.exe",
        r"C:\Palworld\PalServer.exe",
        str(Path.home() / "Steam" / "steamapps" / "common" / "PalServer" / "PalServer.sh"),
        str(Path.home() / ".steam" / "steam" / "steamapps" / "common" / "PalServer" / "PalServer.sh"),
        str(Path.home() / "palworld" / "PalServer.sh"),
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\PalServer"),
        Path(r"C:\PalServer"),
        Path(r"C:\Palworld"),
        Path.home() / "Steam" / "steamapps" / "common" / "PalServer",
        Path.home() / ".steam" / "steam" / "steamapps" / "common" / "PalServer",
        Path.home() / "palworld",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        exe_path = Path(candidate)
        if exe_path.exists():
            return exe_path.parent
    for folder in candidates:
        if folder.exists():
            return folder
    return None


def get_updater_command() -> str | None:
    load_env()

    configured = os.getenv("PALWORLD_UPDATER_CMD", "").strip()
    if configured:
        return configured

    steamcmd_candidates: list[Path] = []
    which_cmd = shutil.which("steamcmd")
    if which_cmd:
        steamcmd_candidates.append(Path(which_cmd))

    steamcmd_candidates.extend([
        Path(r"C:\steamcmd\steamcmd.exe"),
        Path(r"C:\Program Files (x86)\SteamCMD\steamcmd.exe"),
        Path.home() / "steamcmd" / "steamcmd.sh",
        Path.home() / ".local" / "share" / "Steam" / "steamcmd" / "steamcmd.sh",
        Path("/usr/games/steamcmd"),
        Path("/usr/bin/steamcmd"),
    ])

    steamcmd_exe: Path | None = None
    for cand in steamcmd_candidates:
        if cand.exists():
            steamcmd_exe = cand
            break

    if not steamcmd_exe:
        return None

    install_dir = get_server_install_dir()
    if install_dir:
        return (
            f'"{steamcmd_exe}" +force_install_dir "{install_dir}" '
            f"+login anonymous +app_update 2394010 validate +quit"
        )

    return f'"{steamcmd_exe}" +login anonymous +app_update 2394010 validate +quit'


def parse_version(text: str) -> str | None:
    patterns = [
        r"(?i)update\s+to\s+version\s+([^\r\n]+)",
        r"(?i)updated\s+to\s+version\s+([^\r\n]+)",
        r"(?i)version\s+([0-9][^\r\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = match.group(1).strip(" \t\r\n").strip("'")
            if value:
                return value
    return None


def get_installed_build_id() -> str:
    """Read the installed build ID from Steam's appmanifest file."""
    load_env()
    install_dir = get_server_install_dir()

    manifest_paths: list[Path] = []
    if install_dir:
        manifest_paths.append(install_dir.parent.parent / "appmanifest_2394010.acf")
        manifest_paths.append(install_dir / "steamapps" / "appmanifest_2394010.acf")

    manifest_paths.extend([
        Path(r"C:\Program Files (x86)\Steam\steamapps\appmanifest_2394010.acf"),
        Path(r"C:\Steam\steamapps\appmanifest_2394010.acf"),
        Path(r"C:\steamcmd\steamapps\appmanifest_2394010.acf"),
        Path.home() / ".steam" / "steam" / "steamapps" / "appmanifest_2394010.acf",
        Path.home() / "Steam" / "steamapps" / "appmanifest_2394010.acf",
        ROOT / "steamapps" / "appmanifest_2394010.acf",
    ])

    for manifest_path in manifest_paths:
        if not manifest_path.exists():
            continue
        try:
            text = manifest_path.read_text(encoding="utf-8", errors="ignore")
            match = re.search(r'"buildid"\s*"([^"]+)"', text)
            if match:
                return match.group(1)
        except OSError:
            pass

    return "unknown"


def write_status(message: str) -> None:
    STATUS_PATH.write_text(message, encoding="utf-8")


def ensure_server_stopped() -> None:
    """Ensure no PalServer processes are locking game files during update."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/IM", "PalServer.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        subprocess.run(
            ["taskkill", "/F", "/IM", "PalServer-Win64-Shipping-Cmd.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        subprocess.run(
            ["pkill", "-f", "PalServer"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def run_updater(command: str) -> tuple[int, str]:
    command_text = command.strip()
    LOG_PATH.write_text("", encoding="utf-8")

    # Stop any running server instances to prevent file locking (error 0x602 / exit 8)
    ensure_server_stopped()

    try:
        if os.name == "nt":
            completed = subprocess.run(command_text, shell=True, capture_output=True, text=True, check=False)
        else:
            args = shlex.split(command_text)
            completed = subprocess.run(args, capture_output=True, text=True, check=False)
    except Exception as exc:  # pragma: no cover - defensive path
        return 1, str(exc)

    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    try:
        LOG_PATH.write_text(output, encoding="utf-8")
    except OSError:
        pass

    return completed.returncode, output


def main() -> int:
    command = get_updater_command()
    if not command:
        print("No Palworld updater configured or steamcmd not found; skipping update check.")
        return 0

    old_build = get_installed_build_id()
    print(f"Running Palworld updater: {command}")
    return_code, output = run_updater(command)

    if return_code != 0:
        if old_build != "unknown":
            status = f"Update check failed (exit {return_code}), continuing with build {old_build}."
        else:
            status = f"Update check failed (exit {return_code}), continuing launch."
        write_status(status)
        print(status)
        return 0

    new_build = get_installed_build_id()
    if old_build != "unknown" and new_build != "unknown" and new_build != old_build:
        status = f"Updated Palworld server: build {old_build} ➔ {new_build}!"
        write_status(status)
        print(status)
        return 0

    if "fully installed" in output.lower() or "downloading update" in output.lower():
        status = f"Palworld server update applied (build {new_build})."
        write_status(status)
        print(status)
        return 0

    if old_build != "unknown":
        status = f"Palworld server is up to date (build {old_build})."
    else:
        status = "Palworld server is up to date."
    write_status(status)
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
