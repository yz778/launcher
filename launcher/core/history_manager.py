#!/usr/bin/env python3


from launcher.plugins.base import Plugin, SearchResult
from launcher.utils.icon_utils import load_theme_icon
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
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.user_input_history = data if isinstance(data, list) else []

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
            # Write to a temporary file first
            fd, temp_path = tempfile.mkstemp(
                dir=os.path.dirname(self.history_file), suffix=".tmp"
            )

            def _json_default(obj):
                if hasattr(obj, "to_dict") and callable(obj.to_dict):
                    return obj.to_dict()
                return ""

            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(
                    self.user_input_history,
                    f,
                    ensure_ascii=False,
                    indent=2,
                    default=_json_default,
                )

            # Atomically rename the temporary file to the history file
            os.replace(temp_path, self.history_file)
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
                        return usage_count if isinstance(usage_count, (int)) else 1
                except Exception:
                    continue

            return 0

        except Exception as e:
            logger.error(f"Error getting usage count for {plugin_id}:{item_id}: {e}")
            return 0

    def add_execution(self, result: SearchResult, user_input: str) -> None:
        """
        Record a successful execution in history.

        Args:
            result: The SearchResult object that was executed.
            user_input: The exact text that the user typed.
        """
        if not result or not user_input:
            return

        current_time = time.time()

        # Extract all necessary information from the result object
        plugin_id = result.plugin_id
        item_id = result.item_id
        result_name = result.name
        description = result.description
        icon_spec = result.icon_spec
        actual_command = result.metadata.get("actual_executed_command", user_input)
        processed_metadata = result.metadata.copy()

        self.add_user_input_history(
            user_input,
            plugin_id,
            item_id,
            current_time,
            actual_command,
            result_name,
            description,
            icon_spec,
            processed_metadata,  # Pass the processed metadata
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
        timestamp: Optional[float] = None,
        actual_command_string: Optional[str] = None,
        result_name: Optional[str] = None,
        description: Optional[str] = None,
        icon_spec: Optional[str] = None,
        original_metadata: Optional[Dict[str, Any]] = None,  # New parameter
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
            icon_spec: The icon specification to store for the item
            original_metadata: The original metadata from the SearchResult
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
            icon_spec,
            original_metadata,  # Pass the new parameter
        )

        self._add_and_limit_history(entry)

    def _process_existing_entries(
        self, user_input: str, plugin_id: str, actual_command_string: Optional[str]
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

        self._remove_entries(entries_to_remove)
        return current_usage_count

    def _is_exact_duplicate(self, entry: dict, user_input: str) -> bool:
        """Check if entry is an exact duplicate of user input"""
        return entry.get("user_input", "").lower() == user_input.lower()

    def _should_merge_commands(
        self, entry: dict, normalized_new_command: Optional[str]
    ) -> bool:
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
        actual_command_string: Optional[str],
        result_name: Optional[str],
        description: Optional[str],
        usage_count: int,
        icon_spec: Optional[str],
        original_metadata: Optional[Dict[str, Any]] = None,  # New parameter
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
            "original_metadata": original_metadata
            if original_metadata is not None
            else {},  # Store original metadata
        }

        if icon_spec:
            entry["icon_spec"] = icon_spec

        return entry

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

        self.user_input_history = new_history
        removed_count = original_length - len(self.user_input_history)

        if removed_count > 0:
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

    def should_store_in_history(
        self,
        user_input: str,
        executed_result: SearchResult,
    ) -> bool:
        """
        Determine if execution should be stored in history.
        Always stores a successful execution unless it's an exact duplicate of the immediately preceding entry.

        Args:
            user_input: Original user query
            executed_result: The result that was actually executed

        Returns:
            True if should store, False otherwise
        """
        if not user_input or not executed_result:
            return False

        # Check if the last entry is an exact duplicate of the current execution
        if self.user_input_history:
            last_entry = self.user_input_history[0]
            if (
                last_entry.get("user_input", "").lower() == user_input.lower()
                and last_entry.get("plugin_id") == executed_result.plugin_id
                and last_entry.get("item_id") == executed_result.item_id
            ):
                return False

        return True

    def increment_usage_count(
        self, plugin_id: str, item_id: str, user_input: Optional[str] = None
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
            return False

    def _validate_increment_inputs(
        self, plugin_id: str, item_id: str, user_input: Optional[str] = None
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
        self, plugin_id: str, item_id: str, user_input: Optional[str] = None
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

        return False

    def _validate_entry_structure(self, entry: dict, index: int) -> bool:
        """Validate individual entry structure"""
        if not isinstance(entry, dict):
            logger.warning(
                f"History entry {index} is not a dict ({type(entry)}) - skipping"
            )
            return False
        return True

    def _extract_entry_data(self, entry: dict, index: int) -> Optional[dict]:
        """Extract and validate entry data"""
        try:
            entry_plugin_id = entry.get("plugin_id")
            entry_item_id = entry.get("item_id")
            entry_user_input = entry.get("user_input", "")

            if not isinstance(entry_plugin_id, str) or not isinstance(
                entry_item_id, str
            ):
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
        user_input: Optional[str],
        index: int,
    ) -> bool:
        """Check if entry matches search criteria"""
        if entry_data["plugin_id"] != plugin_id or entry_data["item_id"] != item_id:
            return False

        if user_input:
            if not isinstance(entry_data["user_input"], str):
                return False
            if entry_data["user_input"].lower() != user_input.lower():
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
            return True

        except Exception as increment_error:
            logger.error(
                f"Error incrementing usage count for entry {index}: {increment_error}"
            )
            return False

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

        self.user_input_history = valid_entries

        if removed_count > 0:
            logger.info(f"Cleaned {removed_count} structurally invalid history entries")
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

        return Plugin.is_structurally_valid(entry, plugin_manager)

    def get_result_for_history_entry(
        self,
        plugin_id: str,
        item_id: str,
        history_entry: Optional[Dict[str, Any]] = None,
        plugin_manager=None,
        icon_size: int = 48,
    ) -> Optional[Any]:
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
        """Get result with stored icon spec from history entry"""
        if not history_entry:
            return None

        stored_icon_spec = history_entry.get("icon_spec")
        if not stored_icon_spec:
            return None

        return self._create_mock_result(
            stored_icon_spec,
            history_entry.get("user_input", ""),
            plugin_id,
            item_id,
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
            except Exception:
                pass

        return None

    def _create_mock_result(self, icon_spec, name, plugin_id, item_id):
        """Create a mock result object with the given properties"""

        class MockResult:
            def __init__(self, icon_spec, name, plugin_id, item_id):
                self.icon_spec = icon_spec
                self.name = name
                self.plugin_id = plugin_id
                self.item_id = item_id

        return MockResult(icon_spec, name, plugin_id, item_id)

    def get_fallback_history_icon(self, icon_size: int = 48):
        """Get fallback icon for history items"""
        fallback_names = ["document-open-recent"]
        return load_theme_icon("accessories-history", icon_size, fallback_names)

    def cleanup(self) -> None:
        """
        Clean up resources, ensuring history is saved on exit.
        """
        self.save_history()
        logger.info("HistoryManager cleaned up and history saved.")
