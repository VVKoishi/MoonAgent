"""Lark Channel - Feishu/Lark messaging integration"""

import os
import logging

from channels import Channel, Message, MessageQueue, Reply
from .receive import LarkReceive
from .reply_plain import LarkPlainReply
from .reply_stream import LarkStreamReply

logger = logging.getLogger(__name__)


class LarkChannel(Channel):
    """Feishu/Lark channel -- full message type support with SQLite-backed queue.

    Receive: text, image, file, audio, media, post (rich text)
    Reply:   streaming card (default) or plain markdown text
             controlled by LARK_REPLY_MODE env var (stream | plain)
    """

    @classmethod
    def is_available(cls) -> bool:
        if os.getenv("ENABLE_LARK", "true").lower() != "true":
            return False
        return bool(os.getenv("LARK_APP_ID") and os.getenv("LARK_APP_SECRET"))

    def __init__(self, db_path: str = "assets/lark/messages.db"):
        self._queue = MessageQueue(db_path)
        self._receive = LarkReceive(self._queue)
        mode = os.getenv("LARK_REPLY_MODE", "stream")
        self._reply_impl = LarkStreamReply() if mode == "stream" else LarkPlainReply()

    async def setup(self):
        await self._queue.setup()
        await self._receive.start()

    async def receive(self) -> Message:
        return await self._queue.get()

    async def reply(self, reply: Reply) -> None:
        await self._reply_impl.reply(reply)
        await self._queue.ack(reply.message_id)