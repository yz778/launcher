from typing import Callable, Generic, List, Tuple, TypeVar

from launcher.utils.scoring_system import FieldHighlight, calculate_match_score

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

    def match(
        self, query: str, limit: int = 10
    ) -> List[Tuple[T, float, FieldHighlight]]:
        """
        Match items against the query and return scored results with highlight information

        Args:
            query: The query string to match against
            limit: Maximum number of results to return

        Returns:
            List of tuples (item, score, field_highlight) sorted by score descending
        """
        if not query:
            # Create empty highlight for no-query results
            empty_highlight = FieldHighlight("name", set())
            return [(item, 100.0, empty_highlight) for item in self.items[:limit]]

        query_lower = query.lower().strip()
        matches = []

        for item in self.items:
            result = self._calculate_score(query_lower, item)
            if result is not None:
                score, field_highlight = result
                matches.append((item, score, field_highlight))

        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:limit]

    def _calculate_score(
        self, query: str, item: T
    ) -> tuple[float, FieldHighlight] | None:
        """
        Calculate match score between query and item using simplified scoring system

        Args:
            query: The normalized query string (lowercase)
            item: The item to score

        Returns:
            Tuple of (score, field_highlight) or None if no match
        """
        key = self.key_func(item)

        return calculate_match_score(query, key, is_name=True)
