from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
import time


class AppMode(str, Enum):
    IDLE = "Idle"
    SCANNING = "Scanning"
    ATTACKING = "Attacking"
    CONFIG = "Config"


@dataclass(slots=True)
class SystemMetrics:
    cpu_load_pct: float = 0.0
    ram_used_pct: float = 0.0
    temperature_c: float = 0.0
    battery_pct: float | None = None


@dataclass(slots=True)
class RuntimeFlags:
    monitor_mode: bool = False
    vpn_enabled: bool = False
    active_scan: bool = False
    handshake_count: int = 0


@dataclass(slots=True)
class AppState:
    mode: AppMode = AppMode.IDLE
    metrics: SystemMetrics = field(default_factory=SystemMetrics)
    flags: RuntimeFlags = field(default_factory=RuntimeFlags)
    wifi_interface: str = "wlan0"
    monitor_interface: str | None = None
    header_message: str = "BOOT"
    last_error: str = ""
    rssi_history: deque[int] = field(default_factory=lambda: deque(maxlen=48))
    updated_at: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.updated_at = time.monotonic()

    def push_rssi(self, value: int) -> None:
        self.rssi_history.append(value)
        self.touch()


class StateMachine:
    """Simple guardrail state machine for operating modes."""

    _ALLOWED = {
        AppMode.IDLE: {AppMode.SCANNING, AppMode.ATTACKING, AppMode.CONFIG},
        AppMode.SCANNING: {AppMode.IDLE, AppMode.ATTACKING, AppMode.CONFIG},
        AppMode.ATTACKING: {AppMode.IDLE, AppMode.SCANNING, AppMode.CONFIG},
        AppMode.CONFIG: {AppMode.IDLE, AppMode.SCANNING, AppMode.ATTACKING},
    }

    def __init__(self, state: AppState) -> None:
        self.state = state

    def transition(self, next_mode: AppMode) -> bool:
        current = self.state.mode
        if next_mode == current:
            return True
        if next_mode not in self._ALLOWED[current]:
            self.state.last_error = f"Blocked transition: {current.value} -> {next_mode.value}"
            self.state.touch()
            return False
        self.state.mode = next_mode
        self.state.header_message = f"MODE:{next_mode.value.upper()}"
        self.state.touch()
        return True
