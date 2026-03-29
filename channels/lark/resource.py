"""Lark Resource - Download images and files"""

import logging
import mimetypes
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import lark_oapi as lark
from lark_oapi.api.im.v1 import GetMessageResourceRequest

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent.parent.parent / "assets" / "lark"


class LarkResource:
    """Download Lark message resources (images, files)."""

    def __init__(self):
        app_id     = os.environ.get("LARK_APP_ID")
        app_secret = os.environ.get("LARK_APP_SECRET")
        if not app_id or not app_secret:
            raise ValueError("LARK_APP_ID or LARK_APP_SECRET not set")
        self._client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()

    def download(self, message_id: str, file_key: str, type: str) -> tuple[bytes, str] | None:
        """Download resource (type: 'image' or 'file'). Returns (bytes, filename) or None."""
        try:
            resp = self._client.im.v1.message_resource.get(
                GetMessageResourceRequest.builder()
                    .message_id(message_id).file_key(file_key).type(type).build()
            )
            if not resp.success():
                logger.error(f"Download failed: {resp.code} {resp.msg}")
                return None
            content_type = getattr(resp, "content_type", "") or ""
            filename = resp.file_name or ""
            if "." not in filename:
                ext = ""
                if content_type:
                    ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ""
                    if ext == ".jpe":
                        ext = ".jpg"
                if not ext and type == "image":
                    ext = ".jpg"
                filename = (filename or file_key) + ext
            return resp.file.read(), filename
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None

    def _save(self, data: bytes, filename: str) -> Path:
        folder = ASSETS_DIR / datetime.now().strftime("%Y%m%d")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / filename
        path.write_bytes(data)
        return path

    def download_image(self, message_id: str, image_key: str) -> str | None:
        """Download image to dated assets folder and return absolute path."""
        self._cleanup_old()
        result = self.download(message_id, image_key, "image")
        if not result:
            return None
        data, filename = result
        return str(self._save(data, filename).absolute())

    def download_file(self, message_id: str, file_key: str, filename: str = "") -> str | None:
        """Download file to dated assets folder and return absolute path."""
        self._cleanup_old()
        result = self.download(message_id, file_key, "file")
        if not result:
            return None
        data, original_name = result
        return str(self._save(data, filename or original_name).absolute())

    def _cleanup_old(self, days: int = 7):
        if not ASSETS_DIR.exists():
            return
        cutoff = datetime.now() - timedelta(days=days)
        for folder in ASSETS_DIR.iterdir():
            if not folder.is_dir():
                continue
            try:
                if datetime.strptime(folder.name, "%Y%m%d") < cutoff:
                    shutil.rmtree(folder)
                    logger.info(f"Removed old assets folder: {folder}")
            except ValueError:
                pass

