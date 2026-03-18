from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Awaitable, Callable

from aegis_zero.menu import MenuItem
from aegis_zero.state import AppMode, AppState
from aegis_zero.terminal import MiniTerminal


@dataclass(slots=True)
class PluginContext:
    state: AppState
    terminal: MiniTerminal
    run_command: Callable[[list[str]], Awaitable[tuple[int, str]]]
    set_mode: Callable[[AppMode], bool]


class ToolPlugin(ABC):
    plugin_id: str
    menu_title: str

    @abstractmethod
    def menu_root(self) -> MenuItem:
        raise NotImplementedError

    @abstractmethod
    async def handle_action(self, action: str, ctx: PluginContext) -> bool:
        raise NotImplementedError


class PluginManager:
    def __init__(self) -> None:
        self._plugins: list[ToolPlugin] = []

    def register(self, plugin: ToolPlugin) -> None:
        self._plugins.append(plugin)

    def menu_entries(self) -> list[MenuItem]:
        return [plugin.menu_root() for plugin in self._plugins]

    async def dispatch(self, action: str, ctx: PluginContext) -> bool:
        for plugin in self._plugins:
            handled = await plugin.handle_action(action, ctx)
            if handled:
                return True
        return False
