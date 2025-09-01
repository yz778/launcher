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

        # Build set of actual commands from non-history results
        other_commands = set()
        for result in other_results:
            actual_command = result.metadata.get("actual_executed_command")
            if actual_command:
                other_commands.add(actual_command)

        # Filter history results - keep only those whose actual command
        # doesn't exist in the current non-history results
        filtered_history = []
        for history_result in history_results:
            history_command = history_result.metadata.get("actual_command")
            if not history_command or history_command not in other_commands:
                filtered_history.append(history_result)

        return other_results + filtered_history
