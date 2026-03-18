from __future__ import annotations

import asyncio
from contextlib import suppress

from aegis_zero.config import AppConfig
from aegis_zero.display import DisplayManager
from aegis_zero.input import InputEvent, InputManager
from aegis_zero.menu import MenuController, MenuItem
from aegis_zero.metrics import MetricsCollector
from aegis_zero.plugins import AircrackPlugin, PluginContext, PluginManager
from aegis_zero.state import AppMode, AppState, StateMachine
from aegis_zero.terminal import MiniTerminal


class AegisZeroApp:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.state = AppState(wifi_interface=cfg.wifi_interface)
        self.state_machine = StateMachine(self.state)
        self.terminal = MiniTerminal()
        self.terminal_focus = True

        self.display = DisplayManager(cfg.display)
        self.input = InputManager(cfg.gpio, cfg.keyboard_device)
        self.metrics = MetricsCollector(self.state, cfg.wifi_interface, cfg.battery_adc_path)
        self.plugins = PluginManager()
        self.plugins.register(AircrackPlugin(cfg.wifi_interface, cfg.monitor_suffix))

        self.menu = MenuController(self._build_root_menu())
        self.stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    async def run(self) -> int:
        self.terminal.push_system("Aegis-Zero initialized")
        await self.display.initialize()
        await self.display.boot_animation()
        await self.input.start()

        self._tasks = [
            asyncio.create_task(self.metrics.run(self.stop_event), name="metrics"),
            asyncio.create_task(self._event_loop(), name="event-loop"),
            asyncio.create_task(self._render_loop(), name="render-loop"),
        ]

        await self.stop_event.wait()
        await self._shutdown()
        return 0

    async def _shutdown(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        await self.input.stop()

    def _build_root_menu(self) -> list[MenuItem]:
        plugin_entries = self.plugins.menu_entries()
        return [
            MenuItem(
                "Operations",
                submenu=[
                    MenuItem("Set Idle", action="mode.idle"),
                    MenuItem("Set Scanning", action="mode.scanning"),
                    MenuItem("Set Attacking", action="mode.attacking"),
                    MenuItem("Set Config", action="mode.config"),
                    MenuItem("Reset Counters", action="state.reset"),
                ],
            ),
            *plugin_entries,
            MenuItem("Mini Terminal", action="terminal.open"),
            MenuItem(
                "Config",
                submenu=[
                    MenuItem("Toggle VPN", action="flag.vpn.toggle"),
                    MenuItem("Sync Wi-Fi State", action="plugin.aircrack.sync_status"),
                ],
            ),
            MenuItem(
                "System",
                submenu=[
                    MenuItem("Clear Terminal", action="terminal.clear"),
                    MenuItem("Exit UI", action="app.quit"),
                ],
            ),
        ]

    async def _event_loop(self) -> None:
        while not self.stop_event.is_set():
            event = await self.input.get()
            await self._handle_input(event)

    async def _render_loop(self) -> None:
        frame_time = 1 / max(1, self.cfg.display.fps)
        while not self.stop_event.is_set():
            self.menu.tick()
            lines = self.terminal.render_lines(max_chars=30, max_lines=3)
            self.display.render(
                state=self.state,
                menu_items=self.menu.current_items,
                selected_index=self.menu.selected_index,
                menu_transition=self.menu.page_transition,
                terminal_lines=lines,
                terminal_focus=self.terminal_focus,
            )
            await asyncio.sleep(frame_time)

    async def _handle_input(self, event: InputEvent) -> None:
        kind = event.kind
        if kind == "nav_up":
            self.menu.move(-1)
            return
        if kind == "nav_down":
            self.menu.move(1)
            return
        if kind == "nav_left":
            if self.terminal_focus:
                self.terminal_focus = False
            else:
                self.menu.back()
            return
        if kind == "nav_right":
            action = self.menu.enter()
            if action:
                await self._execute_action(action)
            return
        if kind in {"select", "action"}:
            if self.terminal_focus:
                command = self.terminal.consume_command()
                if command:
                    asyncio.create_task(self._run_terminal_command(command))
                return
            action = self.menu.enter()
            if action:
                await self._execute_action(action)
            return
        if kind == "back":
            if self.terminal_focus:
                self.terminal_focus = False
            else:
                self.menu.back()
            return
        if kind == "backspace":
            if self.terminal_focus:
                self.terminal.backspace()
            return
        if kind == "text":
            if not self.terminal_focus:
                self.terminal_focus = True
            self.terminal.append_input_text(event.value)
            return

    async def _execute_action(self, action: str) -> None:
        if action.startswith("mode."):
            mapping = {
                "mode.idle": AppMode.IDLE,
                "mode.scanning": AppMode.SCANNING,
                "mode.attacking": AppMode.ATTACKING,
                "mode.config": AppMode.CONFIG,
            }
            target = mapping.get(action)
            if target and self.state_machine.transition(target):
                self.terminal.push_system(f"Mode switched to {target.value}")
            return

        if action == "terminal.open":
            self.terminal_focus = not self.terminal_focus
            self.state.header_message = "TERMINAL"
            self.state.touch()
            return

        if action == "terminal.clear":
            self.terminal.clear()
            self.terminal.push_system("Terminal buffer cleared")
            return

        if action == "flag.vpn.toggle":
            self.state.flags.vpn_enabled = not self.state.flags.vpn_enabled
            self.state.header_message = "VPN:ON" if self.state.flags.vpn_enabled else "VPN:OFF"
            self.state.touch()
            return

        if action == "state.reset":
            self.state.flags.handshake_count = 0
            self.state.rssi_history.clear()
            self.state.header_message = "COUNTERS RESET"
            self.state.touch()
            return

        if action == "app.quit":
            self.stop_event.set()
            return

        handled = await self.plugins.dispatch(action, self._plugin_context())
        if not handled:
            self.terminal.push_system(f"Unknown action: {action}")

    async def _run_terminal_command(self, command: str) -> None:
        self.state.flags.active_scan = True
        self.state.touch()
        await self.terminal.run_shell(command)
        self.state.flags.active_scan = False
        self.state.touch()

    def _plugin_context(self) -> PluginContext:
        return PluginContext(
            state=self.state,
            terminal=self.terminal,
            run_command=self._run_exec,
            set_mode=self.state_machine.transition,
        )

    async def _run_exec(self, argv: list[str]) -> tuple[int, str]:
        self.state.flags.active_scan = True
        self.state.touch()
        output = ""
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError:
            output = f"{argv[0]} not found in PATH"
            self.terminal.push_system(output)
            self.state.flags.active_scan = False
            self.state.touch()
            return 127, output
        except Exception as exc:  # noqa: BLE001
            output = str(exc)
            self.terminal.push_system(output)
            self.state.flags.active_scan = False
            self.state.touch()
            return 1, output

        assert proc.stdout is not None
        chunks: list[str] = []
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip("\n")
            chunks.append(text)
            self.terminal.append_output(text)

        rc = await proc.wait()
        output = "\n".join(chunks)
        self.state.flags.active_scan = False
        self.state.touch()
        return rc, output


async def async_main() -> int:
    app = AegisZeroApp(AppConfig.from_env())
    return await app.run()


def main() -> int:
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        return 130
