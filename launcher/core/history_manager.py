#!/usr/bin/env python3

import os
import json
import logging
import time
import base64
import math
from typing import Dict, Any, List, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf

from launcher.utils.result_analyzer import ResultAnalyzer
from launcher.plugins.base import SearchResult

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
            general_config = config.get("general", {})
            history_file = general_config.get(
                "history_file", "~/.local/share/launcher/history.json"
            )
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
        try:
            # Validate input parameters
            if not plugin_id or not item_id:
                logger.debug("Empty plugin_id or item_id in get_usage_count")
                return 0

            # Handle corrupted history data
            if not isinstance(self.user_input_history, list):
                logger.warning(
                    f"History data is corrupted in get_usage_count - not a list ({type(self.user_input_history)})"
                )
                return 0

            # Find the most recent entry for this plugin_id/item_id
            for entry in self.user_input_history:
                try:
                    if not isinstance(entry, dict):
                        continue

                    if (
                        entry.get("plugin_id") == plugin_id
                        and entry.get("item_id") == item_id
                    ):
                        usage_count = entry.get("usage_count", 1)
                        return (
                            usage_count if isinstance(usage_count, (int, float)) else 1
                        )
                except Exception as e:
                    logger.debug(
                        f"Error processing history entry in get_usage_count: {e}"
                    )
                    continue

            return 0

        except Exception as e:
            logger.error(f"Error getting usage count for {plugin_id}:{item_id}: {e}")
            return 0

    def add_execution(
        self,
        plugin_id: str,
        item_id: str,
        executed_command: str,
        original_user_input: str,
        description: str = None,
        icon_pixbuf=None,
    ) -> None:
        """
        Record a successful execution in history.

        Args:
            plugin_id: Plugin ID that was executed
            item_id: Item ID that was executed
            user_input: The exact text that the user typed before submitting
            description: Description of the executed item
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
            description,
            icon_pixbuf,
        )

    def _normalize_command_for_comparison(self, command: str) -> Optional[str]:
        """
        Normalizes a command string for comparison, handling common executable variations.
        For example, 'firefox.desktop' and '/usr/bin/firefox' should normalize to the same string.
        """
        if not command:
            return None

        # Get the base name without directory
        base_name = os.path.basename(command)

        # Remove common executable extensions or .desktop
        if base_name.endswith(".desktop"):
            base_name = base_name[: -len(".desktop")]
        # Add more specific extension handling if needed, e.g., .py, .sh, but be careful
        # For now, keep it simple to avoid false positives.

        # Convert to lowercase for case-insensitive comparison
        return base_name.lower()

    def add_user_input_history(
        self,
        user_input: str,
        plugin_id: str,
        item_id: str,
        timestamp: float = None,
        executed_command_string: str = None,
        description: str = None,
        icon_pixbuf=None,
    ) -> None:
        """
        Add user input to history, removing duplicates and maintaining order.
        Merges usage counts for executables that resolve to the same command.

        Args:
            user_input: The exact text that the user typed
            plugin_id: Plugin ID that was executed
            item_id: Item ID that was executed
            timestamp: Timestamp when executed (defaults to current time)
            executed_command_string: The actual command string that was executed.
            description: Description of the executed item
            icon_pixbuf: The actual icon pixbuf to store for better performance
        """
        if timestamp is None:
            timestamp = time.time()

        current_usage_count = self._process_existing_entries(
            user_input, plugin_id, executed_command_string
        )

        entry = self._create_history_entry(
            user_input,
            plugin_id,
            item_id,
            timestamp,
            executed_command_string,
            description,
            current_usage_count + 1,
            icon_pixbuf,
        )

        self._add_and_limit_history(entry)

    def _process_existing_entries(
        self, user_input: str, plugin_id: str, executed_command_string: str
    ) -> int:
        """Process existing entries for duplicates and merging"""
        current_usage_count = 0
        entries_to_remove = []

        normalized_new_command = None
        if plugin_id in ["executable", "desktop_file"] and executed_command_string:
            normalized_new_command = self._normalize_command_for_comparison(
                executed_command_string
            )

        for entry in self.user_input_history:
            if self._is_exact_duplicate(entry, user_input):
                current_usage_count = entry.get("usage_count", 0)
                entries_to_remove.append(entry)
                continue

            if self._should_merge_commands(entry, normalized_new_command):
                current_usage_count += entry.get("usage_count", 0)
                entries_to_remove.append(entry)
                logger.debug(
                    f"Merging history entry for command '{executed_command_string}' with existing entry: {entry.get('user_input')}"
                )

        self._remove_entries(entries_to_remove)
        return current_usage_count

    def _is_exact_duplicate(self, entry: dict, user_input: str) -> bool:
        """Check if entry is an exact duplicate of user input"""
        return entry.get("user_input", "").lower() == user_input.lower()

    def _should_merge_commands(self, entry: dict, normalized_new_command: str) -> bool:
        """Check if entry should be merged based on normalized command"""
        if not normalized_new_command or not entry.get("executed_command"):
            return False

        normalized_existing_command = self._normalize_command_for_comparison(
            entry["executed_command"]
        )
        return normalized_new_command == normalized_existing_command

    def _remove_entries(self, entries_to_remove: list) -> None:
        """Remove specified entries from history"""
        self.user_input_history = [
            entry for entry in self.user_input_history if entry not in entries_to_remove
        ]

    def _create_history_entry(
        self,
        user_input: str,
        plugin_id: str,
        item_id: str,
        timestamp: float,
        executed_command_string: str,
        description: str,
        usage_count: int,
        icon_pixbuf,
    ) -> dict:
        """Create a new history entry"""
        entry = {
            "user_input": user_input,
            "plugin_id": plugin_id,
            "item_id": item_id,
            "timestamp": timestamp,
            "description": description,
            "usage_count": usage_count,
            "executed_command": executed_command_string,
        }

        if icon_pixbuf:
            self._store_icon_data(entry, icon_pixbuf, plugin_id, description)

        return entry

    def _store_icon_data(
        self, entry: dict, icon_pixbuf, plugin_id: str, description: str
    ) -> None:
        """Store icon data in history entry"""
        try:
            icon_data = self._pixbuf_to_base64(icon_pixbuf)
            if icon_data:
                entry["icon_data"] = icon_data
                logger.debug(f"Stored icon data for {plugin_id}: {description}")
            else:
                logger.warning(
                    f"Failed to convert icon to base64 for {plugin_id}: {description}"
                )
        except Exception as e:
            logger.error(f"Exception storing icon data for {description}: {e}")

    def _add_and_limit_history(self, entry: dict) -> None:
        """Add entry to history and limit to 100 entries"""
        self.user_input_history.insert(0, entry)
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

    def should_store_in_history(
        self,
        user_input: str,
        search_results: List[SearchResult],
        executed_result: SearchResult,
    ) -> bool:
        """
        Determine if execution should be stored in history based on match quality.

        Args:
            user_input: Original user query
            search_results: All search results that were available
            executed_result: The result that was actually executed

        Returns:
            True if should store, False otherwise
        """
        try:
            if not self._validate_storage_inputs(user_input, executed_result):
                return True

            search_results = self._normalize_search_results(search_results)
            match_quality = self._get_match_quality_safely(user_input, executed_result)

            return self._determine_storage_decision(
                match_quality, user_input, executed_result
            )

        except (ImportError, MemoryError, RecursionError) as e:
            logger.error(
                f"{type(e).__name__} during storage analysis: {e} - storing by default"
            )
            return True
        except Exception as e:
            logger.error(
                f"Critical error analyzing match quality for history storage: {e}"
            )
            logger.debug(
                f"Error details - user_input: {repr(user_input)}, executed_result: {repr(executed_result)}"
            )
            return True

    def _validate_storage_inputs(
        self, user_input: str, executed_result: SearchResult
    ) -> bool:
        """Validate inputs for storage decision"""
        if not user_input:
            logger.debug(
                f"User input is falsy ({type(user_input)}): {repr(user_input)} - storing by default"
            )
            return False

        if not executed_result:
            logger.debug(
                f"Executed result is falsy ({type(executed_result)}) - storing by default"
            )
            return False

        try:
            result_name = getattr(executed_result, "name", None)
            if result_name is None:
                logger.warning(
                    "Executed result missing 'name' attribute - storing by default"
                )
                return False
        except Exception as attr_error:
            logger.warning(
                f"Error accessing executed result attributes: {attr_error} - storing by default"
            )
            return False

        logger.debug(
            f"Analyzing storage decision for user_input='{user_input}' -> result='{result_name}'"
        )
        return True

    def _normalize_search_results(
        self, search_results: List[SearchResult]
    ) -> List[SearchResult]:
        """Normalize search results parameter"""
        if search_results is None:
            logger.debug("Search results is None - continuing with analysis")
            return []
        elif not isinstance(search_results, list):
            logger.warning(
                f"Search results is not a list ({type(search_results)}) - converting to empty list"
            )
            return []
        return search_results

    def _get_match_quality_safely(
        self, user_input: str, executed_result: SearchResult
    ) -> str:
        """Get match quality with error handling"""
        try:
            match_quality = ResultAnalyzer.get_match_quality(
                user_input, executed_result
            )
            logger.debug(f"Match quality analysis result: '{match_quality}'")

            if not isinstance(match_quality, str):
                logger.warning(
                    f"Match quality is not a string ({type(match_quality)}): {match_quality} - using 'none'"
                )
                return "none"

            return match_quality.lower().strip()
        except (AttributeError, TypeError) as e:
            logger.warning(
                f"{type(e).__name__} in match quality analysis: {e} - using 'none'"
            )
            return "none"
        except Exception as e:
            logger.error(
                f"Unexpected error in match quality analysis: {e} - using 'none'"
            )
            return "none"

    def _determine_storage_decision(
        self, match_quality: str, user_input: str, executed_result: SearchResult
    ) -> bool:
        """Determine whether to store based on match quality"""
        if match_quality == "exact":
            logger.debug("Storing exact match in history")
            return True
        elif match_quality == "partial":
            return self._handle_partial_match(user_input, executed_result)
        elif match_quality == "fuzzy":
            logger.debug("Storing fuzzy match in history")
            return True
        elif match_quality == "none":
            logger.debug(
                "No match detected - storing by default (conservative approach)"
            )
            return True
        else:
            logger.debug(
                f"Unknown match quality '{match_quality}' - storing by default"
            )
            return True

    def _handle_partial_match(
        self, user_input: str, executed_result: SearchResult
    ) -> bool:
        """Handle storage decision for partial matches"""
        try:
            has_args = ResultAnalyzer.has_command_arguments(user_input, executed_result)
            logger.debug(f"Partial match - command arguments detected: {has_args}")

            if has_args:
                logger.debug("Storing partial match with command arguments in history")
                return True
            else:
                logger.debug(
                    "Skipping storage of partial match without command arguments"
                )
                return False
        except Exception as args_error:
            logger.warning(
                f"Error checking command arguments: {args_error} - storing by default"
            )
            return True

    def increment_usage_count(
        self, plugin_id: str, item_id: str, user_input: str = None
    ) -> bool:
        """
        Increment usage count for an existing history entry.

        Args:
            plugin_id: Plugin ID of the executed item
            item_id: Item ID of the executed item
            user_input: Optional user input to find specific entry

        Returns:
            True if count was incremented, False if entry not found
        """
        try:
            if not self._validate_increment_inputs(plugin_id, item_id, user_input):
                return False

            if not self._validate_history_structure():
                return False

            return self._find_and_increment_entry(plugin_id, item_id, user_input)

        except (TypeError, AttributeError, MemoryError) as e:
            logger.error(
                f"{type(e).__name__} incrementing usage count for {plugin_id}:{item_id}: {e}"
            )
            return False
        except Exception as e:
            logger.error(
                f"Critical error incrementing usage count for {plugin_id}:{item_id}: {e}"
            )
            logger.debug(
                f"Error context - plugin_id: {repr(plugin_id)}, item_id: {repr(item_id)}, user_input: {repr(user_input)}"
            )
            return False

    def _validate_increment_inputs(
        self, plugin_id: str, item_id: str, user_input: str = None
    ) -> bool:
        """Validate inputs for increment usage count"""
        if not plugin_id:
            logger.warning("Cannot increment usage count - plugin_id is empty or None")
            return False

        if not item_id:
            logger.warning("Cannot increment usage count - item_id is empty or None")
            return False

        if not isinstance(plugin_id, str):
            logger.warning(
                f"plugin_id is not a string ({type(plugin_id)}): {repr(plugin_id)}"
            )
            return False

        if not isinstance(item_id, str):
            logger.warning(
                f"item_id is not a string ({type(item_id)}): {repr(item_id)}"
            )
            return False

        if user_input is not None and not isinstance(user_input, str):
            logger.warning(
                f"user_input is not a string ({type(user_input)}): {repr(user_input)} - ignoring"
            )
            return False

        logger.debug(
            f"Searching for history entry to increment: {plugin_id}:{item_id}"
            + (f" with user_input='{user_input}'" if user_input else "")
        )
        return True

    def _validate_history_structure(self) -> bool:
        """Validate history data structure"""
        if not isinstance(self.user_input_history, list):
            logger.error(
                f"History data is corrupted - not a list ({type(self.user_input_history)})"
            )
            return False
        return True

    def _find_and_increment_entry(
        self, plugin_id: str, item_id: str, user_input: str = None
    ) -> bool:
        """Find and increment matching history entry"""
        entries_checked = 0
        entries_with_errors = 0

        for i, entry in enumerate(self.user_input_history):
            entries_checked += 1

            if not self._validate_entry_structure(entry, i):
                entries_with_errors += 1
                continue

            entry_data = self._extract_entry_data(entry, i)
            if not entry_data:
                entries_with_errors += 1
                continue

            if self._entry_matches(entry_data, plugin_id, item_id, user_input, i):
                success = self._increment_entry_count(entry, i, plugin_id, item_id)
                if success:
                    return True
                entries_with_errors += 1

        self._log_search_results(
            entries_checked, entries_with_errors, plugin_id, item_id, user_input
        )
        return False

    def _validate_entry_structure(self, entry: dict, index: int) -> bool:
        """Validate individual entry structure"""
        if not isinstance(entry, dict):
            logger.warning(
                f"History entry {index} is not a dict ({type(entry)}) - skipping"
            )
            return False
        return True

    def _extract_entry_data(self, entry: dict, index: int) -> dict:
        """Extract and validate entry data"""
        try:
            entry_plugin_id = entry.get("plugin_id")
            entry_item_id = entry.get("item_id")
            entry_user_input = entry.get("user_input", "")

            if not isinstance(entry_plugin_id, str) or not isinstance(
                entry_item_id, str
            ):
                logger.debug(
                    f"Entry {index} has invalid plugin_id/item_id types - skipping"
                )
                return None

            return {
                "plugin_id": entry_plugin_id,
                "item_id": entry_item_id,
                "user_input": entry_user_input,
            }
        except Exception as get_error:
            logger.warning(
                f"Error accessing entry {index} data: {get_error} - skipping"
            )
            return None

    def _entry_matches(
        self,
        entry_data: dict,
        plugin_id: str,
        item_id: str,
        user_input: str,
        index: int,
    ) -> bool:
        """Check if entry matches search criteria"""
        if entry_data["plugin_id"] != plugin_id or entry_data["item_id"] != item_id:
            return False

        if user_input:
            if not isinstance(entry_data["user_input"], str):
                logger.debug(
                    f"Entry {index} has invalid user_input type - skipping user_input match"
                )
                return False
            if entry_data["user_input"].lower() != user_input.lower():
                logger.debug(
                    f"Entry {index} user_input mismatch: '{entry_data['user_input']}' != '{user_input}'"
                )
                return False

        return True

    def _increment_entry_count(
        self, entry: dict, index: int, plugin_id: str, item_id: str
    ) -> bool:
        """Increment usage count for the entry"""
        try:
            current_count = entry.get("usage_count", 0)
            if not isinstance(current_count, (int, float)):
                logger.warning(
                    f"Entry {index} has invalid usage_count type ({type(current_count)}): {current_count} - resetting to 0"
                )
                current_count = 0

            new_count = int(current_count) + 1
            entry["usage_count"] = new_count
            entry["timestamp"] = time.time()

            logger.debug(
                f"Incremented usage count for {plugin_id}:{item_id} from {current_count} to {new_count}"
            )

            save_success = self.save_history()
            if not save_success:
                logger.warning(
                    f"Failed to save history after incrementing usage count for {plugin_id}:{item_id}"
                )

            return True
        except Exception as increment_error:
            logger.error(
                f"Error incrementing usage count for entry {index}: {increment_error}"
            )
            return False

    def _log_search_results(
        self,
        entries_checked: int,
        entries_with_errors: int,
        plugin_id: str,
        item_id: str,
        user_input: str = None,
    ):
        """Log search results"""
        logger.debug(
            f"Searched {entries_checked} history entries, {entries_with_errors} had errors"
        )
        logger.debug(
            f"No existing history entry found for {plugin_id}:{item_id}"
            + (f" with user_input='{user_input}'" if user_input else "")
        )

    def validate_and_clean_history(self, plugin_manager=None) -> int:
        """
        Validate all history entries and remove structurally invalid ones.
        This only performs basic validation - plugins should handle their own content validation.

        Args:
            plugin_manager: Optional plugin manager to validate against current plugins

        Returns:
            Number of entries removed
        """
        if not isinstance(self.user_input_history, list):
            logger.warning("History data is corrupted - resetting to empty list")
            original_count = (
                len(self.user_input_history)
                if hasattr(self.user_input_history, "__len__")
                else 0
            )
            self.user_input_history = []
            return original_count

        original_count = len(self.user_input_history)
        valid_entries = []
        removed_count = 0

        logger.info(
            f"Validating {original_count} history entries (basic structure only)..."
        )

        for entry in self.user_input_history:
            if self._is_valid_history_entry(entry, plugin_manager):
                valid_entries.append(entry)
            else:
                removed_count += 1
                logger.debug(
                    f"Removing structurally invalid history entry: {entry.get('user_input', 'unknown')}"
                )

        self.user_input_history = valid_entries

        if removed_count > 0:
            logger.info(f"Cleaned {removed_count} structurally invalid history entries")
            self.save_history()
        else:
            logger.info("All history entries are structurally valid")

        return removed_count

    def _is_valid_history_entry(
        self, entry: Dict[str, Any], plugin_manager=None
    ) -> bool:
        """
        Check if a history entry is valid (basic structure validation only).

        Args:
            entry: History entry to validate
            plugin_manager: Optional plugin manager to check if plugins still exist

        Returns:
            True if entry is valid, False otherwise
        """
        from launcher.plugins.base import Plugin
        return Plugin.is_structurally_valid(entry, plugin_manager)
