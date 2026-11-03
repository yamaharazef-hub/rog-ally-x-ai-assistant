#!/usr/bin/env python3
"""Read-only system reports for the guarded terminal actions.

No shell is used. This file is invoked only with a fixed mode name from
actions.SAFE_COMMANDS, never with arbitrary user text.
"""
from __future__ import annotations

import os
import platform
import shlex
import shutil
import socket
import subprocess
import sys
from pathlib import Path

MODES = {"status", "battery", "temperature", "network", "updates", "processes"}


def human_bytes(number: float) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    for unit in units:
        if abs(number) < 1024 or unit == units[-1]:
            return f"{number:.1f} {unit}"
        number /= 1024
    return f"{number:.1f} TiB"


def read_text(path: Path, default: str = "unknown") -> str:
    try:
        return path.read_text(encoding="utf-8").strip() or default
    except OSError:
        return default


def os_release() -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                result[key.strip()] = value.strip().strip('"')
    except OSError:
        pass
    return result


def run_argv(argv: list[str], timeout: int = 5, limit: int = 30) -> str:
    pretty = "$ " + shlex.join(argv) + "\n"
    if not shutil.which(argv[0]):
        return pretty + f"(not installed: {argv[0]})"
    try:
        proc = subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=timeout, check=False)
        lines = (proc.stdout + proc.stderr).splitlines()[:limit]
        return pretty + "\n".join(lines) + (f"\nexit={proc.returncode}" if proc.returncode else "")
    except subprocess.TimeoutExpired:
        return pretty + f"(timed out after {timeout}s)"
    except OSError as exc:
        return pretty + f"(error: {exc})"


def battery_report() -> str:
    supplies = sorted(Path("/sys/class/power_supply").glob("*"))
    lines: list[str] = []
    for supply in supplies:
        supply_type = read_text(supply / "type", "")
        if supply_type != "Battery":
            continue
        capacity = read_text(supply / "capacity", "?")
        status = read_text(supply / "status", "unknown")
        health = read_text(supply / "health", "")
        power = read_text(supply / "power_now", "")
        extra = []
        if health and health != "unknown":
            extra.append(f"health={health}")
        if power.isdigit():
            extra.append(f"draw={int(power) / 1_000_000:.1f} W")
        lines.append(f"{supply.name}: {capacity}% • {status}" + (f" • {' • '.join(extra)}" if extra else ""))
    return "\n".join(lines) if lines else "No battery was detected (desktop/AC-only session)."


def status_report() -> str:
    release = os_release()
    uname = platform.uname()
    uptime = "unknown"
    try:
        seconds = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
        days, rem = divmod(int(seconds), 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        uptime = f"{days}d {hours}h {minutes}m"
    except (OSError, ValueError, IndexError):
        pass
    meminfo: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, value = line.split(":", 1)
            meminfo[key.strip()] = int(value.strip().split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    total = meminfo.get("MemTotal", 0)
    available = meminfo.get("MemAvailable", 0)
    used = max(0, total - available)
    disk = shutil.disk_usage(Path.home())
    return "\n".join(
        [
            f"Host      : {socket.gethostname()} ({uname.machine})",
            f"OS        : {release.get('PRETTY_NAME', uname.system + ' ' + uname.release)}",
            f"Kernel    : {uname.release}",
            f"Desktop   : {os.environ.get('XDG_CURRENT_DESKTOP', 'unknown')} / {os.environ.get('WAYLAND_DISPLAY', os.environ.get('DISPLAY', 'unknown'))}",
            f"Uptime    : {uptime}",
            f"CPU       : {os.cpu_count() or 'unknown'} logical cores",
            f"Memory    : {human_bytes(used)} used of {human_bytes(total)} ({used / total * 100 if total else 0:.0f}%)",
            f"Home disk : {human_bytes(disk.used)} used of {human_bytes(disk.total)} ({disk.used / disk.total * 100 if disk.total else 0:.0f}%)",
            "Battery   : " + battery_report().replace("\n", " | "),
        ]
    )


def temperature_report() -> str:
    zones = sorted(Path("/sys/class/thermal").glob("thermal_zone*")) if Path("/sys/class/thermal").exists() else []
    lines = []
    for zone in zones:
        raw = read_text(zone / "temp", "")
        if not raw.lstrip("-").isdigit():
            continue
        celsius = int(raw) / 1000
        name = read_text(zone / "type", zone.name)
        lines.append(f"{name}: {celsius:.1f} °C")
    return "\n".join(lines[:20]) if lines else "No thermal zones are exposed on this system."


def network_report() -> str:
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_UNSPEC)
        addresses = sorted({item[4][0] for item in infos})
    except OSError:
        addresses = []
    wireless = read_text(Path("/proc/net/wireless"), "")
    wifi_lines = [line.strip() for line in wireless.splitlines()[2:] if line.strip()]
    return "\n".join(
        [
            f"Hostname  : {socket.gethostname()}",
            "Addresses : " + (", ".join(addresses) if addresses else "unavailable"),
            "Wi-Fi     : " + (" | ".join(wifi_lines) if wifi_lines else "no /proc/net/wireless data"),
            "",
            run_argv(["ip", "-brief", "address"], limit=20),
        ]
    )


def updates_report() -> str:
    release = os_release()
    parts = [f"Image: {release.get('PRETTY_NAME', 'unknown OS')}", ""]
    parts.append(run_argv(["rpm-ostree", "status"], timeout=8, limit=25))
    parts.append("")
    parts.append(run_argv(["flatpak", "list", "--app", "--columns=name,application"], timeout=8, limit=20))
    return "\n".join(parts)


def processes_report() -> str:
    return run_argv(["ps", "-eo", "pid,comm,%cpu,%mem", "--sort=-%cpu"], timeout=5, limit=13)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    if mode not in MODES:
        print(f"Unknown report mode: {mode}. Choose from {', '.join(sorted(MODES))}.", file=sys.stderr)
        return 2
    reports = {
        "status": status_report,
        "battery": battery_report,
        "temperature": temperature_report,
        "network": network_report,
        "updates": updates_report,
        "processes": processes_report,
    }
    print(reports[mode]())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
