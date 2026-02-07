from __future__ import annotations


async def apply_stealth(page) -> None:
    """Best-effort stealth; no hard failure when package is missing."""
    try:
        from playwright_stealth import stealth_async  # type: ignore

        await stealth_async(page)
    except Exception:
        return
