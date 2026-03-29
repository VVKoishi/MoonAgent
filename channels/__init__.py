"""Channel abstraction layer"""

import json
import logging
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio
import aiosqlite

logger = logging.getLogger(__name__)


def get_all_channels() -> list["Channel"]:
    """Discover and instantiate all available channels."""
    from channels.shell import ShellChannel
    from channels.lark import LarkChannel
    return [cls() for cls in (ShellChannel, LarkChannel) if cls.is_available()]


@dataclass
class Message:
    """Incoming message from any channel."""
    message_id: str
    session_id: str
    content: list


@dataclass
class Reply:
    """Agent response ready to be delivered back to the user."""
    message_id: str
    session_id: str
    stream: AsyncIterator[Any]


class Channel(ABC):
    """Base channel interface — implement to add a new messaging platform."""

    @classmethod
    def is_available(cls) -> bool:
        return True

    async def setup(self): pass
    async def teardown(self): pass

    @abstractmethod
    async def receive(self) -> Message: ...

    @abstractmethod
    async def reply(self, reply: Reply) -> None:
        """Send response back to the user.
        reply.stream is the raw async iterator from agent.receive_response();
        each channel is responsible for parsing SDK types and formatting output.
        """
        ...


class MessageQueue:
    """SQLite-backed persistent queue — survives service restarts.

    Schema:
        messages(message_id TEXT PK, session_id TEXT, content_json TEXT,
                 status TEXT, created_at INTEGER)
        status: 'pending' | 'processing' | 'done'

    Guarantees:
        - put_sync() is safe to call from any thread
        - Duplicate message_id is silently ignored
        - Processing messages are reset to 'pending' on startup
        - ack() must be called after successful reply
    """

    _DDL = """
        CREATE TABLE IF NOT EXISTS messages (
            message_id   TEXT PRIMARY KEY,
            session_id   TEXT NOT NULL,
            content_json TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'pending',
            created_at   INTEGER NOT NULL
        )
    """

    def __init__(self, db_path: str = "assets/messages.db"):
        p = Path(db_path).absolute()
        p.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(p)
        self._notify  = threading.Event()

    def _sync_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    async def _async_conn(self):
        db = await aiosqlite.connect(self._db_path)
        await db.execute("PRAGMA journal_mode=WAL")
        return db

    async def setup(self):
        """Initialize schema and recover interrupted messages from last run."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(self._DDL)
            await db.execute("UPDATE messages SET status = 'pending' WHERE status = 'processing'")
            await db.commit()
        self._notify.set()  # wake get() if pending messages exist
        logger.info(f"MessageQueue ready: {self._db_path}")

    def exists_sync(self, message_id: str) -> bool:
        with self._sync_conn() as conn:
            return conn.execute(
                "SELECT 1 FROM messages WHERE message_id = ? LIMIT 1", (message_id,)
            ).fetchone() is not None

    def put_sync(self, message: Message) -> bool:
        """Enqueue from any thread. Returns False if duplicate."""
        with self._sync_conn() as conn:
            inserted = conn.execute(
                "INSERT OR IGNORE INTO messages (message_id, session_id, content_json, status, created_at) "
                "VALUES (?, ?, ?, 'pending', ?)",
                (message.message_id, message.session_id, json.dumps(message.content), int(time.time() * 1000)),
            ).rowcount > 0
        if inserted:
            self._notify.set()
        return inserted

    async def get(self) -> Message:
        """Block until a pending message is available. Marks it as 'processing'."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            while True:
                async with db.execute(
                    "SELECT message_id, session_id, content_json FROM messages "
                    "WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
                ) as cur:
                    row = await cur.fetchone()
                if row:
                    await db.execute("UPDATE messages SET status = 'processing' WHERE message_id = ?", (row[0],))
                    await db.commit()
                    return Message(row[0], row[1], json.loads(row[2]))

                self._notify.clear()
                await anyio.to_thread.run_sync(lambda: self._notify.wait(timeout=1.0))

    async def ack(self, message_id: str):
        """Mark message as done after successful processing."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("UPDATE messages SET status = 'done' WHERE message_id = ?", (message_id,))
            await db.commit()
