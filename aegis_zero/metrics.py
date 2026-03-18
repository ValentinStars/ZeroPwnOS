from __future__ import annotations

import asyncio
import os
import re
from typing import Optional

from aegis_zero.state import AppState

try:
    import psutil  # type: ignore
except Exception:  # noqa: BLE001
    psutil = None


class MetricsCollector:
    def __init__(self, state: AppState, wifi_interface: str, battery_adc_path: str | None = None) -> None:
        self.state = state
        self.wifi_interface = wifi_interface
        self.battery_adc_path = battery_adc_path

    async def run(self, stop_event: asyncio.Event) -> None:
        """Background collector for CPU/RAM/temp/battery and RSSI sparkline data."""
        while not stop_event.is_set():
            await self._collect_once()
            await asyncio.sleep(1.0)

    async def _collect_once(self) -> None:
        self.state.metrics.cpu_load_pct = self._cpu_load()
        self.state.metrics.ram_used_pct = self._ram_used()
        self.state.metrics.temperature_c = self._temperature_c()
        self.state.metrics.battery_pct = self._battery_pct()

        rssi = await self._read_rssi_dbm()
        if rssi is not None:
            self.state.push_rssi(rssi)

        self.state.touch()

    def _cpu_load(self) -> float:
        if psutil is not None:
            return float(psutil.cpu_percent(interval=None))
        try:
            load1, _, _ = os.getloadavg()
            cores = os.cpu_count() or 1
            return max(0.0, min(100.0, (load1 / cores) * 100.0))
        except OSError:
            return 0.0

    def _ram_used(self) -> float:
        if psutil is not None:
            return float(psutil.virtual_memory().percent)

        try:
            total = 0
            available = 0
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        total = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        available = int(line.split()[1])
            if total <= 0:
                return 0.0
            used = total - available
            return max(0.0, min(100.0, (used / total) * 100.0))
        except OSError:
            return 0.0

    def _temperature_c(self) -> float:
        if psutil is not None:
            try:
                temps = psutil.sensors_temperatures() or {}
                for entries in temps.values():
                    if entries:
                        return float(entries[0].current)
            except Exception:  # noqa: BLE001
                pass

        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r", encoding="utf-8") as f:
                return float(f.read().strip()) / 1000.0
        except OSError:
            return 0.0

    def _battery_pct(self) -> Optional[float]:
        if not self.battery_adc_path:
            return None
        try:
            with open(self.battery_adc_path, "r", encoding="utf-8") as f:
                raw = float(f.read().strip())
            return max(0.0, min(100.0, raw))
        except (OSError, ValueError):
            return None

    async def _read_rssi_dbm(self) -> Optional[int]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "iw",
                "dev",
                self.wifi_interface,
                "link",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception:  # noqa: BLE001
            return None

        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return None

        text = stdout.decode("utf-8", errors="replace")
        match = re.search(r"signal:\s*(-?\d+)\s*dBm", text)
        if not match:
            return None

        return int(match.group(1))
