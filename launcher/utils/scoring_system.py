#!/usr/bin/env python3

"""
Simple unified scoring system.

Rules:
1. Name matches: 100 points base
2. Description matches: 50 points base
3. History boost: +100 points
4. Exact > prefix > substring > fuzzy (within each category)
"""

import logging
import math

logger = logging.getLogger(__name__)


# Simple scoring constants
NAME_MATCH_BASE = 100
DESCRIPTION_MATCH_BASE = 50
HISTORY_BOOST = 20
EXACT_MATCH_BONUS = 100


def calculate_match_score(query: str, text: str, is_name: bool = True) -> float:
    """
    Calculate match score between query and text.

    Args:
        query: Search query
        text: Text to match against
        is_name: True for name/title matches, False for description matches

    Returns:
        Score (higher is better)
    """
    if not text or not query:
        return 0.0

    query = query.lower().strip()
    text = text.lower().strip()

    base_score = NAME_MATCH_BASE if is_name else DESCRIPTION_MATCH_BASE

    # Exact match
    if query == text:
        return base_score + EXACT_MATCH_BONUS

    # Prefix match
    if text.startswith(query):
        quality = len(query) / len(text)
        return base_score + 20 + (quality * 10)

    # Substring match
    if query in text:
        quality = len(query) / len(text)
        position = text.find(query) / len(text)
        position_bonus = (1.0 - position) * 5  # Earlier matches get bonus
        return base_score + 10 + (quality * 5) + position_bonus

    # Fuzzy match (all characters in order)
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
    """Apply history boost to a score"""
    return score + HISTORY_BOOST


def apply_usage_boost(score: float, usage_count: int) -> float:
    """Apply usage frequency boost"""
    if usage_count <= 1:
        return score
    return score + min(20, 5 * math.log2(usage_count))


def apply_recency_boost(score: float, age_hours: float) -> float:
    """Apply recency boost (within 24 hours)"""
    if age_hours >= 24:
        return score
    return score + max(0, 10 * (1 - age_hours / 24))


# Convenience functions (deprecated - use calculate_match_score directly)
def score_name_match(query: str, name: str) -> float:
    """Score a name/title match (deprecated - use calculate_match_score)"""
    return calculate_match_score(query, name, is_name=True)


def score_description_match(query: str, description: str) -> float:
    """Score a description match (deprecated - use calculate_match_score)"""
    return calculate_match_score(query, description, is_name=False)
