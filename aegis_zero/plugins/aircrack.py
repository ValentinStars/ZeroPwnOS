from __future__ import annotations

import re

from aegis_zero.menu import MenuItem
from aegis_zero.plugins.base import PluginContext, ToolPlugin
from aegis_zero.state import AppMode


class AircrackPlugin(ToolPlugin):
    plugin_id = "aircrack"
    menu_title = "Aircrack Suite"

    def __init__(self, interface: str = "wlan0", monitor_suffix: str = "mon") -> None:
        self.interface = interface
        self.monitor_suffix = monitor_suffix

    def menu_root(self) -> MenuItem:
        return MenuItem(
            title=self.menu_title,
            submenu=[
                MenuItem("One-Tap Monitor", action="plugin.aircrack.toggle_monitor"),
                MenuItem("Stop Monitor", action="plugin.aircrack.stop_monitor"),
                MenuItem("Sync Status", action="plugin.aircrack.sync_status"),
                MenuItem("+ Handshake", action="plugin.aircrack.handshake_inc"),
            ],
        )

    async def handle_action(self, action: str, ctx: PluginContext) -> bool:
        if not action.startswith("plugin.aircrack."):
            return False

        if action == "plugin.aircrack.toggle_monitor":
            if ctx.state.flags.monitor_mode:
                await self._stop_monitor(ctx)
            else:
                await self._start_monitor(ctx)
            return True

        if action == "plugin.aircrack.stop_monitor":
            await self._stop_monitor(ctx)
            return True

        if action == "plugin.aircrack.sync_status":
            await self._sync_status(ctx)
            return True

        if action == "plugin.aircrack.handshake_inc":
            ctx.state.flags.handshake_count += 1
            ctx.state.header_message = "HANDSHAKE++"
            return True

        return False

    async def _start_monitor(self, ctx: PluginContext) -> None:
        ctx.terminal.push_system(f"Enabling monitor mode on {self.interface}")
        ctx.state.flags.active_scan = True
        rc, out = await ctx.run_command(["airmon-ng", "start", self.interface])
        ctx.state.flags.active_scan = False

        if rc != 0:
            ctx.terminal.push_system("airmon-ng start failed")
            ctx.state.last_error = out.strip()[-120:]
            return

        monitor_iface = self._extract_monitor_interface(out) or f"{self.interface}{self.monitor_suffix}"
        ctx.state.monitor_interface = monitor_iface
        ctx.state.flags.monitor_mode = True
        ctx.state.header_message = f"MON:{monitor_iface}"
        ctx.set_mode(AppMode.SCANNING)
        ctx.terminal.push_system(f"Monitor mode enabled: {monitor_iface}")

    async def _stop_monitor(self, ctx: PluginContext) -> None:
        target = ctx.state.monitor_interface or f"{self.interface}{self.monitor_suffix}"
        ctx.terminal.push_system(f"Disabling monitor mode on {target}")
        rc, out = await ctx.run_command(["airmon-ng", "stop", target])
        if rc != 0:
            ctx.state.last_error = out.strip()[-120:]
            ctx.terminal.push_system("airmon-ng stop failed")
            return

        ctx.state.flags.monitor_mode = False
        ctx.state.monitor_interface = None
        ctx.state.header_message = "MON:OFF"
        ctx.set_mode(AppMode.IDLE)
        ctx.terminal.push_system("Monitor mode disabled")

    async def _sync_status(self, ctx: PluginContext) -> None:
        iface = ctx.state.monitor_interface or f"{self.interface}{self.monitor_suffix}"
        rc, out = await ctx.run_command(["iw", "dev"])
        if rc != 0:
            ctx.terminal.push_system("Failed to query iw dev")
            return

        if iface in out:
            ctx.state.flags.monitor_mode = True
            ctx.state.monitor_interface = iface
            ctx.state.header_message = f"MON:{iface}"
        else:
            ctx.state.flags.monitor_mode = False
            ctx.state.monitor_interface = None
            ctx.state.header_message = "MON:OFF"

    @staticmethod
    def _extract_monitor_interface(output: str) -> str | None:
        pattern1 = re.search(r"\bon\s+\[([a-zA-Z0-9_]+)\]", output)
        if pattern1:
            return pattern1.group(1)
        pattern2 = re.search(r"\b([a-zA-Z0-9_]+mon)\b", output)
        if pattern2:
            return pattern2.group(1)
        return None
