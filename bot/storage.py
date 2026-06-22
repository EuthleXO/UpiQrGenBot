"""
User data storage.

IMPORTANT — Vercel serverless functions run on a read-only, ephemeral
filesystem and each invocation may run on a fresh container. Writing to
a local JSON file (the original approach) silently loses all data
between requests in production. This module supports three backends:

  STORAGE_BACKEND=memory  -> in-process dict (default, local dev only)
  STORAGE_BACKEND=json    -> local JSON file (local dev / VPS with disk)
  STORAGE_BACKEND=redis   -> persistent, required for real Vercel use
                             (works with Vercel KV, Upstash, or any
                             Redis-compatible REDIS_URL)

Pick the backend with the STORAGE_BACKEND env var. See README.md.
"""

import json
import os
import threading
from typing import Dict, Optional

from config import STORAGE_BACKEND, USERS_FILE, REDIS_URL

_DEFAULT_USER = {
    "upi": "",
    "name": "",
    "hide_upi": True,
    "qr_count": 0,
}

_lock = threading.Lock()

# ─── In-memory backend (default) ─────────────────────────────────────────────
_memory_store: Dict[str, dict] = {}


def _memory_load() -> Dict[str, dict]:
    return _memory_store


def _memory_save(data: Dict[str, dict]) -> None:
    global _memory_store
    _memory_store = data


# ─── JSON file backend ────────────────────────────────────────────────────────
def _json_load() -> Dict[str, dict]:
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _json_save(data: Dict[str, dict]) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ─── Redis backend ────────────────────────────────────────────────────────────
_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis  # imported lazily so it's an optional dependency
        except ImportError as exc:
            raise RuntimeError(
                "STORAGE_BACKEND=redis requires the 'redis' package. "
                "Install it with: pip install redis"
            ) from exc
        if not REDIS_URL:
            raise RuntimeError("STORAGE_BACKEND=redis requires REDIS_URL to be set.")
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def _redis_get_user(user_id: int) -> dict:
    client = _get_redis()
    raw = client.get(f"user:{user_id}")
    if raw is None:
        return dict(_DEFAULT_USER)
    return {**_DEFAULT_USER, **json.loads(raw)}


def _redis_save_user(user_id: int, user_data: dict) -> None:
    client = _get_redis()
    client.set(f"user:{user_id}", json.dumps(user_data))


def _redis_all_users() -> Dict[str, dict]:
    client = _get_redis()
    result = {}
    for key in client.scan_iter(match="user:*"):
        uid = key.split(":", 1)[1]
        raw = client.get(key)
        if raw:
            result[uid] = json.loads(raw)
    return result


# ─── Public API ───────────────────────────────────────────────────────────────
def get_user(user_id: int) -> dict:
    if STORAGE_BACKEND == "redis":
        return _redis_get_user(user_id)
    with _lock:
        data = _json_load() if STORAGE_BACKEND == "json" else _memory_load()
        return {**_DEFAULT_USER, **data.get(str(user_id), {})}


def save_user(user_id: int, user_data: dict) -> None:
    if STORAGE_BACKEND == "redis":
        _redis_save_user(user_id, user_data)
        return
    with _lock:
        if STORAGE_BACKEND == "json":
            data = _json_load()
            data[str(user_id)] = user_data
            _json_save(data)
        else:
            data = _memory_load()
            data[str(user_id)] = user_data
            _memory_save(data)


def increment_qr_count(user_id: int) -> int:
    user = get_user(user_id)
    user["qr_count"] = user.get("qr_count", 0) + 1
    save_user(user_id, user)
    return user["qr_count"]


def all_users() -> Dict[str, dict]:
    """Used by the /admin command for aggregate stats."""
    if STORAGE_BACKEND == "redis":
        return _redis_all_users()
    with _lock:
        return _json_load() if STORAGE_BACKEND == "json" else _memory_load()
