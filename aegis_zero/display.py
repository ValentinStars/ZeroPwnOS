from __future__ import annotations

import asyncio
import math
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from aegis_zero.config import DisplayConfig
from aegis_zero.menu import MenuItem
from aegis_zero.state import AppState

try:
    from luma.core.interface.serial import i2c  # type: ignore
    from luma.oled.device import ssd1306  # type: ignore
except Exception:  # noqa: BLE001
    i2c = None
    ssd1306 = None


class DisplayManager:
    def __init__(self, cfg: DisplayConfig) -> None:
        self.cfg = cfg
        self.device = None
        self.emulated = False
        self._font = ImageFont.load_default()
        self._font_mono = ImageFont.load_default()

    async def initialize(self) -> None:
        if i2c is None or ssd1306 is None:
            self.emulated = True
            return
        try:
            serial = i2c(port=self.cfg.i2c_port, address=self.cfg.i2c_address)
            self.device = ssd1306(serial, width=self.cfg.width, height=self.cfg.height)
        except Exception:  # noqa: BLE001
            self.emulated = True

    async def boot_animation(self, title: str = "AEGIS-ZERO") -> None:
        steps = 30
        for idx in range(steps):
            image = Image.new("1", (self.cfg.width, self.cfg.height), 0)
            draw = ImageDraw.Draw(image)
            progress = (idx + 1) / steps
            bar_width = int((self.cfg.width - 4) * progress)
            draw.text((2, 4), title, font=self._font_mono, fill=1)
            draw.text((2, 16), "INIT PENTEST CORE", font=self._font, fill=1)
            draw.rectangle((2, 31, self.cfg.width - 2, 40), outline=1, fill=0)
            draw.rectangle((3, 32, 3 + bar_width, 39), outline=1, fill=1)
            sweep_y = 48 + int(8 * math.sin(idx * 0.55))
            draw.line((0, sweep_y, self.cfg.width - 1, sweep_y), fill=1)
            draw.text((2, 54), f"BOOT {int(progress * 100):02d}%", font=self._font, fill=1)
            self._flush(image)
            await asyncio.sleep(0.035)

    def render(
        self,
        state: AppState,
        menu_items: list[MenuItem],
        selected_index: int,
        menu_transition: float,
        terminal_lines: list[str],
        terminal_focus: bool,
    ) -> None:
        image = Image.new("1", (self.cfg.width, self.cfg.height), 0)
        draw = ImageDraw.Draw(image)

        self._draw_header(draw, state)
        if terminal_focus:
            self._draw_terminal(draw, terminal_lines)
        else:
            self._draw_menu(draw, menu_items, selected_index, menu_transition)
        self._draw_rssi_sparkline(draw, state.rssi_history)
        self._flush(image)

    def _draw_header(self, draw: ImageDraw.ImageDraw, state: AppState) -> None:
        w = self.cfg.width
        hh = self.cfg.header_height
        draw.rectangle((0, 0, w - 1, hh - 1), outline=1, fill=0)
        draw.line((0, hh, w - 1, hh), fill=1)

        status = (
            f"CPU {state.metrics.cpu_load_pct:2.0f}% "
            f"RAM {state.metrics.ram_used_pct:2.0f}% "
            f"T {state.metrics.temperature_c:2.0f}C"
        )
        draw.text((1, 0), status[:27], font=self._font, fill=1)

        battery = "--"
        if state.metrics.battery_pct is not None:
            battery = f"{state.metrics.battery_pct:2.0f}%"
        flags = (
            f"M:{'1' if state.flags.monitor_mode else '0'} "
            f"V:{'1' if state.flags.vpn_enabled else '0'} "
            f"S:{'1' if state.flags.active_scan else '0'} "
            f"H:{state.flags.handshake_count} "
            f"B:{battery}"
        )
        draw.text((1, 8), flags[:27], font=self._font, fill=1)

    def _draw_menu(
        self,
        draw: ImageDraw.ImageDraw,
        menu_items: list[MenuItem],
        selected_index: int,
        menu_transition: float,
    ) -> None:
        if not menu_items:
            draw.text((2, self.cfg.header_height + 4), "No menu items", font=self._font, fill=1)
            return

        row_h = 11
        max_rows = 3
        y_start = self.cfg.header_height + 2

        window_start = 0
        if selected_index >= max_rows:
            window_start = selected_index - max_rows + 1

        visible = menu_items[window_start : window_start + max_rows]
        x_offset = int(menu_transition * 18)
        for rel, item in enumerate(visible):
            absolute_index = window_start + rel
            y = y_start + rel * row_h
            selected = absolute_index == selected_index
            if selected:
                draw.rectangle((0, y, self.cfg.width - 1, y + row_h - 1), outline=1, fill=1)
                draw.text((2 + x_offset, y + 1), item.title[:21], font=self._font_mono, fill=0)
            else:
                draw.text((2 + x_offset, y + 1), item.title[:21], font=self._font_mono, fill=1)

    def _draw_terminal(self, draw: ImageDraw.ImageDraw, lines: list[str]) -> None:
        y = self.cfg.header_height + 2
        for line in lines:
            draw.text((1, y), line[:26], font=self._font_mono, fill=1)
            y += 9
            if y >= self.cfg.height - 8:
                break

    def _draw_rssi_sparkline(self, draw: ImageDraw.ImageDraw, rssi_points: Iterable[int]) -> None:
        points = list(rssi_points)
        if len(points) < 2:
            return
        graph_height = 7
        y_bottom = self.cfg.height - 1
        y_top = y_bottom - graph_height
        x_start = 0
        width = self.cfg.width

        normalized = [self._normalize_rssi(v) for v in points[-width:]]
        coords = []
        for idx, val in enumerate(normalized):
            x = x_start + idx
            y = y_bottom - int((val / 100) * graph_height)
            y = max(y_top, min(y_bottom, y))
            coords.append((x, y))
        if len(coords) >= 2:
            draw.line(coords, fill=1)

    @staticmethod
    def _normalize_rssi(dbm: int) -> int:
        clamped = max(-95, min(-30, dbm))
        return int((clamped + 95) / 65 * 100)

    def _flush(self, image: Image.Image) -> None:
        if self.device is not None:
            self.device.display(image)
