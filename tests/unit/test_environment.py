import platform
from pathlib import Path

import pytest

import experiments.environment as environment


def test_linux_hardware_parses_cpu_memory_and_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = {
        "/sys/devices/virtual/dmi/id/sys_vendor": "Microsoft Corporation\n",
        "/sys/devices/virtual/dmi/id/product_name": "Virtual Machine\n",
        "/proc/cpuinfo": (
            "processor : 0\nmodel name : AMD EPYC 9V45 96-Core Processor\n"
        ),
        "/proc/meminfo": ("MemTotal:       16368184 kB\nMemFree:         1000000 kB\n"),
    }

    monkeypatch.setattr(platform, "system", lambda: "Linux")

    def fake_read_text(
        self: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        del encoding, errors
        return files[str(self)]

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    result = environment._linux_hardware()

    assert result["machine_model"] == ("Microsoft Corporation Virtual Machine")
    assert result["chip"] == "AMD EPYC 9V45 96-Core Processor"
    assert result["memory"] == "15.61 GiB (16368184 KiB)"
