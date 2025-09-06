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
from typing import Set

logger = logging.getLogger(__name__)


class FieldHighlight:
    """Represents highlighting information for multiple fields"""

    def __init__(
        self, name_indices: Set[int] = None, description_indices: Set[int] = None
    ):
        self.name_indices = name_indices or set()
        self.description_indices = description_indices or set()

    def __bool__(self):
        """Return True if there are indices to highlight"""
        return bool(self.name_indices or self.description_indices)

    def get_indices_for_field(self, field: str) -> Set[int]:
        """Get indices for a specific field"""
        if field == "name":
            return self.name_indices
        elif field == "description":
            return self.description_indices
        return set()

    def to_dict(self):
        """Convert to dictionary for serialization (if needed)"""
        return {
            "name_indices": sorted(self.name_indices),
            "description_indices": sorted(self.description_indices),
        }


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
) -> tuple[float, FieldHighlight] | None:
    """
    Calculate match score and highlight information.

    Args:
        query: Search query
        text: Text to match against
        is_name: True for name/title matches, False for description matches
        user_input_with_args: Full user input with arguments (for history priority)

    Returns:
        Tuple of (score, field_highlight) on match, None if no match found.
        Score follows priority order:
        1. History with user arguments match: 1000+ points
        2. Name matches (exact and fuzzy): 500-999 points
        3. Description matches: 1-499 points
        field_highlight: FieldHighlight object containing field type and indices
    """
    if not text or not query:
        return None

    query = query.lower().strip()
    text = text.lower().strip()
    original_text = text  # Keep original for index mapping

    # Priority 1: History with user arguments match
    if user_input_with_args:
        user_input_lower = user_input_with_args.lower().strip()
        if query == user_input_lower:
            indices = set(range(len(query)))
            highlight = FieldHighlight(name_indices=indices)
            return HISTORY_WITH_ARGS_BASE + 200, highlight  # Exact match with args
        elif user_input_lower.startswith(query):
            quality = len(query) / len(user_input_lower)
            indices = set(range(len(query)))
            highlight = FieldHighlight(name_indices=indices)
            return HISTORY_WITH_ARGS_BASE + (
                quality * 100
            ), highlight  # Prefix match with args

    # Priority 2: Name matches
    if is_name:
        result = _calculate_name_score(query, text)
        if result:
            highlight = FieldHighlight(name_indices=result[1])
            return result[0], highlight
        return None

    # Priority 3: Description matches
    result = _calculate_description_score(query, text)
    if result:
        highlight = FieldHighlight(description_indices=result[1])
        return result[0], highlight
    return None


def _calculate_name_score(query: str, text: str) -> tuple[float, set[int]] | None:
    """Calculate score for name matches (500-999 points) and return highlight indices"""
    base_score = NAME_MATCH_BASE

    # Exact match gets highest name score
    if query == text:
        indices = set(range(len(text)))
        return base_score + EXACT_MATCH_BONUS, indices

    # Prefix match
    if text.startswith(query):
        quality = len(query) / len(text)
        indices = set(range(len(query)))
        return base_score + FUZZY_MATCH_BONUS + (quality * 100), indices

    # Substring match
    if query in text:
        quality = len(query) / len(text)
        position = text.find(query) / len(text)
        position_bonus = (1.0 - position) * 50
        start_idx = text.find(query)
        indices = set(range(start_idx, start_idx + len(query)))
        return base_score + 150 + (quality * 100) + position_bonus, indices

    # Fuzzy match (characters appear in order)
    fuzzy_indices = _get_fuzzy_match_indices(query, text)
    if fuzzy_indices:
        quality = len(query) / len(text)
        return base_score + (quality * 100), fuzzy_indices

    return None


def _calculate_description_score(
    query: str, text: str
) -> tuple[float, set[int]] | None:
    """Calculate score for description matches (1-499 points) and return highlight indices"""
    base_score = DESCRIPTION_MATCH_BASE

    # Exact match
    if query == text:
        indices = set(range(len(text)))
        return base_score + 300, indices

    # Prefix match
    if text.startswith(query):
        quality = len(query) / len(text)
        indices = set(range(len(query)))
        return base_score + 200 + (quality * 100), indices

    # Substring match
    if query in text:
        quality = len(query) / len(text)
        position = text.find(query) / len(text)
        position_bonus = (1.0 - position) * 50
        start_idx = text.find(query)
        indices = set(range(start_idx, start_idx + len(query)))
        return base_score + 100 + (quality * 100) + position_bonus, indices

    # Fuzzy match
    fuzzy_indices = _get_fuzzy_match_indices(query, text)
    if fuzzy_indices:
        quality = len(query) / len(text)
        return base_score + (quality * 50), fuzzy_indices

    return None


def _get_fuzzy_match_indices(query: str, text: str) -> set[int] | None:
    """Get indices of fuzzy match characters, or None if no fuzzy match"""
    query_idx = 0
    indices = set()

    for text_idx, char in enumerate(text):
        if query_idx < len(query) and char == query[query_idx]:
            indices.add(text_idx)
            query_idx += 1

    return indices if query_idx == len(query) else None
