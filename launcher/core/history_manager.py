#!/usr/bin/env python3

import os
import json
import logging
import time
import base64
from typing import Dict, Any, List, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf

logger = logging.getLogger(__name__)


class HistoryManager:
    """Manager for tracking and persisting launch history"""

    __slots__ = ("user_input_history", "history_file")

    def __init__(self, config=None):
        self.user_input_history: List[
            Dict[str, Any]
        ] = []  # List of user input entries with timestamps
        self.history_file = None

        if config:
            history_file = config.get("general", {}).get(
                "history_file", "~/.local/share/launcher/history.json"
            )
            self.load_history(history_file)

    def load_history(self, history_file_path: str) -> None:
        """
        Load history from file

        Args:
            history_file_path: Path to history file
        """
        self.history_file = os.path.expanduser(history_file_path)

        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)

        if os.path.isfile(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    self.user_input_history = json.load(f)

                logger.info(f"Loaded history from {self.history_file}")
            except Exception as e:
                logger.error(f"Error loading history from {self.history_file}: {e}")
                self.user_input_history = []
        else:
            logger.info("History file not found, starting with empty history")
            self.user_input_history = []

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
                json.dump(self.user_input_history, f, indent=2)
            logger.info(f"Saved history to {self.history_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving history to {self.history_file}: {e}")
            return False

    def get_usage_count(self, plugin_id: str, item_id: str) -> int:
        """
        Get the usage count for an item from history

        Args:
            plugin_id: Plugin ID
            item_id: Item ID

        Returns:
            Usage count
        """
        # Find the most recent entry for this plugin_id/item_id
        for entry in self.user_input_history:
            if entry.get("plugin_id") == plugin_id and entry.get("item_id") == item_id:
                return entry.get("usage_count", 1)
        return 0

    def add_execution(
        self,
        plugin_id: str,
        item_id: str,
        executed_command: str,
        original_user_input: str,
        result_name: str = None,
        icon_pixbuf=None,
    ) -> None:
        """
        Record a successful execution in history.

        Args:
            plugin_id: Plugin ID that was executed
            item_id: Item ID that was executed
            user_input: The exact text that the user typed before submitting
            result_name: Display name of the executed item
            icon_pixbuf: The actual icon pixbuf to store for better performance
        """
        current_time = time.time()

        # Add to user input history
        self.add_user_input_history(
            original_user_input,
            plugin_id,
            item_id,
            current_time,
            executed_command,
            result_name,
            icon_pixbuf,
        )

    def add_user_input_history(
        self,
        user_input: str,
        plugin_id: str,
        item_id: str,
        timestamp: float = None,
        executed_command_string: str = None,
        result_name: str = None,
        icon_pixbuf=None,
    ) -> None:
        """
        Add user input to history, removing duplicates and maintaining order.

        Args:
            user_input: The exact text that the user typed
            plugin_id: Plugin ID that was executed
            item_id: Item ID that was executed
            timestamp: Timestamp when executed (defaults to current time)
            result_name: Display name of the executed item
            icon_pixbuf: The actual icon pixbuf to store for better performance
        """
        if timestamp is None:
            timestamp = time.time()

        # Find existing entry with same plugin_id/item_id to get current usage count
        current_usage_count = 0
        for entry in self.user_input_history:
            if entry.get("plugin_id") == plugin_id and entry.get("item_id") == item_id:
                current_usage_count = entry.get("usage_count", 0)
                break

        # Remove any existing entry with the same user input
        self.user_input_history = [
            entry
            for entry in self.user_input_history
            if entry.get("user_input", "").lower() != user_input.lower()
        ]

        # Add new entry at the beginning (most recent first)
        entry = {
            "user_input": user_input,
            "plugin_id": plugin_id,
            "item_id": item_id,
            "timestamp": timestamp,
            "result_name": result_name,
            "usage_count": current_usage_count + 1,
        }

        # Store the actual icon data if provided and plugin is executable
        if icon_pixbuf and plugin_id == "executable":
            try:
                # Convert pixbuf to PNG data and then base64 encode
                icon_data = self._pixbuf_to_base64(icon_pixbuf)
                if icon_data:
                    entry["icon_data"] = icon_data
                    logger.debug(f"Stored icon data for executable: {result_name}")
            except Exception as e:
                logger.warning(f"Failed to store icon data for {result_name}: {e}")

        self.user_input_history.insert(0, entry)

        # Keep only the most recent 100 entries to prevent unlimited growth
        self.user_input_history = self.user_input_history[:100]

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

        for entry in self.user_input_history:
            user_input = entry.get("user_input", "")
            if (
                user_input.lower().startswith(partial_lower)
                and user_input.lower() != partial_lower
            ):
                matches.append(user_input)

            if len(matches) >= limit:
                break

        return matches

    def get_recent_history(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get the most recent user inputs with their metadata.

        Args:
            limit: Maximum number of results to return

        Returns:
            List of recent history entries with full metadata
        """
        return self.user_input_history[:limit]

    def remove_history_entries_by_ids(
        self, entries_to_remove: List[Dict[str, Any]]
    ) -> int:
        """
        Remove multiple history entries based on a list of identifiers.

        Args:
            entries_to_remove: A list of dictionaries, where each dictionary
                               contains "plugin_id", "item_id", and "timestamp"
                               to uniquely identify a history entry.

        Returns:
            The number of entries successfully removed.
        """
        original_length = len(self.user_input_history)

        # Create a set of identifiable tuples for faster lookup
        remove_set = set()
        for entry in entries_to_remove:
            # Ensure the necessary keys are present
            if all(k in entry for k in ["plugin_id", "item_id", "timestamp"]):
                remove_set.add(
                    (entry["plugin_id"], entry["item_id"], entry["timestamp"])
                )
            else:
                logger.warning(
                    f"Invalid entry_to_remove provided: {entry}. Missing required keys."
                )

        new_history = []
        for entry in self.user_input_history:
            entry_identifier = (
                entry.get("plugin_id"),
                entry.get("item_id"),
                entry.get("timestamp"),
            )
            if entry_identifier not in remove_set:
                new_history.append(entry)
            else:
                logger.debug(f"Removing history entry: {entry_identifier}")

        self.user_input_history = new_history
        removed_count = original_length - len(self.user_input_history)

        if removed_count > 0:
            self.save_history()
            logger.info(f"Removed {removed_count} history entries.")
        else:
            logger.info("No history entries matched for removal.")

        return removed_count

    def remove_user_input(self, user_input: str) -> bool:
        """
        Remove a user input entry from history

        Args:
            user_input: User input to remove

        Returns:
            True if entry was removed, False otherwise
        """
        original_length = len(self.user_input_history)
        self.user_input_history = [
            entry
            for entry in self.user_input_history
            if entry.get("user_input", "").lower() != user_input.lower()
        ]

        if len(self.user_input_history) < original_length:
            self.save_history()
            return True
        return False

    def adjust_score(self, plugin_id: str, item_id: str, base_score: float) -> float:
        """
        Adjust a score based on usage history

        Args:
            plugin_id: Plugin ID
            item_id: Item ID
            base_score: Base score

        Returns:
            Adjusted score
        """
        count = self.get_usage_count(plugin_id, item_id)
        if count > 0:
            import math

            boost = min(50, 10 * math.log2(count + 1))
            return base_score + boost
        return base_score

    def _pixbuf_to_base64(self, pixbuf) -> Optional[str]:
        """
        Convert a GdkPixbuf to base64 encoded PNG data

        Args:
            pixbuf: GdkPixbuf to convert

        Returns:
            Base64 encoded PNG data, or None if conversion fails
        """
        try:
            # Save pixbuf to PNG bytes
            success, buffer = pixbuf.save_to_bufferv("png", [], [])
            if success:
                # Encode to base64
                return base64.b64encode(buffer).decode("utf-8")
        except Exception as e:
            logger.error(f"Error converting pixbuf to base64: {e}")
        return None

    def _base64_to_pixbuf(
        self, icon_data: str, icon_size: int = 48
    ) -> Optional[object]:
        """
        Convert base64 encoded PNG data back to GdkPixbuf

        Args:
            icon_data: Base64 encoded PNG data
            icon_size: Desired icon size

        Returns:
            GdkPixbuf or None if conversion fails
        """
        try:
            # Decode from base64
            png_data = base64.b64decode(icon_data)

            # Create pixbuf from PNG data
            from gi.repository import Gio

            input_stream = Gio.MemoryInputStream.new_from_data(png_data)
            pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(
                input_stream, icon_size, icon_size, True, None
            )
            return pixbuf
        except Exception as e:
            logger.error(f"Error converting base64 to pixbuf: {e}")
        return None

    def get_stored_icon(self, history_entry: Dict[str, Any], icon_size: int = 48):
        """
        Get the stored icon from a history entry

        Args:
            history_entry: History entry dict
            icon_size: Desired icon size

        Returns:
            GdkPixbuf or None if no stored icon
        """
        icon_data = history_entry.get("icon_data")
        if icon_data:
            return self._base64_to_pixbuf(icon_data, icon_size)
        return None
