"""Check for Palworld updates and write a Discord-friendly status message."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATUS_PATH = ROOT / "palworld_update_status.txt"
LOG_PATH = ROOT / "palworld_update_output.log"


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def get_updater_command() -> str | None:
    load_env()

    configured = os.getenv("PALWORLD_UPDATER_CMD", "").strip()
    if configured:
        return configured

    default = r'"C:\steamcmd\steamcmd.exe" +login anonymous +app_update 2394010 validate +quit'
    if Path(r"C:\steamcmd\steamcmd.exe").exists():
        return default

    return None


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


def get_installed_version() -> str:
    candidates = [
        os.getenv("SERVER_EXE_PATH", ""),
        r"C:\PalServer\PalServer.exe",
        r"C:\Palworld\PalServer.exe",
    ]

    for candidate in candidates:
        if not candidate:
            continue
        exe_path = Path(candidate)
        if not exe_path.exists():
            continue
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-Item -LiteralPath '{str(exe_path).replace("'", "''")}').VersionInfo.FileVersion",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            version = result.stdout.strip()
            if version:
                return version
        except Exception:
            pass

    manifest_paths = [
        ROOT / "steamapps" / "appmanifest_2394010.acf",
        Path(r"C:\Steam\steamapps\appmanifest_2394010.acf"),
        Path(r"C:\Program Files (x86)\Steam\steamapps\appmanifest_2394010.acf"),
    ]
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


def run_updater(command: str) -> tuple[int, str]:
    command_text = command.strip()
    LOG_PATH.write_text("", encoding="utf-8")

    try:
        if os.name == "nt" and not command_text.startswith('"'):
            completed = subprocess.run(command_text, shell=True, capture_output=True, text=True, check=False)
        else:
            args = shlex.split(command_text, posix=(os.name != "nt"))
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
        print("No Palworld updater configured; skipping update check.")
        return 0

    print(f"Running Palworld updater: {command}")
    return_code, output = run_updater(command)

    if return_code == 0:
        version = parse_version(output)
        if version:
            write_status(f"Found update, updated to {version}")
            print(f"Found update, updated to {version}")
        else:
            write_status("Found update, updated successfully.")
            print("Found update, updated successfully.")
        return 0

    old_version = get_installed_version()
    if old_version != "unknown":
        write_status(f"Found update, failed, still launching {old_version}")
        print(f"Found update, failed, still launching {old_version}")
    else:
        write_status("Found update, failed, still launching.")
        print("Found update, failed, still launching.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
