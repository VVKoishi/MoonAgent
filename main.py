"""MoonAgent - Main entry point"""

import argparse
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage
from dotenv import load_dotenv

from channels import Channel, Reply, get_all_channels

load_dotenv(Path(__file__).parent / ".env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_AGENT_OPTIONS = ClaudeAgentOptions(
    system_prompt={"type": "preset", "preset": "claude_code"},
    model="sonnet",
    effort="medium",
    permission_mode="bypassPermissions",
    include_partial_messages=True,
    max_buffer_size=16 * 1024 * 1024,
    setting_sources=["user", "project", "local"],
)


async def _user_turn(content):
    yield {"type": "user", "message": {"role": "user", "content": content}}


@asynccontextmanager
async def create_agent():
    async with ClaudeSDKClient(options=_AGENT_OPTIONS) as agent:
        yield agent


async def channel_task(agent, lock: anyio.Lock, channel: Channel, cancel_scope: anyio.CancelScope):
    while True:
        try:
            msg = await channel.receive()
        except SystemExit:
            cancel_scope.cancel()
            return
        # Lock covers the entire query→stream→reply cycle: reply() consumes a live
        # stream from the agent's internal buffer, so a concurrent query() on another
        # channel would corrupt both streams if reply() ran outside the lock.
        async with lock:
            await agent.query(_user_turn(msg.content), session_id=msg.session_id)
            await channel.reply(Reply(msg.message_id, msg.session_id, agent.receive_response()))


async def serve():
    channels = get_all_channels()
    async with create_agent() as agent:
        lock = anyio.Lock()
        for ch in channels:
            await ch.setup()
        logger.info(f"All {len(channels)} channel(s) initialized, agent is ready.")
        async with anyio.create_task_group() as tg:
            for ch in channels:
                tg.start_soon(channel_task, agent, lock, ch, tg.cancel_scope)


async def run_headless(prompt: str) -> None:
    """One-shot: send prompt, print result, then exit."""
    async with create_agent() as agent:
        await agent.query(_user_turn([{"type": "text", "text": prompt}]), session_id="headless")
        async for msg in agent.receive_response():
            if isinstance(msg, ResultMessage):
                print(msg.result or "")


def cli():
    parser = argparse.ArgumentParser(prog="moon")
    parser.add_argument("-p", dest="prompt", metavar="PROMPT", help="Run headless: send prompt, print result, then exit")
    args, _ = parser.parse_known_args()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not found.")
        print("Copy .env.example to .env, set your ANTHROPIC_API_KEY, then restart.")
        raise SystemExit(1)
    try:
        if args.prompt:
            logging.getLogger().setLevel(logging.WARNING)
            anyio.run(run_headless, args.prompt)
        else:
            anyio.run(serve)
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    cli()
