#!/usr/bin/env python3

"""
Prioritized scoring system.

Priority Order:
1. History with user arguments match: 1000+ points
2. Name matches (exact and fuzzy): 500-999 points
3. Description matches: 1-499 points

History gets priority only when it includes user arguments that match the query.
Otherwise, all plugins (including history) are scored equally based on match quality.
"""

import logging

logger = logging.getLogger(__name__)


# Priority 1: History with user arguments (1000+ points)
HISTORY_WITH_ARGS_BASE = 1000

# Priority 2: Name matches (500-999 points)
NAME_MATCH_BASE = 500
EXACT_MATCH_BONUS = 400  # Brings exact matches to 900+ points
FUZZY_MATCH_BONUS = 200  # Brings good fuzzy matches to 700+ points

# Priority 3: Description matches (1-499 points)
DESCRIPTION_MATCH_BASE = 100


def calculate_match_score(
    query: str, text: str, is_name: bool = True, user_input_with_args: str = None
) -> float:
    """
    Calculate match score.

    Args:
        query: Search query
        text: Text to match against
        is_name: True for name/title matches, False for description matches
        user_input_with_args: Full user input with arguments (for history priority)

    Returns:
        Score (higher is better) following priority order:
        1. History with user arguments match: 1000+ points
        2. Name matches (exact and fuzzy): 500-999 points
        3. Description matches: 1-499 points
    """
    if not text or not query:
        return 0.0

    query = query.lower().strip()
    text = text.lower().strip()

    # Priority 1: History with user arguments match
    if user_input_with_args:
        user_input_lower = user_input_with_args.lower().strip()
        if query == user_input_lower:
            return HISTORY_WITH_ARGS_BASE + 200  # Exact match with args
        elif user_input_lower.startswith(query):
            quality = len(query) / len(user_input_lower)
            return HISTORY_WITH_ARGS_BASE + (quality * 100)  # Prefix match with args

    # Priority 2: Name matches
    if is_name:
        return _calculate_name_score(query, text)

    # Priority 3: Description matches
    return _calculate_description_score(query, text)


def _calculate_name_score(query: str, text: str) -> float:
    """Calculate score for name matches (500-999 points)"""
    base_score = NAME_MATCH_BASE

    # Exact match gets highest name score
    if query == text:
        return base_score + EXACT_MATCH_BONUS

    # Prefix match
    if text.startswith(query):
        quality = len(query) / len(text)
        return base_score + FUZZY_MATCH_BONUS + (quality * 100)

    # Substring match
    if query in text:
        quality = len(query) / len(text)
        position = text.find(query) / len(text)
        position_bonus = (1.0 - position) * 50
        return base_score + 150 + (quality * 100) + position_bonus

    # Fuzzy match (characters appear in order)
    if _is_fuzzy_match(query, text):
        quality = len(query) / len(text)
        return base_score + (quality * 100)

    return 0.0


def _calculate_description_score(query: str, text: str) -> float:
    """Calculate score for description matches (1-499 points)"""
    base_score = DESCRIPTION_MATCH_BASE

    # Exact match
    if query == text:
        return base_score + 300

    # Prefix match
    if text.startswith(query):
        quality = len(query) / len(text)
        return base_score + 200 + (quality * 100)

    # Substring match
    if query in text:
        quality = len(query) / len(text)
        position = text.find(query) / len(text)
        position_bonus = (1.0 - position) * 50
        return base_score + 100 + (quality * 100) + position_bonus

    # Fuzzy match
    if _is_fuzzy_match(query, text):
        quality = len(query) / len(text)
        return base_score + (quality * 50)

    return 0.0


def _is_fuzzy_match(query: str, text: str) -> bool:
    """Check if all query characters appear in text in order"""
    query_idx = 0
    for char in text:
        if query_idx < len(query) and char == query[query_idx]:
            query_idx += 1
    return query_idx == len(query)
