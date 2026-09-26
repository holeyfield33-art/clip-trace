"""Resource usage measurement helpers."""

from __future__ import annotations

import resource
import time
from contextlib import contextmanager
from typing import Dict, Iterator


@contextmanager
def measure() -> Iterator[Dict[str, float]]:
    """Context manager that records wall time and max RSS (best-effort)."""
    start = time.perf_counter()
    usage_start = resource.getrusage(resource.RUSAGE_SELF)
    out: Dict[str, float] = {}
    try:
        yield out
    finally:
        end = time.perf_counter()
        usage_end = resource.getrusage(resource.RUSAGE_SELF)
        out["wall_s"] = end - start
        # maxrss is KB on Linux
        out["max_rss_kb"] = float(usage_end.ru_maxrss)
        out["cpu_user_s"] = usage_end.ru_utime - usage_start.ru_utime
        out["cpu_sys_s"] = usage_end.ru_stime - usage_start.ru_stime
