"""API keys from the environment, rotated on quota errors.

A video is a few dozen TTS calls, and a free-tier key can run out partway. Any of
these spellings is read, merged and de-duplicated:

    GEMINI_API_KEY=key_one,key_two
    GEMINI_API_KEYS=key_one;key_two
    GEMINI_API_KEY_1=key_one

A quota or rate-limit error moves to the next key at once; once every key has
been tried, the ring waits and goes round again. Any other error is raised on the
first key, because it would fail the same way on all of them. Keys are never
printed or written anywhere.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable

_RATE_LIMITED = re.compile(r"\b429\b|RESOURCE_EXHAUSTED|rate.?limit|quota|too many requests|overloaded", re.I)
_SEP = re.compile(r"[,;\s]+")


def read_keys(name: str, env: dict[str, str] | None = None) -> list[str]:
    env = dict(os.environ) if env is None else env
    raw = [env.get(name, ""), env.get(name + "S", "")] + [env.get(f"{name}_{i}", "") for i in range(1, 33)]
    out: list[str] = []
    for chunk in raw:
        for k in _SEP.split(chunk.strip()):
            if k and k not in out:
                out.append(k)
    return out


def run_with_keys[T](name: str, call: Callable[[str], T], sleep: Callable[[float], None] = time.sleep) -> T:
    keys = read_keys(name)
    if not keys:
        raise SystemExit(f"{name} is not set (in the environment or the workspace .env)")
    attempts, wait = len(keys) * 2, 5.0
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            return call(keys[attempt % len(keys)])
        except Exception as exc:
            if not _RATE_LIMITED.search(str(exc)):
                raise
            last = exc
            if (attempt + 1) % len(keys) == 0 and attempt + 1 < attempts:
                sleep(wait)
                wait = min(wait * 2, 60.0)
    raise RuntimeError(f"every {name} key is rate-limited") from last
