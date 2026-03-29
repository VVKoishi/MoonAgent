"""Lark Receive - WebSocket message reception"""

import asyncio
import json
import logging
import os
import time

import lark_oapi as lark
import lark_oapi.ws.client as _lark_ws_mod
from lark_oapi.api.im.v1 import GetMessageRequest

from channels import Message
from .resource import LarkResource
from .richtext import LarkRichText

logger = logging.getLogger(__name__)


class LarkReceive:

    def __init__(self, queue):
        app_id     = os.environ.get("LARK_APP_ID")
        app_secret = os.environ.get("LARK_APP_SECRET")
        if not app_id or not app_secret:
            raise ValueError("LARK_APP_ID or LARK_APP_SECRET not set")
        self._queue       = queue
        self._open_id     = os.environ.get("LARK_OPEN_ID")
        self._resource    = LarkResource()
        self._richtext    = LarkRichText()
        self._client      = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
        self._start_time  = int(time.time() * 1000)
        self._app_id      = app_id
        self._app_secret  = app_secret

    async def start(self) -> None:
        # lark_oapi.ws.client captures the event loop at import time; update it here.
        _lark_ws_mod.loop = asyncio.get_running_loop()
        handler = (
            lark.EventDispatcherHandler.builder(self._app_id, self._app_secret)
                .register_p2_im_message_receive_v1(self._on_message)
                .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(lambda _: None)
                .build()
        )
        self._ws = lark.ws.Client(self._app_id, self._app_secret,
                                  event_handler=handler, log_level=lark.LogLevel.ERROR)
        await self._ws._connect()
        logger.info("LarkReceive: WebSocket connected")

    def _get_message(self, message_id: str) -> tuple[str, dict] | None:
        try:
            res = self._client.im.v1.message.get(
                GetMessageRequest.builder().message_id(message_id).build()
            )
            if res.success() and res.data.items:
                item = res.data.items[0]
                return item.msg_type, json.loads(item.body.content) if item.body else {}
        except Exception as e:
            logger.error(f"Get message failed: {e}")
        return None

    def _on_message(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        if not (data and data.event and (msg := data.event.message)):
            return
        if msg.create_time and int(msg.create_time) < self._start_time:
            return
        if self._open_id and msg.chat_type != "p2p":
            if not any(m.id and m.id.open_id == self._open_id for m in (msg.mentions or [])):
                return

        content_data = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
        content = self._parse_content(msg.message_id, msg.message_type, content_data)

        if (pid := msg.parent_id) and not self._queue.exists_sync(pid) and (parent := self._get_message(pid)):
            content = self._parse_content(pid, *parent) + content

        if content:
            sender = data.event.sender
            sid = sender and sender.sender_id
            sender_label = None
            if sid:
                if sid.open_id:
                    sender_label = f"open_id {sid.open_id}"
                elif sid.user_id:
                    sender_label = f"user_id {sid.user_id}"
                elif sid.union_id:
                    sender_label = f"union_id {sid.union_id}"
            if sender_label:
                content = [{"type": "text", "text": f"[Message from {sender_label}]"}] + content
            if self._queue.put_sync(Message(msg.message_id, msg.chat_id, content)):
                logger.info(f"Queued [{msg.chat_id}] {msg.message_id} ({msg.message_type})")

    def _parse_content(self, message_id: str, message_type: str, data: dict) -> list:
        match message_type:
            case "text":
                if text := data.get("text", "").strip():
                    return [{"type": "text", "text": text}]
            case "post":
                if result := self._richtext.parse(message_id, data):
                    return result
            case "image":
                if (key := data.get("image_key")) and (
                    path := self._resource.download_image(message_id, key)
                ):
                    return [{"type": "text", "text": f"[Image: {path}]"}]
            case "file":
                if key := data.get("file_key"):
                    name = data.get("file_name", "")
                    if path := self._resource.download_file(message_id, key, name):
                        return [{"type": "text", "text": f"[File: {name}, Path: {path}]"}]
            case "audio" | "media":
                if (key := data.get("file_key")) and (
                    path := self._resource.download_file(message_id, key)
                ):
                    return [{"type": "text", "text": f"[{message_type.capitalize()}: {path}]"}]
        return [{"type": "text", "text": f"[{message_type}] {data}"}]

