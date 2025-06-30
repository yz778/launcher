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
        Match items against the query

        Args:
            query: The query string to match against
            limit: Maximum number of results to return

        Returns:
            List of tuples (item, score) sorted by score descending
        """
        if not query:
            # Return all items with a perfect score if query is empty
            return [(item, 100.0) for item in self.items[:limit]]

        # Normalize query
        query = query.lower().strip()

        # Calculate scores for each item
        scored_items = []
        for item in self.items:
            key = self.key_func(item).lower()

            # Calculate score based on different matching strategies
            score = self._calculate_score(query, key, item)

            if score > 0:
                scored_items.append((item, score))

        # Sort by score descending
        scored_items.sort(key=lambda x: x[1], reverse=True)

        # Return top matches
        return scored_items[:limit]

    def _calculate_score(self, query: str, key: str, item: T) -> float:
        """
        Calculate match score between query and key

        Args:
            query: The normalized query string
            key: The normalized key string
            item: The original item

        Returns:
            Score between 0 and 100, where 100 is a perfect match
        """
        # Base scores for each category
        HISTORY_BASE = 300.0
        EXACT_BASE = 200.0
        PREFIX_BASE = 150.0
        PARTIAL_BASE = 100.0

        # Calculate match quality (0.0 to 1.0)
        match_quality = len(query) / len(key) if len(key) > 0 else 0

        # 1. History partial match
        if item in self.history and query in key:
            # Add bonus for better matches within history
            if key.startswith(query):
                return HISTORY_BASE + 20.0 * match_quality
            return HISTORY_BASE + 10.0 * match_quality

        # 2. Exact match
        if query == key:
            return EXACT_BASE

        # 3. Prefix match (key starts with query)
        if key.startswith(query):
            return PREFIX_BASE + 30.0 * match_quality

        # 4. Partial match
        if query in key:
            # Calculate position factor (earlier matches get higher scores)
            position = key.find(query) / len(key) if len(key) > 0 else 0
            position_factor = 1.0 - position  # Higher for matches at the beginning

            return PARTIAL_BASE + 20.0 * match_quality * position_factor

        # No match
        return 0.0
