import logging
from typing import List

from launcher.plugins.base import SearchResult

logger = logging.getLogger(__name__)


class ResultDeduplicator:
    """
    Handles deduplication of search results by removing live entries
    when a history entry exists for the same actual command.
    History results are prioritized because they include usage statistics.
    """

    def deduplicate_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        Optimized deduplication using hash-based lookup that removes results
        by removing live results when history results exist for the same logical item.
        History results are prioritized because they show usage statistics and are preferred by users.
        A history result is considered to have priority if its original_result metadata contains
        plugin_id and item_id matching a live result's plugin_id and item_id.

        Args:
            results: List of search results to deduplicate

        Returns:
            List of deduplicated results
        """
        if not results:
            return results

        # Use a single pass with a dictionary to deduplicate and prioritize history results.
        # This is more efficient and avoids code duplication.
        unique_results_map = {}

        def get_logical_key(result: "SearchResult") -> tuple:
            """Determines the logical key for a search result."""
            if result.plugin_id == "history" and "original_result" in result.metadata:
                original_result_data = result.metadata["original_result"]
                original_plugin_id = original_result_data.get("plugin_id")
                original_item_id = original_result_data.get("item_id")
                original_name = original_result_data.get("name")

                if original_plugin_id and original_item_id:
                    return (original_plugin_id, original_item_id, original_name)

            return (result.plugin_id, result.item_id, result.name)

        for result in results:
            logical_key = get_logical_key(result)

            existing_result = unique_results_map.get(logical_key)

            # If we haven't seen this logical item, add it.
            if not existing_result:
                unique_results_map[logical_key] = result
                continue

            # If we have seen it, replace if the new one is a history result and the old one is not.
            if result.plugin_id == "history" and existing_result.plugin_id != "history":
                unique_results_map[logical_key] = result

        return list(unique_results_map.values())
