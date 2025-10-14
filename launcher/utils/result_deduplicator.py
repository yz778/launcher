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

        # Two-phase approach:
        # 1. Identify all logical items and prioritize history results over live results
        # 2. Build result list, preferring history results over live results for same logical item

        # Phase 1: First pass - collect all logical keys from history results to give them priority
        history_logical_keys = set()

        for result in results:
            if result.plugin_id == "history" and "original_result" in result.metadata:
                # This is a history result, use its original identity
                original_result_data = result.metadata["original_result"]
                original_plugin_id = original_result_data.get("plugin_id")
                original_item_id = original_result_data.get("item_id")
                original_name = original_result_data.get("name")

                if original_plugin_id and original_item_id:
                    logical_key = (original_plugin_id, original_item_id, original_name)
                    history_logical_keys.add(logical_key)

        # Phase 2: Build the final list, skipping live results that have corresponding history results
        seen_logical_keys = set()
        unique_results = []

        for result in results:
            # Determine the logical key for this result
            if result.plugin_id == "history" and "original_result" in result.metadata:
                # This is a history result, use its original identity
                original_result_data = result.metadata["original_result"]
                original_plugin_id = original_result_data.get("plugin_id")
                original_item_id = original_result_data.get("item_id")
                original_name = original_result_data.get("name")

                if original_plugin_id and original_item_id:
                    logical_key = (original_plugin_id, original_item_id, original_name)
                else:
                    # If no proper original_result data, use actual result data
                    logical_key = (result.plugin_id, result.item_id, result.name)
            else:
                # This is a live plugin result
                logical_key = (result.plugin_id, result.item_id, result.name)

            # Skip if we've already seen this logical item
            if logical_key in seen_logical_keys:
                continue

            # For live results, skip if there's a corresponding history result (same logical item)
            if result.plugin_id != "history" and logical_key in history_logical_keys:
                continue

            # Add the result
            seen_logical_keys.add(logical_key)
            unique_results.append(result)

        return unique_results
