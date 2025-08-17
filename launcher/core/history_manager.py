#!/usr/bin/env python3

import os
import yaml
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
                with open(self.history_file, "r") as f:
                    data = yaml.safe_load(f)
                    self.user_input_history = data if data is not None else []

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
                yaml.dump(
                    self.user_input_history,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                )
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
        actual_command: str,
        original_user_input: str,
        result_name: str = None,
        description: str = None,
        icon_pixbuf=None,
    ) -> None:
        """
        Record a successful execution in history.

        Args:
            plugin_id: Plugin ID that was executed
            item_id: Item ID that was executed
            actual_command: The actual command that was executed (subprocess command)
            original_user_input: The exact text that the user typed before submitting
            result_name: The display name of the executed result (e.g., title-cased executable name)
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
            actual_command,
            result_name,
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
        actual_command_string: str = None,
        result_name: str = None,
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
            actual_command_string: The actual command string that was executed (subprocess command)
            result_name: The display name of the executed result (e.g., title-cased executable name)
            description: Description of the executed item
            icon_pixbuf: The actual icon pixbuf to store for better performance
        """
        if timestamp is None:
            timestamp = time.time()

        current_usage_count = self._process_existing_entries(
            user_input, plugin_id, actual_command_string
        )

        entry = self._create_history_entry(
            user_input,
            plugin_id,
            item_id,
            timestamp,
            actual_command_string,
            result_name,
            description,
            current_usage_count + 1,
            icon_pixbuf,
        )

        self._add_and_limit_history(entry)

    def _process_existing_entries(
        self, user_input: str, plugin_id: str, actual_command_string: str
    ) -> int:
        """Process existing entries for duplicates and merging"""
        current_usage_count = 0
        entries_to_remove = []

        normalized_new_command = None
        if plugin_id in ["executable", "desktop_file"] and actual_command_string:
            normalized_new_command = self._normalize_command_for_comparison(
                actual_command_string
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
                    f"Merging history entry for command '{actual_command_string}' with existing entry: {entry.get('user_input')}"
                )

        self._remove_entries(entries_to_remove)
        return current_usage_count

    def _is_exact_duplicate(self, entry: dict, user_input: str) -> bool:
        """Check if entry is an exact duplicate of user input"""
        return entry.get("user_input", "").lower() == user_input.lower()

    def _should_merge_commands(self, entry: dict, normalized_new_command: str) -> bool:
        """Check if entry should be merged based on normalized command"""
        if not normalized_new_command or not entry.get("actual_command"):
            return False

        normalized_existing_command = self._normalize_command_for_comparison(
            entry["actual_command"]
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
        actual_command_string: str,
        result_name: str,
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
            "result_name": result_name,
            "description": description,
            "usage_count": usage_count,
            "actual_command": actual_command_string,
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

    def get_result_for_history_entry(
        self,
        plugin_id: str,
        item_id: str,
        history_entry: Dict[str, Any] = None,
        plugin_manager=None,
        icon_size: int = 48,
    ):
        """Try to get the actual result object for a history entry to access current icon."""
        if not plugin_manager:
            return None

        # Check for stored icon first
        stored_result = self._get_stored_icon_result(
            history_entry, plugin_id, item_id, icon_size
        )
        if stored_result:
            return stored_result

        # Try to get result from plugin
        return self._get_plugin_result(plugin_id, item_id, plugin_manager, icon_size)

    def _get_stored_icon_result(self, history_entry, plugin_id, item_id, icon_size):
        """Get result with stored icon from history entry"""
        if not history_entry:
            return None

        stored_icon = self.get_stored_icon(history_entry, icon_size)
        if not stored_icon:
            return None

        return self._create_mock_result(
            stored_icon, history_entry.get("user_input", ""), plugin_id, item_id
        )

    def _get_plugin_result(self, plugin_id, item_id, plugin_manager, icon_size):
        """Delegate result fetching to the plugin itself."""
        plugin = plugin_manager.plugins.get(plugin_id)
        if not plugin:
            return None
        # Each plugin should implement get_result_for_history(item_id, icon_size)
        get_result = getattr(plugin, "get_result_for_history", None)
        if callable(get_result):
            try:
                return get_result(item_id, icon_size)
            except Exception as e:
                logger.debug(
                    f"Could not get item {item_id} from plugin {plugin_id}: {e}"
                )
        return None

    def _create_mock_result(self, icon, name, plugin_id, item_id):
        """Create a mock result object with the given properties"""

        class MockResult:
            def __init__(self, icon, name, plugin_id, item_id):
                self.icon = icon
                self.name = name
                self.plugin_id = plugin_id
                self.item_id = item_id

        return MockResult(icon, name, plugin_id, item_id)

    def get_fallback_history_icon(self, icon_size: int = 48):
        """Get fallback icon for history items"""
        from launcher.utils.icon_utils import load_theme_icon

        fallback_names = ["document-open-recent"]
        return load_theme_icon("accessories-history", icon_size, fallback_names)

    def execute_history_item(
        self, history_entry: Dict[str, Any], plugin_manager
    ) -> bool:
        """
        Execute an item from history by doing a targeted search and executing the first exact match.

        Args:
            history_entry: History entry containing plugin_id, item_id, user_input, etc.
            plugin_manager: Plugin manager to use for execution

        Returns:
            True if execution was successful, False otherwise
        """
        plugin_id = history_entry.get("plugin_id")
        item_id = history_entry.get("item_id")
        user_input = history_entry.get("user_input", "")

        if not plugin_id or not item_id or not plugin_manager:
            # Return False to indicate fallback to search is needed
            return False

        # Get the specific plugin and search for the exact item
        plugin = plugin_manager.plugins.get(plugin_id)
        if not plugin:
            # Plugin not available, fallback to search
            return False

        try:
            # Use the plugin's search method to find the item
            results = plugin.search(user_input)

            # Find the exact result by item_id
            target_result = None
            for result in results:
                if result.item_id == item_id:
                    target_result = result
                    break

            if target_result:
                # Found the exact item, execute it directly
                return plugin_manager.execute(target_result)
            else:
                # Item not found, fallback to regular search
                return False

        except Exception as e:
            logger.debug(f"Error executing history item: {e}")
            # Fallback to regular search
            return False

    def should_deduplicate_history_entry(
        self, history_name: str, current_name: str
    ) -> bool:
        """
        Determine if a history entry should be deduplicated based on similarity to current result.

        Args:
            history_name: Name from the history entry (user input)
            current_name: Name from the current search result

        Returns:
            True if the history entry should be removed (deduplicated), False to keep it
        """
        if not history_name or not current_name:
            return False

        history_lower = history_name.lower().strip()
        current_lower = current_name.lower().strip()

        # Don't deduplicate if they're exactly the same (shouldn't happen but be safe)
        if history_lower == current_lower:
            return True

        # Don't deduplicate if the history entry is significantly longer
        # This preserves entries like "brave gmail.com" when "brave" is found
        if len(history_lower) > len(current_lower) * 1.5:
            return False

        # Don't deduplicate if the history entry contains additional meaningful content
        # Check for URLs, file paths, or additional arguments
        if any(char in history_lower for char in [".", "/", ":", "=", "&", "?"]):
            return False

        # Don't deduplicate if the history entry has multiple words and current is single word
        history_words = history_lower.split()
        current_words = current_lower.split()

        if len(history_words) > 1 and len(current_words) == 1:
            return False

        # Only deduplicate if the history entry is very similar to current result
        # (essentially the same thing with minor variations)
        if (
            history_lower.startswith(current_lower)
            and len(history_lower) <= len(current_lower) + 3
        ):
            return True

        return False

    def deduplicate_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        Remove history results if exact matches exist from other plugins.
        Enhanced with comprehensive logging, error handling, and performance optimization.

        Args:
            results: List of search results to deduplicate

        Returns:
            List of deduplicated results
        """
        if not results:
            logger.debug("No results to deduplicate")
            return results

        try:
            # Performance optimization: use efficient data structures for large result sets
            start_time = None
            if logger.isEnabledFor(logging.DEBUG):
                import time

                start_time = time.time()
                logger.debug(f"Starting deduplication for {len(results)} results")

            # Group results by plugin type using list comprehensions for better performance
            history_results = []
            other_results = []

            for result in results:
                try:
                    # Enhanced validation of result structure
                    if not hasattr(result, "plugin_id"):
                        logger.warning(
                            f"Result missing plugin_id attribute: {getattr(result, 'name', 'unknown')}"
                        )
                        continue

                    if result.plugin_id == "history":
                        history_results.append(result)
                    else:
                        other_results.append(result)

                except Exception as e:
                    logger.error(f"Error categorizing result: {e}")
                    # Preserve result in other_results as fallback to avoid data loss
                    other_results.append(result)
                    continue

            logger.debug(
                f"Found {len(history_results)} history results and {len(other_results)} other results"
            )

            if not history_results or not other_results:
                logger.debug(
                    "No deduplication needed - missing history or other results"
                )
                return results  # No deduplication needed

            # Performance optimization: create efficient lookup structures
            # Use dict for O(1) lookups with enhanced error handling
            other_result_keys = {}  # (plugin_id, item_id) -> result for debugging
            invalid_results_count = 0

            for result in other_results:
                try:
                    # Enhanced validation that result has required attributes
                    if not hasattr(result, "plugin_id") or not hasattr(
                        result, "item_id"
                    ):
                        logger.warning(
                            f"Result missing required attributes (plugin_id/item_id): {getattr(result, 'name', 'unknown')}"
                        )
                        invalid_results_count += 1
                        continue

                    # Validate that plugin_id and item_id are not None or empty
                    if not result.plugin_id or not result.item_id:
                        logger.debug(
                            f"Result has empty plugin_id or item_id: {getattr(result, 'name', 'unknown')}"
                        )
                        invalid_results_count += 1
                        continue

                    key = (result.plugin_id, result.item_id)
                    other_result_keys[key] = result

                except AttributeError as e:
                    logger.warning(
                        f"AttributeError processing result {getattr(result, 'name', 'unknown')}: {e}"
                    )
                    invalid_results_count += 1
                    continue
                except Exception as e:
                    logger.error(
                        f"Unexpected error processing result {getattr(result, 'name', 'unknown')}: {e}"
                    )
                    invalid_results_count += 1
                    continue

            logger.debug(
                f"Created lookup table with {len(other_result_keys)} entries ({invalid_results_count} invalid results skipped)"
            )

            # Filter out history results that have exact matches in other plugins
            filtered_history_results = []
            deduplicated_count = 0
            preserved_count = 0
            missing_metadata_count = 0
            error_count = 0

            for history_result in history_results:
                try:
                    # Enhanced validation of history result structure
                    if not hasattr(history_result, "metadata"):
                        logger.warning(
                            f"History result missing metadata attribute: {getattr(history_result, 'name', 'unknown')}"
                        )
                        filtered_history_results.append(history_result)
                        preserved_count += 1
                        missing_metadata_count += 1
                        continue

                    if not isinstance(history_result.metadata, dict):
                        logger.warning(
                            f"History result has invalid metadata type ({type(history_result.metadata)}): {getattr(history_result, 'name', 'unknown')}"
                        )
                        filtered_history_results.append(history_result)
                        preserved_count += 1
                        missing_metadata_count += 1
                        continue

                    # Get original plugin info from history metadata with enhanced validation
                    try:
                        original_plugin_id = history_result.metadata.get(
                            "original_plugin_id"
                        )
                        original_item_id = history_result.metadata.get(
                            "original_item_id"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Error accessing metadata for history result '{getattr(history_result, 'name', 'unknown')}': {e}"
                        )
                        filtered_history_results.append(history_result)
                        preserved_count += 1
                        missing_metadata_count += 1
                        continue

                    # Validate metadata exists and is not empty with type checking
                    if not original_plugin_id or not original_item_id:
                        logger.debug(
                            f"History result '{getattr(history_result, 'name', 'unknown')}' missing original plugin metadata - preserving"
                        )
                        filtered_history_results.append(history_result)
                        preserved_count += 1
                        missing_metadata_count += 1
                        continue

                    # Ensure metadata values are strings
                    if not isinstance(original_plugin_id, str) or not isinstance(
                        original_item_id, str
                    ):
                        logger.warning(
                            f"History result '{getattr(history_result, 'name', 'unknown')}' has non-string metadata values - preserving"
                        )
                        filtered_history_results.append(history_result)
                        preserved_count += 1
                        missing_metadata_count += 1
                        continue

                    # Check if this history item has an exact match in current results
                    match_key = (original_plugin_id, original_item_id)
                    matching_result = other_result_keys.get(match_key)

                    if matching_result is None:
                        # No exact match found, keep this history result
                        filtered_history_results.append(history_result)
                        preserved_count += 1
                        logger.debug(
                            f"Preserving history result '{getattr(history_result, 'name', 'unknown')}' - no current match for {original_plugin_id}:{original_item_id}"
                        )
                    else:
                        # Found a matching result, but only deduplicate if the history entry
                        # represents the same user intent (similar input)
                        history_name = getattr(history_result, "name", "")
                        current_name = getattr(matching_result, "name", "")

                        # Only deduplicate if the history entry name is very similar to the current result
                        # This prevents removing "brave gmail.com" when "brave" app is found
                        if self.should_deduplicate_history_entry(
                            history_name, current_name
                        ):
                            deduplicated_count += 1
                            logger.debug(
                                f"Deduplicating history result '{history_name}' - too similar to current result '{current_name}' ({original_plugin_id}:{original_item_id})"
                            )
                        else:
                            filtered_history_results.append(history_result)
                            preserved_count += 1
                            logger.debug(
                                f"Preserving history result '{history_name}' - different intent from current result '{current_name}' ({original_plugin_id}:{original_item_id})"
                            )

                except AttributeError as e:
                    # Graceful error handling for missing attributes
                    logger.warning(f"AttributeError processing history result: {e}")
                    filtered_history_results.append(history_result)
                    preserved_count += 1
                    error_count += 1
                    continue
                except KeyError as e:
                    # Graceful error handling for missing dictionary keys
                    logger.warning(f"KeyError processing history result metadata: {e}")
                    filtered_history_results.append(history_result)
                    preserved_count += 1
                    error_count += 1
                    continue
                except Exception as e:
                    # Graceful error handling - preserve result if processing fails
                    logger.error(
                        f"Unexpected error processing history result '{getattr(history_result, 'name', 'unknown')}': {e}"
                    )
                    filtered_history_results.append(history_result)
                    preserved_count += 1
                    error_count += 1
                    continue

            # Return deduplicated list
            # Maintain original order: other results first, then filtered history results
            deduplicated_results = other_results + filtered_history_results
            original_count = len(results)
            final_count = len(deduplicated_results)

            # Comprehensive logging summary with error reporting
            logger.debug(
                f"Deduplication complete: {original_count} -> {final_count} results"
            )
            logger.debug(f"  - Deduplicated: {deduplicated_count} history results")
            logger.debug(f"  - Preserved: {preserved_count} history results")
            logger.debug(
                f"  - Missing metadata: {missing_metadata_count} history results"
            )

            if error_count > 0:
                logger.warning(
                    f"  - Errors encountered: {error_count} results had processing errors"
                )

            if invalid_results_count > 0:
                logger.warning(
                    f"  - Invalid results: {invalid_results_count} results skipped due to missing attributes"
                )

            if start_time and logger.isEnabledFor(logging.DEBUG):
                elapsed_time = time.time() - start_time
                logger.debug(f"Deduplication took {elapsed_time:.3f}s")

                # Performance warning for slow deduplication
                if elapsed_time > 0.1:  # More than 100ms
                    logger.warning(
                        f"Deduplication took longer than expected: {elapsed_time:.3f}s for {original_count} results"
                    )

            return deduplicated_results

        except MemoryError as e:
            # Handle memory errors specifically
            logger.error(
                f"Memory error during deduplication with {len(results)} results: {e}"
            )
            logger.warning("Skipping deduplication due to memory constraints")
            return results
        except Exception as e:
            # Graceful error handling - log error but don't break search functionality
            logger.error(f"Critical error during deduplication: {e}")
            logger.debug("Continuing with original results due to deduplication error")
            return results
