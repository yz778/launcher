#!/usr/bin/env python3

from typing import List, Tuple, TypeVar, Generic, Callable

T = TypeVar("T")


class StringMatcher(Generic[T]):
    """
    Basic result matcher that can match items based on a string representation
    """

    __slots__ = ("items", "key_func", "history")

    def __init__(
        self, items: List[T], key_func: Callable[[T], str], history: List[T] = None
    ):
        """
        Initialize the result matcher

        Args:
            items: List of items to match against
            key_func: Function to extract the string to match from an item
            history: Optional list of previously used items
        """
        self.items = items
        self.key_func = key_func
        self.history = history or []

    def match(self, query: str, limit: int = 10) -> List[Tuple[T, float]]:
        """
        Match items against the query and return scored results

        Args:
            query: The query string to match against
            limit: Maximum number of results to return

        Returns:
            List of tuples (item, score) sorted by score descending
        """
        if not query:
            return [(item, 100.0) for item in self.items[:limit]]

        query_lower = query.lower().strip()
        matches = []

        for item in self.items:
            score = self._calculate_score(query_lower, item)
            if score > 0:
                matches.append((item, score))

        # Sort by score descending and limit results
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:limit]

    def _calculate_score(self, query: str, item: T) -> float:
        """
        Calculate match score between query and item

        Args:
            query: The normalized query string (lowercase)
            item: The item to score

        Returns:
            Score between 0 and 300+ (higher is better)
        """
        key = self.key_func(item).lower()

        # Base scores for different match types
        HISTORY_BASE = 300.0
        EXACT_BASE = 200.0
        PREFIX_BASE = 150.0
        PARTIAL_BASE = 100.0

        # Calculate match quality (0.0 to 1.0)
        match_quality = len(query) / len(key) if len(key) > 0 else 0

        # History boost for any match type
        history_boost = HISTORY_BASE if item in self.history else 0.0

        # Determine match type and base score
        if query == key:
            # Exact match
            return EXACT_BASE + history_boost
        elif key.startswith(query):
            # Prefix match
            return PREFIX_BASE + (30.0 * match_quality) + history_boost
        elif query in key:
            # Partial match
            position = key.find(query) / len(key) if len(key) > 0 else 0
            position_factor = 1.0 - position  # Earlier matches score higher
            return (
                PARTIAL_BASE + (20.0 * match_quality * position_factor) + history_boost
            )
        else:
            # No match
            return 0.0
