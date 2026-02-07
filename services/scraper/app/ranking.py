from __future__ import annotations

import re


def _tokenize(text: str) -> set[str]:
    """Extract lowercase alphanumeric tokens from text."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def semantic_match_score(query: str, title: str, description: str) -> float:
    """Score job relevance using keyword overlap with the search query.

    Returns a float between 0.0 and 1.0:
    - Title matches are weighted more heavily than description matches.
    - Exact phrase presence in title gives a bonus.
    """
    if not query:
        return 0.0

    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0

    title_tokens = _tokenize(title)
    desc_tokens = _tokenize(description)

    # Title keyword overlap (weighted 0.6)
    title_overlap = len(query_tokens & title_tokens) / len(query_tokens)

    # Description keyword overlap (weighted 0.2)
    desc_overlap = len(query_tokens & desc_tokens) / len(query_tokens) if desc_tokens else 0.0

    # Exact phrase bonus (weighted 0.2)
    query_lower = query.strip().lower()
    phrase_bonus = 0.0
    if query_lower in title.lower():
        phrase_bonus = 1.0
    elif query_lower in description.lower():
        phrase_bonus = 0.5

    score = (title_overlap * 0.6) + (desc_overlap * 0.2) + (phrase_bonus * 0.2)
    return round(min(1.0, score), 3)
