"""Lark Stream Reply - streaming card with typing effect"""

import json
import logging
import os
import uuid
from enum import Enum, auto

import lark_oapi as lark
from lark_oapi.api.cardkit.v1 import (
    CreateCardRequest, CreateCardRequestBody,
    SettingsCardRequest, SettingsCardRequestBody,
    ContentCardElementRequest, ContentCardElementRequestBody,
)
from lark_oapi.api.im.v1 import (
    ReplyMessageRequest, ReplyMessageRequestBody,
    CreateMessageRequest, CreateMessageRequestBody,
)
from claude_agent_sdk import ResultMessage
from claude_agent_sdk.types import StreamEvent

from channels import Reply
from channels.lark.tool_docs import TOOL_DESCRIPTIONS

logger = logging.getLogger(__name__)

STREAMING_CONFIG = {
    "print_frequency_ms": {"default": 30, "android": 30, "ios": 30, "pc": 30},
    "print_step":         {"default": 1,  "android": 1,  "ios": 1,  "pc": 1},
    "print_strategy": "fast",
}

_TODO_MARK = {"completed": " ✓", "in_progress": " ⋯"}


class ChunkType(Enum):
    NEW_CARD = auto()  # message_start: open a new card
    TEXT     = auto()  # text_delta: append to current card
    TOOL     = auto()  # tool call completed: append formatted tool line


def _uid() -> str:
    return str(uuid.uuid4())


def _truncate(s: str, n: int = 100) -> str:
    return s[:n] + "..." if len(s) > n else s


