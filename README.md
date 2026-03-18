# Aegis-Zero

Asynchronous pentest GUI environment for Raspberry Pi Zero W + SSD1306 (128x64 bi-color), designed for headless security workflows.

## Features

- Asynchronous architecture (`asyncio`) so rendering does not freeze during CLI tools execution.
- Yellow/Blue screen split:
  - Header (0-16 px): CPU, RAM, temperature, battery, state flags.
  - Workspace (17-64 px): nested menu + mini terminal.
- Input hybrid logic:
  - GPIO controls: 5-way navigation + back + action.
  - Global keyboard input via `evdev`.
- Plugin system: add new tools as classes without touching the core loop.
- Aircrack plugin with one-tap monitor mode (`airmon-ng` wrapper).
- Boot animation and RSSI sparklines.

## Project Structure

```text
.
├── main.py
├── requirements.txt
├── systemd/
│   └── aegis-zero.service
└── aegis_zero/
    ├── app.py
    ├── config.py
    ├── display.py
    ├── input.py
    ├── menu.py
    ├── metrics.py
    ├── state.py
    ├── terminal.py
    └── plugins/
        ├── __init__.py
        ├── aircrack.py
        └── base.py
```

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

## Environment Variables

```bash
AEGIS_WIDTH=128
AEGIS_HEIGHT=64
AEGIS_HEADER_HEIGHT=16
AEGIS_FPS=25
AEGIS_I2C_PORT=1
AEGIS_I2C_ADDR=0x3C

AEGIS_WIFI_IFACE=wlan0
AEGIS_MON_SUFFIX=mon
AEGIS_KEYBOARD_DEVICE=/dev/input/event0
AEGIS_BATTERY_ADC_PATH=/sys/bus/iio/devices/iio:device0/in_voltage0_raw

AEGIS_GPIO_UP=5
AEGIS_GPIO_DOWN=6
AEGIS_GPIO_LEFT=13
AEGIS_GPIO_RIGHT=19
AEGIS_GPIO_CENTER=26
AEGIS_GPIO_BACK=20
AEGIS_GPIO_ACTION=21
AEGIS_GPIO_DEBOUNCE_MS=120
```

## systemd Autostart

1. Copy project to `/opt/aegis-zero`.
2. Edit `systemd/aegis-zero.service` if paths differ.
3. Install and enable:

```bash
sudo cp systemd/aegis-zero.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable aegis-zero.service
sudo systemctl start aegis-zero.service
```

## Notes

- If OLED hardware is unavailable, the app runs in emulated display mode (no crash).
- `airmon-ng` and `iw` must be installed on target device for monitor mode and RSSI features.
- `sudo` or proper capabilities may be required for GPIO and wireless interface commands.
