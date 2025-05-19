#!/usr/bin/env python3

import os
import json
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class HistoryManager:
    """Manager for tracking and persisting launch history"""

    def __init__(self, config=None):
        self.history = {}  # plugin_id:item_id -> count
        self.history_file = None

        if config:
            history_file = config.get("general", {}).get(
                "history_file", "~/.local/share/launcher/history.json"
            )
            self.load_history(history_file)

    def load_history(self, history_file_path: str) -> Dict[str, int]:
        """
        Load history from file

        Args:
            history_file_path: Path to history file

        Returns:
            Loaded history
        """
        self.history_file = os.path.expanduser(history_file_path)

        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)

        if os.path.isfile(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    self.history = json.load(f)
                logger.info(f"Loaded history from {self.history_file}")
            except Exception as e:
                logger.error(f"Error loading history from {self.history_file}: {e}")
                self.history = {}
        else:
            logger.info(f"History file not found, starting with empty history")
            self.history = {}

        return self.history

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
            with open(self.history_file, "w") as f:
                json.dump(self.history, f)
            logger.info(f"Saved history to {self.history_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving history to {self.history_file}: {e}")
            return False

    def get_count(self, plugin_id: str, item_id: str) -> int:
        """
        Get the launch count for an item

        Args:
            plugin_id: Plugin ID
            item_id: Item ID

        Returns:
            Launch count
        """
        key = f"{plugin_id}:{item_id}"
        return self.history.get(key, 0)

    def increment_count(self, plugin_id: str, item_id: str) -> int:
        """
        Increment the launch count for an item

        Args:
            plugin_id: Plugin ID
            item_id: Item ID

        Returns:
            New launch count
        """
        key = f"{plugin_id}:{item_id}"
        count = self.history.get(key, 0) + 1
        self.history[key] = count
        self.save_history()
        return count

    def remove_entry(self, plugin_id: str, item_id: str) -> bool:
        """
        Remove an entry from history

        Args:
            plugin_id: Plugin ID
            item_id: Item ID

        Returns:
            True if entry was removed, False otherwise
        """
        key = f"{plugin_id}:{item_id}"
        if key in self.history:
            del self.history[key]
            self.save_history()
            return True
        return False

    def adjust_score(self, plugin_id: str, item_id: str, base_score: float) -> float:
        """
        Adjust a score based on history

        Args:
            plugin_id: Plugin ID
            item_id: Item ID
            base_score: Base score

        Returns:
            Adjusted score
        """
        count = self.get_count(plugin_id, item_id)
        if count > 0:
            import math

            boost = min(50, 10 * math.log2(count + 1))
            return base_score + boost
        return base_score
