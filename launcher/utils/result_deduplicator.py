#!/usr/bin/env python3

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
        Deduplicate results by keeping the highest-scored version of each item.

        Args:
            results: List of search results to deduplicate

        Returns:
            List of deduplicated results with highest-scored versions
        """
        if not results:
            return results

        # Separate history results from other results
        history_results = []
        other_results = []

        for result in results:
            if getattr(result, "plugin_id", None) == "history":
                history_results.append(result)
            else:
                other_results.append(result)

        if not history_results or not other_results:
            return results

        # Create a mapping of (original_plugin_id, original_item_id) -> best_result
        best_results = {}

        # First, add all live plugin results
        for result in other_results:
            key = (result.plugin_id, result.item_id)
            best_results[key] = result

        # Then, check history results and keep them if they have higher scores
        for history_result in history_results:
            original_plugin_id = history_result.metadata.get("original_plugin_id")
            original_item_id = history_result.metadata.get("original_item_id")
            key = (original_plugin_id, original_item_id)

            if key in best_results:
                live_result = best_results[key]
                if history_result.score > live_result.score:
                    best_results[key] = history_result
            else:
                best_results[key] = history_result

        return list(best_results.values())
