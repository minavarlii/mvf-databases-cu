"""Capture reproducibility metadata for MVF experiments."""

from __future__ import annotations

import asyncio
import json
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import text

from backend.app.db import database_manager


@dataclass(frozen=True, slots=True)
class EnvironmentMetadata:
    """Describe the host and MariaDB environment used for an experiment."""

    os: str
    os_release: str
    architecture: str
    processor: str
    python_version: str
    mariadb_version: str
    machine_model: str | None = None
    machine_identifier: str | None = None
    chip: str | None = None
    memory: str | None = None


def _mac_hardware() -> dict[str, str | None]:
    """Return macOS hardware metadata when system_profiler is available."""
    if platform.system() != "Darwin":
        return {}

    try:
        completed = subprocess.run(
            ["system_profiler", "SPHardwareDataType", "-json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        payload = json.loads(completed.stdout)
        rows = payload.get("SPHardwareDataType") or []
        if not rows:
            return {}

        hardware = rows[0]
        return {
            "machine_model": hardware.get("machine_name"),
            "machine_identifier": hardware.get("machine_model"),
            "chip": hardware.get("chip_type")
            or hardware.get("cpu_type")
            or hardware.get("current_processor_speed"),
            "memory": hardware.get("physical_memory"),
        }
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {}


def _read_text(path: Path) -> str | None:
    """Read one small system metadata file, returning None when unavailable."""
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _linux_hardware() -> dict[str, str | None]:
    """Return Linux CPU, VM/model and memory metadata from proc/sysfs."""
    if platform.system() != "Linux":
        return {}

    vendor = _read_text(Path("/sys/devices/virtual/dmi/id/sys_vendor"))
    product = _read_text(Path("/sys/devices/virtual/dmi/id/product_name"))

    machine_model: str | None
    if vendor and product:
        machine_model = f"{vendor} {product}"
    else:
        machine_model = product or vendor

    chip: str | None = None
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                chip = line.split(":", 1)[1].strip() or None
                break
    except OSError:
        pass

    memory: str | None = None
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                parts = line.split()
                if len(parts) >= 2:
                    kib = int(parts[1])
                    gib = kib / (1024 * 1024)
                    memory = f"{gib:.2f} GiB ({kib} KiB)"
                break
    except (OSError, ValueError):
        pass

    return {
        "machine_model": machine_model,
        "machine_identifier": None,
        "chip": chip,
        "memory": memory,
    }


async def collect_environment() -> EnvironmentMetadata:
    """Collect host, hardware, Python, and MariaDB version metadata."""
    async with database_manager.session() as session:
        mariadb_version = await session.scalar(text("SELECT VERSION()"))

    hardware = _mac_hardware() or _linux_hardware()
    chip = hardware.get("chip")
    processor = platform.processor() or chip or "unknown"

    return EnvironmentMetadata(
        os=platform.system(),
        os_release=platform.release(),
        architecture=platform.machine(),
        processor=processor,
        python_version=sys.version.split()[0],
        mariadb_version=str(mariadb_version or "unknown"),
        machine_model=hardware.get("machine_model"),
        machine_identifier=hardware.get("machine_identifier"),
        chip=chip,
        memory=hardware.get("memory"),
    )


async def async_main() -> None:
    """Print environment metadata as JSON."""
    try:
        environment = await collect_environment()
        print(json.dumps(asdict(environment), indent=2))
    finally:
        await database_manager.dispose()


def main() -> None:
    """Run the environment metadata command."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
