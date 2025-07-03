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

            # Calculate score and highlight indices based on different matching strategies
            score, start_index, end_index = self._calculate_score(query, key, item)

            if score > 0:
                scored_items.append((item, score, start_index, end_index))

        # Sort by score descending
        scored_items.sort(key=lambda x: x[1], reverse=True)

        # Return top matches (no longer need highlight indices)
        return [(item, score) for item, score, start_index, end_index in scored_items[:limit]]

    def _calculate_score(self, query: str, key: str, item: T) -> Tuple[float, int, int]:
        """
        Calculate match score between query and key, and return highlight indices.

        Args:
            query: The normalized query string
            key: The normalized key string
            item: The original item

        Returns:
            Tuple of (score, start_index, end_index), where score is between 0 and 100,
            and indices are for highlighting the matched part in the original string.
            Indices will be -1, -1 if no match.
        """
        # Base scores for each category
        HISTORY_BASE = 300.0
        EXACT_BASE = 200.0
        PREFIX_BASE = 150.0
        PARTIAL_BASE = 100.0

        score = 0.0
        start_index = -1
        end_index = -1

        # Calculate match quality (0.0 to 1.0)
        match_quality = len(query) / len(key) if len(key) > 0 else 0

        # 1. History partial match
        if item in self.history and query in key:
            start_index = key.find(query)
            end_index = start_index + len(query)
            if key.startswith(query):
                score = HISTORY_BASE + 20.0 * match_quality
            else:
                score = HISTORY_BASE + 10.0 * match_quality
            return score, start_index, end_index

        # 2. Exact match
        if query == key:
            score = EXACT_BASE
            start_index = 0
            end_index = len(query)
            return score, start_index, end_index

        # 3. Prefix match (key starts with query)
        if key.startswith(query):
            score = PREFIX_BASE + 30.0 * match_quality
            start_index = 0
            end_index = len(query)
            return score, start_index, end_index

        # 4. Partial match
        if query in key:
            start_index = key.find(query)
            end_index = start_index + len(query)
            # Calculate position factor (earlier matches get higher scores)
            position = start_index / len(key) if len(key) > 0 else 0
            position_factor = 1.0 - position  # Higher for matches at the beginning

            score = PARTIAL_BASE + 20.0 * match_quality * position_factor
            return score, start_index, end_index

        # No match
        return score, start_index, end_index