class LarkStreamReply:

    SUMMARY_KEYS = ("description", "url", "query", "skill", "file_path")

    def __init__(self):
        app_id     = os.environ.get("LARK_APP_ID")
        app_secret = os.environ.get("LARK_APP_SECRET")
        if not app_id or not app_secret:
            raise ValueError("LARK_APP_ID or LARK_APP_SECRET not set")
        self._client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()

    # -- Reply parsing ---------------------------------------------------------

    async def _iter_chunks(self, reply: Reply):
        """Yield (ChunkType, chunk) per StreamEvent.
        Text deltas are buffered per content_block and flushed on content_block_stop."""
        current_tool: str | None = None
        tool_input = ""
        current_text = ""

        async for msg in reply.stream:
            if isinstance(msg, ResultMessage):
                logger.info(f"Result: {msg.duration_ms / 1000:.1f}s, ${msg.total_cost_usd or 0:.4f}")
                continue
            if not isinstance(msg, StreamEvent):
                continue

            match msg.event.get("type"):
                case "message_start":
                    yield ChunkType.NEW_CARD, ""

                case "content_block_start":
                    block = msg.event.get("content_block", {})
                    if block.get("type") == "tool_use":
                        current_tool = block.get("name")
                        tool_input = ""
                    else:
                        current_text = ""

                case "content_block_delta":
                    delta = msg.event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        current_text += delta.get("text", "")
                    elif delta.get("type") == "input_json_delta":
                        tool_input += delta.get("partial_json", "")

                case "content_block_stop":
                    if current_tool:
                        yield ChunkType.TOOL, self._format_tool(current_tool, tool_input)
                        current_tool = None
                    elif current_text:
                        yield ChunkType.TEXT, current_text
                        current_text = ""

    # -- Tool output formatting ------------------------------------------------

    def _fmt_todo_write(self, inp: dict) -> str:
        lines = [
            f"- {t.get('content', '')}{_TODO_MARK.get(t.get('status', ''), '')}"
            for t in inp.get("todos", [])
        ]
        return "\n".join(lines)

    def _fmt_ask_user_question(self, inp: dict) -> str:
        lines = []
        for q in inp.get("questions", []):
            header   = q.get("header", "")
            question = q.get("question") or q.get("prompt", "")
            multi    = q.get("multiSelect") or q.get("allow_multiple", False)
            lines.append(f"{header} - {question}" if header else question)
            for i, opt in enumerate(q.get("options", []), 1):
                label = opt.get("label", opt) if isinstance(opt, dict) else opt
                lines.append(f"- {label}" if multi else f"{i}. {label}")
        return "\n".join(lines)

    def _format_tool(self, name: str, input_json: str) -> str:
        try:
            inp = json.loads(input_json) if input_json else {}
        except Exception:
            inp = {}
        logger.info(f"{name}: {input_json[:200]}")

        match name:
            case "TodoWrite":
                body = self._fmt_todo_write(inp)
            case "AskUserQuestion":
                body = self._fmt_ask_user_question(inp)
            case "Agent":
                body = f"{inp.get('subagent_type', '')}: {inp.get('description', '')}"
            case _:
                body = next(
                    (_truncate(v.replace("\\", "/") if k == "file_path" else v)
                     for k in self.SUMMARY_KEYS
                     if isinstance(v := inp.get(k, ""), str) and v),
                    TOOL_DESCRIPTIONS.get(name, ""),
                )

        tag = f"<text_tag color='blue'>{name}</text_tag>"
        return f"{tag}\n{body}" if "\n" in body else f"{tag} {body}" if body else tag

    # -- Lark CardKit API wrappers ---------------------------------------------

    def _create_card(self) -> str | None:
        card_data = {"schema": "2.0", "body": {"elements": [
            {"tag": "markdown", "element_id": "markdown_1", "content": ""}
        ]}}
        resp = self._client.cardkit.v1.card.create(
            CreateCardRequest.builder()
                .request_body(CreateCardRequestBody.builder()
                    .type("card_json").data(json.dumps(card_data)).build()).build()
        )
        if not resp.success():
            logger.error(f"Create card failed: {resp.code} {resp.msg}")
            return None
        return resp.data.card_id

    def _set_streaming(self, card_id: str, enabled: bool, seq: int) -> bool:
        config = {"streaming_mode": enabled}
        if enabled:
            config["streaming_config"] = STREAMING_CONFIG
        resp = self._client.cardkit.v1.card.settings(
            SettingsCardRequest.builder().card_id(card_id)
                .request_body(SettingsCardRequestBody.builder()
                    .settings(json.dumps({"config": config}))
                    .uuid(_uid()).sequence(seq).build()).build()
        )
        if not resp.success():
            logger.error(f"Set streaming failed: {resp.code} {resp.msg}")
        return resp.success()

    def _update_content(self, card_id: str, text: str, seq: int) -> None:
        self._client.cardkit.v1.card_element.content(
            ContentCardElementRequest.builder()
                .card_id(card_id).element_id("markdown_1")
                .request_body(ContentCardElementRequestBody.builder()
                    .uuid(_uid()).content(text).sequence(seq).build()).build()
        )

    def _send_card(self, card_id: str, *, reply_to: str | None = None, chat_id: str | None = None) -> bool:
        content = json.dumps({"type": "card", "data": {"card_id": card_id}})
        if reply_to:
            resp = self._client.im.v1.message.reply(
                ReplyMessageRequest.builder().message_id(reply_to)
                    .request_body(ReplyMessageRequestBody.builder()
                        .content(content).msg_type("interactive").build()).build()
            )
        else:
            resp = self._client.im.v1.message.create(
                CreateMessageRequest.builder().receive_id_type("chat_id")
                    .request_body(CreateMessageRequestBody.builder()
                        .receive_id(chat_id).content(content).msg_type("interactive").build()).build()
            )
        if not resp.success():
            logger.error(f"Send card failed: {resp.code} {resp.msg}")
        return resp.success()

    def _open_card(self, *, reply_to: str | None = None, chat_id: str | None = None) -> tuple[str, int] | tuple[None, None]:
        """Create, enable streaming, and send a new card. Returns (card_id, seq)."""
        card_id = self._create_card()
        if not card_id:
            return None, None
        if not self._send_card(card_id, reply_to=reply_to, chat_id=chat_id):
            return None, None
        seq = 1
        if not self._set_streaming(card_id, True, seq):
            return None, None
        return card_id, seq

    # -- Public interface ------------------------------------------------------

    async def reply(self, reply: Reply) -> bool:
        card_id: str | None = None
        seq = 1
        text = ""
        is_first_card = True

        async for chunk_type, chunk in self._iter_chunks(reply):
            if chunk_type is ChunkType.NEW_CARD:
                if card_id:
                    self._set_streaming(card_id, False, seq + 1)
                card_id, seq = self._open_card(
                    reply_to=reply.message_id if is_first_card else None,
                    chat_id=None if is_first_card else reply.session_id,
                )
                if not card_id:
                    return False
                text = ""
                is_first_card = False
            elif card_id:
                if chunk_type is ChunkType.TOOL and text and not text.endswith("\n"):
                    text += "\n"
                seq += 1
                text += chunk
                self._update_content(card_id, text, seq)

        if card_id:
            self._set_streaming(card_id, False, seq + 1)
        return True