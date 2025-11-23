import json
import logging
import math
import os
import tempfile
import time
from typing import Any, Dict, List, Optional

from gi.repository import GLib

from launcher.plugins.base import SearchResult
from launcher.utils.scoring_system import FieldHighlight, calculate_match_score

logger = logging.getLogger(__name__)


class HistoryManager:
    """Manager for tracking and persisting launch history"""

    def make_search_result(self, entry, query):
        """
        Create a SearchResult from a history entry
        """
        result = entry.get("result")
        if not result:
            return None

        score = 0
        name_indices = set()
        description_indices = set()

        if query is None:
            score = entry.get("last_execution_time")
        else:
            name_l = entry.get("name").lower()
            desc_l = result["description"].lower()

            # Check name match
            name_match = calculate_match_score(query, name_l, is_name=True)
            if name_match:
                score = name_match[0]
                name_indices = name_match[1].name_indices

            # Check description match
            if desc_l and query in desc_l:
                desc_match = calculate_match_score(query, desc_l, is_name=False)
                if desc_match:
                    # Use higher score but keep both highlights
                    if desc_match[0] > score:
                        score = desc_match[0]
                    description_indices = desc_match[1].description_indices

        field_highlight = FieldHighlight(
            name_indices=name_indices, description_indices=description_indices
        )

        return SearchResult(
            plugin_id="history",
            item_id=entry.get("item_id"),
            name=entry.get("name"),
            description=result["description"],
            icon_spec=result["icon_spec"],
            score=score,
            metadata={
                "usage_count": entry.get("usage_count"),
                "original_result": result,
            },
            hilight=field_highlight,
        )

    def get_history_results(
        self, plugin_id: Optional[str] = None, exclude_plugin_only: bool = False
    ) -> List[SearchResult]:
        """
        Return a list of SearchResult objects for history entries.

        Args:
            plugin_id: If specified, only return history for this plugin
            exclude_plugin_only: If True, exclude items from plugins with track_history="plugin"

        Returns:
            List of SearchResult objects
        """
        from launcher import services

        results = []
        for entry in self.history:
            result_data = entry.get("result")
            if not result_data:
                continue

            # Filter by plugin if specified
            if plugin_id:
                if result_data.get("plugin_id") != plugin_id:
                    continue

            # Exclude plugin-only history from global history
            if exclude_plugin_only:
                entry_plugin_id = result_data.get("plugin_id")
                if entry_plugin_id and services.plugin_manager:
                    plugin = services.plugin_manager.get_plugin_by_id(entry_plugin_id)
                    if plugin and plugin.track_history == "plugin":
                        continue

            history_result = self.make_search_result(entry, None)
            if history_result:
                results.append(history_result)

        return results

    def get_plugin_history(self, plugin_id: str) -> List[SearchResult]:
        """
        Get history entries for a specific plugin.

        Args:
            plugin_id: The plugin ID to filter by

        Returns:
            List of SearchResult objects for this plugin
        """
        return self.get_history_results(plugin_id=plugin_id)

    __slots__ = ("history", "history_file", "_cleanup_scheduled")

    def __init__(self, config):
        self.history: List[Dict[str, Any]] = []
        self.history_file = None
        self._cleanup_scheduled = False

        if config and hasattr(config, "system"):
            self.load_history(config.system.history_file)

    def load_history(self, history_file_path: str) -> None:
        """
        Load history from file

        Args:
            history_file_path: Path to history file
        """
        self.history_file = history_file_path

        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)

        if os.path.isfile(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.history = data if isinstance(data, list) else []

                logger.info(f"Loaded history from {self.history_file}")
            except Exception as e:
                logger.error(f"Error loading history from {self.history_file}: {e}")
                self.history = []
        else:
            logger.info("History file not found, starting with empty history")
            self.history = []

    def save_history(self) -> bool:
        """
        Save history to file

        Returns:
            True if save was successful, False otherwise
        """
        if not self.history_file:
            logger.error("No history file specified")
            return False

        try:
            fd, temp_path = tempfile.mkstemp(
                dir=os.path.dirname(self.history_file), suffix=".tmp"
            )

            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(
                    self.history[:100],
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            os.replace(temp_path, self.history_file)
            logger.info(f"Saved history to {self.history_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving history to {self.history_file}: {e}")
            return False

    def add_history(self, result: SearchResult) -> None:
        """
        Record a successful execution in history.

        Args:
            result: The SearchResult object that was executed.
        """
        if not result:
            return

        existing_entry = self._get_entry(result)
        if existing_entry:
            existing_entry["usage_count"] += 1
            existing_entry["last_execution_time"] = time.time()
        else:
            unique_id = int(time.time())
            new_entry = {
                "item_id": f"history_{unique_id}",
                "name": f"{result.name} {' '.join(map(str, result.metadata.get('args', [])))}".strip(),
                "result": result.to_dict(),
                "last_execution_time": time.time(),
                "usage_count": 1,
            }
            self.history.append(new_entry)

        self.history.sort(key=lambda x: x["last_execution_time"], reverse=True)

    def _get_entry(self, result: SearchResult) -> Optional[Dict[str, Any]]:
        for entry in self.history:
            if result.plugin_id == "history" and entry.get("item_id") == result.item_id:
                return entry

            if (
                (orig := entry.get("result"))
                and orig.get("plugin_id") == result.plugin_id
                and orig.get("item_id") == result.item_id
                and orig.get("metadata", {}).get("actual_executed_command")
                == result.metadata.get("actual_executed_command")
            ):
                return entry

        return None

    def get_usage_count(self, plugin_id: str, item_id: str) -> int:
        """
        Get the usage count for an item from history. This will be the sum of
        all executions for a given item, regardless of arguments.

        Args:
            plugin_id: Plugin ID
            item_id: Item ID

        Returns:
            Usage count
        """

        for entry in self.history:
            if (
                (result := entry.get("result"))
                and result.get("plugin_id") == plugin_id
                and result.get("item_id") == item_id
            ):
                return entry.get("usage_count", 0)

        return 0

    def get_matching_history(self, partial_input: str, limit: int = 5) -> List[str]:
        """
        Get matching history entries for autocomplete.

        Args:
            partial_input: Partial user input to match against
            limit: Maximum number of results to return

        Returns:
            List of matching user inputs, sorted by most recent first
        """
        if not partial_input.strip():
            return []

        partial_lower = partial_input.lower()
        matches = []

        for entry in self.history:
            name = entry.get("name", "")
            if name.lower().startswith(partial_lower) and name.lower() != partial_lower:
                matches.append(name)

            if len(matches) >= limit:
                break

        return matches

    def remove_history_entry(self, item_id: str) -> bool:
        """
        Remove a history entry by command.

        Args:
            command: The command of the entry to remove.

        Returns:
            True if an entry was removed, False otherwise.
        """
        if not item_id:
            return False
        original_length = len(self.history)
        self.history = [
            entry for entry in self.history if entry.get("item_id") != item_id
        ]
        return len(self.history) < original_length

    def adjust_score(self, plugin_id: str, item_id: str, base_score: float) -> float:
        """
        Adjust a score based on usage history.

        Args:
            plugin_id: Plugin ID
            item_id: Item ID
            base_score: Base score

        Returns:
            Adjusted score
        """
        total_count = self.get_usage_count(plugin_id, item_id)
        if total_count > 0:
            boost = min(50, 10 * math.log2(total_count + 1))
            return base_score + boost
        return base_score

    def schedule_background_cleanup(self) -> None:
        """
        Schedule background cleanup to run when the system is idle.
        This should be called after all services are initialized.
        """
        if self._cleanup_scheduled:
            return

        self._cleanup_scheduled = True
        # Schedule cleanup to run at idle priority after a short delay
        GLib.timeout_add_seconds(5, self._start_background_cleanup)
        logger.info("Background history cleanup scheduled")

    def _start_background_cleanup(self) -> bool:
        """
        Start the background cleanup process.
        Returns False to prevent the timeout from repeating.
        """
        try:
            self._validate_and_cleanup_history()
        except Exception as e:
            logger.error(f"Error during background history cleanup: {e}")
        return False  # Don't repeat

    def _validate_and_cleanup_history(self) -> None:
        """
        Validate all history entries and remove invalid ones.
        """
        from launcher import services

        if not hasattr(services, "plugin_manager") or not services.plugin_manager:
            logger.warning("Plugin manager not available for history validation")
            return

        logger.info("Starting background history validation")
        initial_count = len(self.history)
        valid_entries = []

        for entry in self.history:
            result_data = entry.get("result")
            if not result_data:
                continue

            plugin_id = result_data.get("plugin_id")
            item_id = result_data.get("item_id")

            if not plugin_id or not item_id:
                continue

            # Get the plugin and validate the item
            plugin = services.plugin_manager.get_plugin_by_id(plugin_id)
            if plugin and hasattr(plugin, "validate_item"):
                try:
                    if plugin.validate_item(item_id):
                        valid_entries.append(entry)
                    else:
                        logger.debug(
                            f"Removing invalid history entry: {plugin_id}:{item_id}"
                        )
                except Exception as e:
                    logger.error(f"Error validating {plugin_id}:{item_id}: {e}")
                    # Keep the entry if validation fails
                    valid_entries.append(entry)
            else:
                # Keep entries for plugins that don't support validation
                valid_entries.append(entry)

        # Update history with valid entries
        self.history = valid_entries
        removed_count = initial_count - len(valid_entries)

        if removed_count > 0:
            logger.info(f"Removed {removed_count} invalid history entries")
            self.save_history()
        else:
            logger.info("All history entries are valid")

    def cleanup(self) -> None:
        """
        Clean up resources, ensuring history is saved on exit.
        """
        self.save_history()
        logger.info("HistoryManager cleaned up and history saved")
