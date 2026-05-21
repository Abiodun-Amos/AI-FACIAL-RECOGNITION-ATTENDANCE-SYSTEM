"""
ImgBB image upload client.
===========================
Single-purpose: upload an image file, get back its hosted URL.
That URL goes into the intruder's Firestore doc + the local
intruders.image_url column.
"""

import base64
import requests

from src import config


_API_URL = "https://api.imgbb.com/1/upload"
_key = None


def _get_key():
    global _key
    if _key is None:
        if not config.IMGBB_KEY_PATH.exists():
            raise FileNotFoundError(
                f"ImgBB key missing: {config.IMGBB_KEY_PATH}")
        _key = config.IMGBB_KEY_PATH.read_text(encoding="utf-8").strip()
    return _key


def upload(image_path, timeout=30):
    """
    Upload a local image file to ImgBB. Returns the hosted URL on
    success. Raises on any failure (network, HTTP error, bad response).
    """
    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read())

    resp = requests.post(
        _API_URL,
        data={"key": _get_key(), "image": encoded},
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError(f"ImgBB rejected upload: {payload}")
    return payload["data"]["url"]