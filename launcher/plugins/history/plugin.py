#!/usr/bin/env python3

from ..base import Plugin, SearchResult
from launcher.utils.scoring_system import calculate_match_score
from typing import List, Dict, Any
from ui.launcher_window import AppListItem
import logging

logger = logging.getLogger(__name__)


class HistoryPlugin(Plugin):
    """Plugin for searching through command history"""

    defaults = {
        "enabled": True,
        "max_results": 10,
        "min_query_length": 2,
    }

    def __init__(self):
        super().__init__()
        self.history_manager = None
        self.plugin_manager = None

    def get_id(self) -> str:
        return "history"

    def get_name(self) -> str:
        return "History Search"

    def get_description(self) -> str:
        return "Search through command execution history"

    def initialize(self, config: Dict[str, Any], config_manager=None) -> bool:
        self.config = config
        logger.info("History plugin initialized successfully")
        return True

    def set_managers(self, history_manager, plugin_manager):
        self.history_manager = history_manager
        self.plugin_manager = plugin_manager
        logger.info("History plugin managers set successfully")

    def _make_search_result(self, entry, query):
        """
        Create a SearchResult from a history entry
        """
        result = entry.get("result")
        if not result:
            return None

        score = 0

        if query is None:
            score = entry.get("last_execution_time")
        else:
            name_l = entry.get("name").lower()
            desc_l = result["description"].lower()
            score = calculate_match_score(query, name_l, is_name=True)
            if desc_l and query in desc_l:
                score = max(score, calculate_match_score(query, desc_l, is_name=False))

        return SearchResult(
            plugin_id=self.get_id(),
            item_id=entry.get("item_id"),
            name=entry.get("name"),
            description=result["description"],
            icon_spec=result["icon_spec"],
            score=score,
            metadata={
                "usage_count": entry.get("usage_count"),
                "original_result": result,
                "track_history": True,
            },
        )

    def search(self, query: str) -> List[SearchResult]:
        query = query.strip().lower()
        if len(query) < self.config.get("min_query_length"):
            return []

        history_entries = self.history_manager.history
        results = []

        for entry in history_entries:
            result = entry.get("result")
            name = entry.get("name").lower()
            description = result["description"].lower()

            if query in name or query in description:
                history_result = self._make_search_result(entry, query)
                if history_result:
                    results.append(history_result)

        results.sort(key=lambda r: r.score, reverse=True)
        return results[: self.config.get("max_results", 10)]

    def execute(self, result: SearchResult) -> bool:
        original_result_dict = result.metadata.get("original_result")
        if not original_result_dict:
            logger.error("No original_result in metadata")
            return False

        original_result = SearchResult.from_dict(original_result_dict)

        if not self.plugin_manager:
            logger.error("Plugin manager not available")
            return False

        return self.plugin_manager.execute(original_result)

    def _populate_recent_history(self, launcher_window):
        history = self.history_manager.history
        if not history:
            return

        results = []
        for entry in history:
            history_result = self._make_search_result(entry, None)
            if not history_result:
                continue

            results.append(history_result)
            list_item = AppListItem(
                history_result,
                icon_size=launcher_window.icon_size or 48,
                usage_count=entry.get("usage_count", 0),
                query="",
            )
            list_item.set_name("history-item")
            launcher_window.list_box.add(list_item)

        launcher_window.list_box.show_all()
        launcher_window.scrolled.show()

        count_text = f"{len(history)} history item{'s' if len(history) != 1 else ''}"
        launcher_window._setup_results_display(results, count_text)

    def register_with_launcher(self, launcher_window=None):
        """Register the history handler for empty input globally."""
        self.__class__.register_global_empty_input_handler(
            self._populate_recent_history
        )
