from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MenuItem:
    title: str
    action: str | None = None
    submenu: list["MenuItem"] = field(default_factory=list)
    description: str = ""


class MenuController:
    def __init__(self, root_items: list[MenuItem]) -> None:
        self._menu_stack: list[list[MenuItem]] = [root_items]
        self._index_stack: list[int] = [0]
        self.page_transition: float = 0.0

    @property
    def depth(self) -> int:
        return len(self._menu_stack)

    @property
    def selected_index(self) -> int:
        return self._index_stack[-1]

    @property
    def current_items(self) -> list[MenuItem]:
        return self._menu_stack[-1]

    def move(self, delta: int) -> None:
        items = self.current_items
        if not items:
            return
        idx = self._index_stack[-1]
        self._index_stack[-1] = (idx + delta) % len(items)

    def selected_item(self) -> MenuItem | None:
        items = self.current_items
        if not items:
            return None
        idx = self.selected_index
        if idx >= len(items):
            self._index_stack[-1] = 0
            idx = 0
        return items[idx]

    def enter(self) -> str | None:
        item = self.selected_item()
        if not item:
            return None
        if item.submenu:
            self._menu_stack.append(item.submenu)
            self._index_stack.append(0)
            self.page_transition = 1.0
            return None
        return item.action

    def back(self) -> bool:
        if len(self._menu_stack) == 1:
            return False
        self._menu_stack.pop()
        self._index_stack.pop()
        self.page_transition = -1.0
        return True

    def tick(self) -> None:
        if abs(self.page_transition) < 0.03:
            self.page_transition = 0.0
            return
        self.page_transition *= 0.72
