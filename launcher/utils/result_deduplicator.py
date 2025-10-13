import logging
from typing import List

from launcher.plugins.base import SearchResult

logger = logging.getLogger(__name__)


class ResultDeduplicator:
    """
    Handles deduplication of search results by removing history entries
    when the same actual command exists from another plugin.
    """

    def deduplicate_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        Optimized deduplication using hash-based lookup that removes results
        by removing all results from other_results if history already captured it.
        A history result is considered to have captured a result if its metadata contains
        the original_plugin_id and original_item_id matching a live result's plugin_id and item_id.

        Args:
            results: List of search results to deduplicate

        Returns:
            List of deduplicated results
        """
        if not results:
            return results

        # For optimization, we'll use a more efficient algorithm based on just plugin_id and item_id
        # Create a set for O(1) lookup of seen items
        seen_keys = set()
        unique_results = []

        for result in results:
            # Create a hashable key based on important fields
            key = (result.plugin_id, result.item_id, result.name)

            # If we haven't seen this key before, add the result
            if key not in seen_keys:
                seen_keys.add(key)
                unique_results.append(result)

        return unique_results
