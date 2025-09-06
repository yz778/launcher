from launcher.plugins.base import SearchResult
from typing import List
import logging

logger = logging.getLogger(__name__)


class ResultDeduplicator:
    """
    Handles deduplication of search results by removing history entries
    when the same actual command exists from another plugin.
    """

    def deduplicate_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        Deduplicate results by removing all results from other_results if history already captured it.
        A history result is considered to have captured a result if its metadata contains
        the original_plugin_id and original_item_id matching a live result's plugin_id and item_id.

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

        if not history_results:
            return results

        # Build a set of (original_plugin_id, original_item_id, args) from history results
        history_keys = set()
        for history_result in history_results:
            result = history_result.metadata.get("original_result")
            plugin_id = result.get("plugin_id")
            item_id = result.get("item_id")
            args = "".join(result.get("metadata").get("args", []))
            history_keys.add((plugin_id, item_id, args))

        # Remove all other_results that are captured by history
        filtered_other_results = [
            r for r in other_results if (r.plugin_id, r.item_id, "") not in history_keys
        ]

        return history_results + filtered_other_results
