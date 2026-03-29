"""Lark Plain Reply - Reply with markdown text"""

import json
import logging
import os

import lark_oapi as lark
from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody
from claude_agent_sdk import ResultMessage

from channels import Reply

logger = logging.getLogger(__name__)


class LarkPlainReply:
    """Reply to Lark messages with the final result text (non-streaming)."""

    def __init__(self):
        app_id     = os.environ.get("LARK_APP_ID")
        app_secret = os.environ.get("LARK_APP_SECRET")
        if not app_id or not app_secret:
            raise ValueError("LARK_APP_ID or LARK_APP_SECRET not set")
        self._client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()

    async def reply(self, reply: Reply) -> bool:
        """Drain the stream, then send the ResultMessage.result as a single markdown reply."""
        result = ""
        async for msg in reply.stream:
            if isinstance(msg, ResultMessage):
                result = msg.result or ""

        if not result:
            return True

        try:
            content = json.dumps(
                {"zh_cn": {"content": [[{"tag": "md", "text": result}]]}},
                ensure_ascii=False,
            )
            request = (
                ReplyMessageRequest.builder()
                    .message_id(reply.message_id)
                    .request_body(ReplyMessageRequestBody.builder()
                        .content(content).msg_type("post").build())
                    .build()
            )
            return self._client.im.v1.message.reply(request).success()
        except Exception as e:
            logger.error(f"Plain reply failed: {e}")
            return False