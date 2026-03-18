from __future__ import annotations

import asyncio
from collections import deque
import textwrap


class MiniTerminal:
    def __init__(self, max_lines: int = 260) -> None:
        self.lines: deque[str] = deque(maxlen=max_lines)
        self.input_buffer: str = ""
        self.busy: bool = False
        self._run_lock = asyncio.Lock()

    def push_system(self, text: str) -> None:
        for line in text.splitlines() or [""]:
            self.lines.append(f"[*] {line}")

    def append_output(self, text: str) -> None:
        parts = text.splitlines()
        if not parts:
            self.lines.append("")
            return
        for line in parts:
            self.lines.append(line)

    def append_input_text(self, text: str) -> None:
        self.input_buffer += text

    def backspace(self) -> None:
        self.input_buffer = self.input_buffer[:-1]

    def clear(self) -> None:
        self.lines.clear()

    def consume_command(self) -> str:
        cmd = self.input_buffer.strip()
        self.input_buffer = ""
        return cmd

    def render_lines(self, max_chars: int, max_lines: int) -> list[str]:
        wrapped: list[str] = []
        for raw in self.lines:
            chunk = textwrap.wrap(
                raw,
                width=max_chars,
                replace_whitespace=False,
                drop_whitespace=False,
            )
            wrapped.extend(chunk or [""])
        cmd_line = f"$ {self.input_buffer}"
        wrapped.extend(
            textwrap.wrap(
                cmd_line,
                width=max_chars,
                replace_whitespace=False,
                drop_whitespace=False,
            )
            or ["$"]
        )
        return wrapped[-max_lines:]

    async def run_shell(self, command: str) -> int:
        async with self._run_lock:
            self.busy = True
            self.lines.append(f"$ {command}")
            try:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
            except Exception as exc:  # noqa: BLE001
                self.lines.append(f"[launch error] {exc}")
                self.busy = False
                return 127

            assert proc.stdout is not None
            while True:
                chunk = await proc.stdout.readline()
                if not chunk:
                    break
                self.append_output(chunk.decode("utf-8", errors="replace").rstrip("\n"))

            code = await proc.wait()
            self.lines.append(f"[exit:{code}]")
            self.busy = False
            return code
