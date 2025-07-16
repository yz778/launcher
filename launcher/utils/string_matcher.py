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
        Calculate match score between query and item using unified scoring system

        Args:
            query: The normalized query string (lowercase)
            item: The item to score

        Returns:
            Score using unified scoring system (higher is better)
        """
        from launcher.utils.scoring_system import (
            calculate_match_score,
            apply_history_boost,
        )

        key = self.key_func(item)

        # Calculate base score using unified system
        base_score = calculate_match_score(query, key, is_name=True)

        # Apply history boost if item is in history
        if self.history and item in self.history:
            return apply_history_boost(base_score)

        return base_score
