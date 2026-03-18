from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from aegis_zero.config import GPIOConfig

try:
    import RPi.GPIO as GPIO  # type: ignore
except Exception:  # noqa: BLE001
    GPIO = None

try:
    from evdev import InputDevice, categorize, ecodes, list_devices  # type: ignore
except Exception:  # noqa: BLE001
    InputDevice = None
    categorize = None
    ecodes = None
    list_devices = None


@dataclass(slots=True)
class InputEvent:
    kind: str
    value: str = ""


class InputManager:
    def __init__(self, gpio_cfg: GPIOConfig, keyboard_device: str | None = None) -> None:
        self.gpio_cfg = gpio_cfg
        self.keyboard_device = keyboard_device
        self.queue: asyncio.Queue[InputEvent] = asyncio.Queue(maxsize=256)
        self._tasks: list[asyncio.Task[None]] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_gpio_ts: dict[int, float] = {}
        self._running = False
        self._gpio_ready = False
        self._gpio_poll_mode = False
        self._gpio_mapping: dict[int, str] = {}
        self._gpio_last_level: dict[int, int] = {}

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._running = True
        self._setup_gpio()
        if self._gpio_poll_mode:
            self._tasks.append(asyncio.create_task(self._gpio_poll_loop(), name="gpio-poll"))
        self._tasks.append(asyncio.create_task(self._keyboard_loop(), name="keyboard-loop"))

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

        if GPIO is not None and self._gpio_ready:
            GPIO.cleanup()

    async def get(self) -> InputEvent:
        return await self.queue.get()

    def emit(self, kind: str, value: str = "") -> None:
        if not self._loop:
            return
        event = InputEvent(kind=kind, value=value)

        def _put() -> None:
            if self.queue.full():
                try:
                    self.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            self.queue.put_nowait(event)

        self._loop.call_soon_threadsafe(_put)

    def _setup_gpio(self) -> None:
        if GPIO is None:
            return

        mapping = {
            self.gpio_cfg.up: "nav_up",
            self.gpio_cfg.down: "nav_down",
            self.gpio_cfg.left: "nav_left",
            self.gpio_cfg.right: "nav_right",
            self.gpio_cfg.center: "select",
            self.gpio_cfg.back: "back",
            self.gpio_cfg.action: "action",
        }
        self._gpio_mapping = mapping

        GPIO.setmode(GPIO.BCM)
        for pin in mapping:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self._gpio_last_level[pin] = GPIO.input(pin)

        def callback(pin: int) -> None:
            now = time.monotonic()
            last = self._last_gpio_ts.get(pin, 0.0)
            if (now - last) * 1000 < self.gpio_cfg.debounce_ms:
                return
            self._last_gpio_ts[pin] = now
            kind = mapping.get(pin)
            if kind:
                self.emit(kind)

        edge_failed = False
        for pin in mapping:
            try:
                GPIO.add_event_detect(
                    pin,
                    GPIO.FALLING,
                    callback=callback,
                    bouncetime=self.gpio_cfg.debounce_ms,
                )
            except RuntimeError:
                edge_failed = True
                break

        if edge_failed:
            for pin in mapping:
                try:
                    GPIO.remove_event_detect(pin)
                except RuntimeError:
                    pass
            self._gpio_poll_mode = True

        self._gpio_ready = True

    async def _gpio_poll_loop(self) -> None:
        if GPIO is None:
            return
        debounce_s = max(0.01, self.gpio_cfg.debounce_ms / 1000)
        while self._running:
            now = time.monotonic()
            for pin, kind in self._gpio_mapping.items():
                try:
                    level = GPIO.input(pin)
                except RuntimeError:
                    continue
                prev = self._gpio_last_level.get(pin, 1)
                self._gpio_last_level[pin] = level
                if prev == 1 and level == 0:
                    last = self._last_gpio_ts.get(pin, 0.0)
                    if now - last >= debounce_s:
                        self._last_gpio_ts[pin] = now
                        self.emit(kind)
            await asyncio.sleep(0.01)

    async def _keyboard_loop(self) -> None:
        if InputDevice is None or list_devices is None or ecodes is None or categorize is None:
            return

        device = self._resolve_keyboard_device()
        if device is None:
            return

        try:
            async for event in device.async_read_loop():
                if not self._running:
                    break
                if event.type != ecodes.EV_KEY or event.value != 1:
                    continue
                key_data = categorize(event)
                keycode = key_data.keycode
                if isinstance(keycode, list):
                    keycode = keycode[0]
                self._map_key(keycode)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            return

    def _resolve_keyboard_device(self) -> InputDevice | None:
        if InputDevice is None or list_devices is None or ecodes is None:
            return None

        if self.keyboard_device:
            try:
                return InputDevice(self.keyboard_device)
            except OSError:
                return None

        for path in list_devices():
            try:
                dev = InputDevice(path)
                caps = dev.capabilities()
                if ecodes.EV_KEY in caps and "keyboard" in dev.name.lower():
                    return dev
            except OSError:
                continue
        return None

    def _map_key(self, keycode: str) -> None:
        nav_map = {
            "KEY_UP": "nav_up",
            "KEY_DOWN": "nav_down",
            "KEY_LEFT": "nav_left",
            "KEY_RIGHT": "nav_right",
            "KEY_ENTER": "select",
            "KEY_ESC": "back",
            "KEY_SPACE": "text",
            "KEY_BACKSPACE": "backspace",
            "KEY_TAB": "action",
        }
        if keycode in nav_map:
            kind = nav_map[keycode]
            if kind == "text":
                self.emit("text", " ")
            else:
                self.emit(kind)
            return

        text = _keycode_to_text(keycode)
        if text:
            self.emit("text", text)


def _keycode_to_text(code: str) -> str:
    if not code.startswith("KEY_"):
        return ""
    token = code[4:]
    if len(token) == 1 and token.isalnum():
        return token.lower()
    mapping = {
        "MINUS": "-",
        "EQUAL": "=",
        "DOT": ".",
        "SLASH": "/",
        "BACKSLASH": "\\",
        "COMMA": ",",
        "SEMICOLON": ";",
        "APOSTROPHE": "'",
        "LEFTBRACE": "[",
        "RIGHTBRACE": "]",
    }
    return mapping.get(token, "")
