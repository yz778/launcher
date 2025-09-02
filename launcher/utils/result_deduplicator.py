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
        Remove history results if the same actual command exists from other plugins.

        Args:
            results: List of search results to deduplicate

        Returns:
            List of deduplicated results
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

        deduplicated_results = []
        seen_keys = set()

        # Prioritize non-history results
        for result in other_results:
            key = (result.plugin_id, result.item_id)
            if key not in seen_keys:
                deduplicated_results.append(result)
                seen_keys.add(key)

        # Add history results only if the original item hasn't been seen from a live plugin
        for history_result in history_results:
            original_plugin_id = history_result.metadata.get("original_plugin_id")
            original_item_id = history_result.metadata.get("original_item_id")
            key = (original_plugin_id, original_item_id)

            if key not in seen_keys:
                deduplicated_results.append(history_result)
                seen_keys.add(key)

        return deduplicated_results
