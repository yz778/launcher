from launcher.plugins.base import Plugin, SearchResult
from typing import List
import launcher.services as services

import logging

logger = logging.getLogger(__name__)


class HistoryPlugin(Plugin):
    """Plugin for searching through command history"""

    DEFAULTS = {
        "enabled": True,
        "max_results": 10,
        "min_query_length": 2,
    }

    def __init__(self):
        super().__init__()

    def get_id(self) -> str:
        return "history"

    def get_name(self) -> str:
        return "History Search"

    def get_description(self) -> str:
        return "Search through command execution history"

    def initialize(self, config) -> bool:
        super().initialize(config)
        logger.info("History plugin initialized successfully")
        return True

    def search(self, query: str) -> List[SearchResult]:
        query = query.strip().lower()
        if len(query) < getattr(
            self.config, "min_query_length", self.DEFAULTS["min_query_length"]
        ):
            return []

        history_manager = services.history_manager
        history_entries = history_manager.history
        results = []

        for entry in history_entries:
            result = entry.get("result")
            name = entry.get("name").lower()
            description = result["description"].lower()

            if query in name or query in description:
                history_result = history_manager.make_search_result(entry, query)
                if history_result:
                    results.append(history_result)

        results.sort(key=lambda r: r.score, reverse=True)
        return results[
            : getattr(self.config, "max_results", self.DEFAULTS["max_results"])
        ]

    def execute(self, result: SearchResult) -> bool:
        original_result_dict = result.metadata.get("original_result")
        if not original_result_dict:
            logger.error("No original_result in metadata")
            return False

        original_result = SearchResult.from_dict(original_result_dict)

        plugin_manager = services.plugin_manager
        if not plugin_manager:
            logger.error("Plugin manager not available")
            return False

        return plugin_manager.execute(original_result)
