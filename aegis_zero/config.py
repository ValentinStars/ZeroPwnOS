from __future__ import annotations

from dataclasses import dataclass, field
import os


@dataclass(slots=True)
class DisplayConfig:
    width: int = 128
    height: int = 64
    header_height: int = 16
    fps: int = 25
    i2c_port: int = 1
    i2c_address: int = 0x3C


@dataclass(slots=True)
class GPIOConfig:
    up: int = 5
    down: int = 6
    left: int = 13
    right: int = 19
    center: int = 26
    back: int = 20
    action: int = 21
    debounce_ms: int = 120


@dataclass(slots=True)
class AppConfig:
    display: DisplayConfig = field(default_factory=DisplayConfig)
    gpio: GPIOConfig = field(default_factory=GPIOConfig)
    wifi_interface: str = "wlan0"
    monitor_suffix: str = "mon"
    keyboard_device: str | None = None
    battery_adc_path: str | None = None

    @classmethod
    def from_env(cls) -> "AppConfig":
        display = DisplayConfig(
            width=int(os.getenv("AEGIS_WIDTH", "128")),
            height=int(os.getenv("AEGIS_HEIGHT", "64")),
            header_height=int(os.getenv("AEGIS_HEADER_HEIGHT", "16")),
            fps=int(os.getenv("AEGIS_FPS", "25")),
            i2c_port=int(os.getenv("AEGIS_I2C_PORT", "1")),
            i2c_address=int(os.getenv("AEGIS_I2C_ADDR", "0x3C"), 16),
        )
        gpio = GPIOConfig(
            up=int(os.getenv("AEGIS_GPIO_UP", "5")),
            down=int(os.getenv("AEGIS_GPIO_DOWN", "6")),
            left=int(os.getenv("AEGIS_GPIO_LEFT", "13")),
            right=int(os.getenv("AEGIS_GPIO_RIGHT", "19")),
            center=int(os.getenv("AEGIS_GPIO_CENTER", "26")),
            back=int(os.getenv("AEGIS_GPIO_BACK", "20")),
            action=int(os.getenv("AEGIS_GPIO_ACTION", "21")),
            debounce_ms=int(os.getenv("AEGIS_GPIO_DEBOUNCE_MS", "120")),
        )
        return cls(
            display=display,
            gpio=gpio,
            wifi_interface=os.getenv("AEGIS_WIFI_IFACE", "wlan0"),
            monitor_suffix=os.getenv("AEGIS_MON_SUFFIX", "mon"),
            keyboard_device=os.getenv("AEGIS_KEYBOARD_DEVICE"),
            battery_adc_path=os.getenv("AEGIS_BATTERY_ADC_PATH"),
        )
