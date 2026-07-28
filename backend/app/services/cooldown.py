"""
Shared guard against a double-click/retry loop burning real AI-provider
cost — extracted here once a second AI-cost endpoint (reporting) needed
the exact same check discovery/router.py already had.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status


def check_cooldown(last_at: Optional[datetime], cooldown_seconds: int) -> None:
    if last_at is None:
        return
    elapsed = (datetime.now(timezone.utc) - last_at).total_seconds()
    if elapsed < cooldown_seconds:
        wait_seconds = int(cooldown_seconds - elapsed) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {wait_seconds}s before running this again.",
        )
