from __future__ import annotations

def semantic_match_score(query: str, title: str, description: str) -> float:
    """Disabled by design: project currently operates as read-only aggregator/notify."""
    _ = (query, title, description)
    return 0.0
