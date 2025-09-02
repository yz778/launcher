#!/usr/bin/env python3

"""
Prioritized scoring system.

Priority Order:
1. Exact plugin name matches (highest priority): 1000+ points
2. Fuzzy name matches: 600-999 points
3. History scoring (including top matches, recent usage, frequency): 500-599 points
4. Description matches (lowest priority): 1-99 points
"""

import logging
import math

logger = logging.getLogger(__name__)


# Prioritized scoring constants
# Priority 1: Exact plugin name matches (1000+ points)
EXACT_NAME_MATCH_BASE = 1000
EXACT_NAME_MATCH_BONUS = 200

# Priority 2: Fuzzy name matches (600-999 points)
FUZZY_NAME_MATCH_BASE = 600

# Priority 3: History scoring (500-599 points)
HISTORY_MATCH_BASE = 500
HISTORY_BOOST = 50
HISTORY_USAGE_BOOST_MAX = 30
HISTORY_RECENCY_BOOST_MAX = 20

# Priority 4: Description matches (1-99 points)
DESCRIPTION_MATCH_BASE = 50
DESCRIPTION_EXACT_BONUS = 30


def calculate_match_score(
    query: str, text: str, is_name: bool = True, is_history: bool = False
) -> float:
    """
    Calculate match score between query and text using prioritized scoring.

    Args:
        query: Search query
        text: Text to match against
        is_name: True for name/title matches, False for description matches
        is_history: True if this is a history item

    Returns:
        Score (higher is better) following priority order:
        1. Exact name matches: 1000+ points
        2. Fuzzy name matches: 600-999 points
        3. History items: 500-599 points
        4. Description matches: 1-99 points
    """
    if not text or not query:
        return 0.0

    query = query.lower().strip()
    text = text.lower().strip()

    # Priority 1: Name matches
    if is_name:
        if query == text:
            return EXACT_NAME_MATCH_BASE + EXACT_NAME_MATCH_BONUS
        else:
            return _calculate_fuzzy_name_score(query, text)

    # Priority 2: History scoring
    if is_history:
        return _calculate_history_score(query, text, is_name)

    # Priority 3: Description matches
    return _calculate_description_score(query, text)


def _calculate_history_score(query: str, text: str, is_name: bool) -> float:
    """Calculate score for history items (Priority 3: 500-599 points)"""
    base_score = HISTORY_MATCH_BASE

    # Exact match gets highest history score
    if query == text:
        return base_score + 50

    # Prefix match
    if text.startswith(query):
        quality = len(query) / len(text)
        return base_score + 30 + (quality * 20)

    # Substring match
    if query in text:
        quality = len(query) / len(text)
        position = text.find(query) / len(text)
        position_bonus = (1.0 - position) * 10
        return base_score + 20 + (quality * 10) + position_bonus

    # Fuzzy match
    if _is_fuzzy_match(query, text):
        quality = len(query) / len(text)
        return base_score + (quality * 10)

    return 0.0


def _calculate_fuzzy_name_score(query: str, text: str) -> float:
    """Calculate score for fuzzy name matches (Priority 2: 600-999 points)"""
    base_score = FUZZY_NAME_MATCH_BASE

    # Prefix match
    if text.startswith(query):
        quality = len(query) / len(text)
        return base_score + 100 + (quality * 50)

    # Substring match
    if query in text:
        quality = len(query) / len(text)
        position = text.find(query) / len(text)
        position_bonus = (1.0 - position) * 20
        return base_score + 50 + (quality * 30) + position_bonus

    # Fuzzy match
    if _is_fuzzy_match(query, text):
        quality = len(query) / len(text)
        return base_score + (quality * 30)

    return 0.0


def _calculate_description_score(query: str, text: str) -> float:
    """Calculate score for description matches (Priority 4: 1-99 points)"""
    base_score = DESCRIPTION_MATCH_BASE

    # Exact match
    if query == text:
        return base_score + DESCRIPTION_EXACT_BONUS

    # Prefix match
    if text.startswith(query):
        quality = len(query) / len(text)
        return base_score + 20 + (quality * 10)

    # Substring match
    if query in text:
        quality = len(query) / len(text)
        position = text.find(query) / len(text)
        position_bonus = (1.0 - position) * 5
        return base_score + 10 + (quality * 5) + position_bonus

    # Fuzzy match
    if _is_fuzzy_match(query, text):
        quality = len(query) / len(text)
        return base_score + (quality * 5)

    return 0.0


def _is_fuzzy_match(query: str, text: str) -> bool:
    """Check if all query characters appear in text in order"""
    query_idx = 0
    for char in text:
        if query_idx < len(query) and char == query[query_idx]:
            query_idx += 1
    return query_idx == len(query)


def apply_history_boost(score: float) -> float:
    """Apply history boost to a score (for items already in history priority tier)"""
    return score + HISTORY_BOOST


def apply_usage_boost(score: float, usage_count: int) -> float:
    """Apply usage frequency boost (capped to stay within history tier)"""
    if usage_count <= 1:
        return score
    boost = min(HISTORY_USAGE_BOOST_MAX, 10 * math.log2(usage_count))
    return score + boost


def apply_recency_boost(score: float, age_hours: float) -> float:
    """Apply recency boost (within 24 hours, capped to stay within history tier)"""
    if age_hours >= 24:
        return score
    boost = max(0, HISTORY_RECENCY_BOOST_MAX * (1 - age_hours / 24))
    return score + boost


def calculate_exact_name_match_score(query: str, text: str) -> float:
    """Calculate score for exact name matches (Priority 1: highest)"""
    if not text or not query:
        return 0.0

    query = query.lower().strip()
    text = text.lower().strip()

    if query == text:
        return EXACT_NAME_MATCH_BASE + EXACT_NAME_MATCH_BONUS

    return 0.0
