#!/usr/bin/env python3


from launcher.plugins.base import SearchResult
from typing import Dict, Any, List, Optional
import logging
import math
import os
import time
import json
import tempfile

logger = logging.getLogger(__name__)


class HistoryManager:
    """Manager for tracking and persisting launch history"""

    __slots__ = ("history", "history_file")

    def __init__(self, config=None):
        self.history: List[Dict[str, Any]] = []
        self.history_file = None

        if config:
            general_config = config.get("general", {})
            history_file = general_config.get("history_file")
            self.load_history(history_file)

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
            existing_entry["times_executed"] += 1
            existing_entry["last_execution_time"] = time.time()
        else:
            unique_id = int(time.time())
            new_entry = {
                "item_id": f"history_{unique_id}",
                "name": (
                    result.name + " " + " ".join(result.metadata.get("args", []))
                ).strip(),
                "result": result.to_dict(),
                "last_execution_time": time.time(),
                "times_executed": 1,
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
                return entry.get("times_executed", 0)

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

    def remove_history_entry(self, command: str) -> bool:
        """
        Remove a history entry by command.

        Args:
            command: The command of the entry to remove.

        Returns:
            True if an entry was removed, False otherwise.
        """
        if not command:
            return False
        original_length = len(self.history)
        self.history = [
            entry
            for entry in self.history
            if entry.get("result", {})
            .get("metadata", {})
            .get("actual_executed_command")
            != command
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

    def cleanup(self) -> None:
        """
        Clean up resources, ensuring history is saved on exit.
        """
        self.save_history()
        logger.info("HistoryManager cleaned up and history saved.")
