"""Shell Channel - stdin/stdout interaction"""

import sys
import anyio
from claude_agent_sdk import AssistantMessage, TextBlock

from channels import Channel, Message, Reply


class ShellChannel(Channel):
    @classmethod
    def is_available(cls) -> bool:
        return sys.stdin.isatty()

    async def receive(self) -> Message:
        text = (await anyio.to_thread.run_sync(
            lambda: input(), abandon_on_cancel=True
        )).strip()
        if text.lower() in ("q", "quit", "exit"):
            raise SystemExit(0)
        return Message("shell", "shell", [{"type": "text", "text": text}])

    async def reply(self, reply: Reply) -> None:
        print("> thinking...", flush=True)
        async for msg in reply.stream:
            if isinstance(msg, AssistantMessage):
                print("".join(b.text for b in msg.content if isinstance(b, TextBlock)), end="", flush=True)
        print()
        print()