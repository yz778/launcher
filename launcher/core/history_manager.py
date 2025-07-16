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
                logger.warning(f"History data is corrupted in get_usage_count - not a list ({type(self.user_input_history)})")
                return 0

            # Find the most recent entry for this plugin_id/item_id
            for entry in self.user_input_history:
                try:
                    if not isinstance(entry, dict):
                        continue

                    if entry.get("plugin_id") == plugin_id and entry.get("item_id") == item_id:
                        usage_count = entry.get("usage_count", 1)
                        return usage_count if isinstance(usage_count, (int, float)) else 1
                except Exception as e:
                    logger.debug(f"Error processing history entry in get_usage_count: {e}")
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

        current_usage_count = 0
        entries_to_remove = []

        # Normalize the executed command for the new entry, if applicable
        normalized_new_command = None
        if plugin_id in ["executable", "desktop_file"] and executed_command_string:
            normalized_new_command = self._normalize_command_for_comparison(
                executed_command_string
            )

        # Iterate through existing history to find duplicates and merge counts
        for entry in self.user_input_history:
            # Check for exact user input duplicate (case-insensitive)
            if entry.get("user_input", "").lower() == user_input.lower():
                # This is the exact same user input, so we'll replace it.
                # Take its usage count as the base for the new entry.
                current_usage_count = entry.get("usage_count", 0)
                entries_to_remove.append(entry)
                continue  # Don't process this entry further for merging, it's being replaced

            # Check for merging based on normalized executed command
            if normalized_new_command and entry.get("executed_command"):
                normalized_existing_command = self._normalize_command_for_comparison(
                    entry["executed_command"]
                )
                if normalized_new_command == normalized_existing_command:
                    current_usage_count += entry.get("usage_count", 0)
                    entries_to_remove.append(entry)
                    logger.debug(
                        f"Merging history entry for command '{executed_command_string}' with existing entry: {entry.get('user_input')}"
                    )

        # Filter out entries that are being replaced or merged
        self.user_input_history = [
            entry for entry in self.user_input_history if entry not in entries_to_remove
        ]

        # Add new entry at the beginning (most recent first)
        entry = {
            "user_input": user_input,
            "plugin_id": plugin_id,
            "item_id": item_id,
            "timestamp": timestamp,
            "description": description,
            "usage_count": current_usage_count + 1,
            "executed_command": executed_command_string,  # Store the actual executed command
        }

        # Store the actual icon data if provided for any plugin type
        if icon_pixbuf:
            try:
                # Convert pixbuf to PNG data and then base64 encode
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
        executed_result: SearchResult
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
            # Enhanced input validation with detailed logging
            if not user_input:
                if user_input is None:
                    logger.debug("User input is None - storing by default")
                elif user_input == "":
                    logger.debug("User input is empty string - storing by default")
                else:
                    logger.debug(f"User input is falsy ({type(user_input)}): {repr(user_input)} - storing by default")
                return True

            if not executed_result:
                if executed_result is None:
                    logger.debug("Executed result is None - storing by default")
                else:
                    logger.debug(f"Executed result is falsy ({type(executed_result)}) - storing by default")
                return True

            # Validate executed_result has required attributes
            try:
                result_name = getattr(executed_result, 'name', None)
                if result_name is None:
                    logger.warning("Executed result missing 'name' attribute - storing by default")
                    return True
            except Exception as attr_error:
                logger.warning(f"Error accessing executed result attributes: {attr_error} - storing by default")
                return True

            # Enhanced logging for analysis input
            logger.debug(f"Analyzing storage decision for user_input='{user_input}' -> result='{result_name}'")

            # Validate search_results parameter
            if search_results is None:
                logger.debug("Search results is None - continuing with analysis")
                search_results = []
            elif not isinstance(search_results, list):
                logger.warning(f"Search results is not a list ({type(search_results)}) - converting to empty list")
                search_results = []

            # Get match quality using ResultAnalyzer with enhanced error handling
            try:
                match_quality = ResultAnalyzer.get_match_quality(user_input, executed_result)
                logger.debug(f"Match quality analysis result: '{match_quality}'")
            except AttributeError as e:
                logger.warning(f"AttributeError in match quality analysis: {e} - storing by default")
                return True
            except TypeError as e:
                logger.warning(f"TypeError in match quality analysis: {e} - storing by default")
                return True
            except Exception as e:
                logger.error(f"Unexpected error in match quality analysis: {e} - storing by default")
                return True

            # Process match quality with enhanced validation
            if not isinstance(match_quality, str):
                logger.warning(f"Match quality is not a string ({type(match_quality)}): {match_quality} - storing by default")
                return True

            match_quality = match_quality.lower().strip()

            # Always store exact matches
            if match_quality == "exact":
                logger.debug("Storing exact match in history")
                return True

            # For partial matches, only store if command arguments are present
            elif match_quality == "partial":
                try:
                    has_args = ResultAnalyzer.has_command_arguments(user_input, executed_result)
                    logger.debug(f"Partial match - command arguments detected: {has_args}")

                    if has_args:
                        logger.debug("Storing partial match with command arguments in history")
                        return True
                    else:
                        logger.debug("Skipping storage of partial match without command arguments")
                        return False

                except Exception as args_error:
                    logger.warning(f"Error checking command arguments: {args_error} - storing by default")
                    return True

            # For fuzzy matches, store them (they represent meaningful user selections)
            elif match_quality == "fuzzy":
                logger.debug("Storing fuzzy match in history")
                return True

            # For no match, don't store unless it's a conservative fallback
            elif match_quality == "none":
                logger.debug("No match detected - storing by default (conservative approach)")
                return True

            # For unknown quality, store by default (conservative approach)
            else:
                logger.debug(f"Unknown match quality '{match_quality}' - storing by default")
                return True

        except ImportError as e:
            # Handle missing ResultAnalyzer module
            logger.error(f"ImportError - ResultAnalyzer not available: {e} - storing by default")
            return True
        except MemoryError as e:
            # Handle memory errors during analysis
            logger.error(f"MemoryError during storage analysis: {e} - storing by default")
            return True
        except RecursionError as e:
            # Handle recursion errors
            logger.error(f"RecursionError during storage analysis: {e} - storing by default")
            return True
        except Exception as e:
            # Fallback to default storage behavior on any other analysis failures
            logger.error(f"Critical error analyzing match quality for history storage: {e}")
            logger.debug(f"Error details - user_input: {repr(user_input)}, executed_result: {repr(executed_result)}")
            logger.debug("Falling back to default storage behavior due to analysis error")
            return True

    def increment_usage_count(
        self,
        plugin_id: str,
        item_id: str,
        user_input: str = None
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
            # Enhanced input validation
            if not plugin_id:
                logger.warning("Cannot increment usage count - plugin_id is empty or None")
                return False

            if not item_id:
                logger.warning("Cannot increment usage count - item_id is empty or None")
                return False

            # Validate plugin_id and item_id are strings
            if not isinstance(plugin_id, str):
                logger.warning(f"plugin_id is not a string ({type(plugin_id)}): {repr(plugin_id)}")
                return False

            if not isinstance(item_id, str):
                logger.warning(f"item_id is not a string ({type(item_id)}): {repr(item_id)}")
                return False

            # Validate user_input if provided
            if user_input is not None and not isinstance(user_input, str):
                logger.warning(f"user_input is not a string ({type(user_input)}): {repr(user_input)} - ignoring")
                user_input = None

            logger.debug(f"Searching for history entry to increment: {plugin_id}:{item_id}" +
                        (f" with user_input='{user_input}'" if user_input else ""))

            # Validate history data structure
            if not isinstance(self.user_input_history, list):
                logger.error(f"History data is corrupted - not a list ({type(self.user_input_history)})")
                return False

            entries_checked = 0
            entries_with_errors = 0

            # Find matching history entry with enhanced error handling
            for i, entry in enumerate(self.user_input_history):
                try:
                    entries_checked += 1

                    # Validate entry structure
                    if not isinstance(entry, dict):
                        logger.warning(f"History entry {i} is not a dict ({type(entry)}) - skipping")
                        entries_with_errors += 1
                        continue

                    # Safely get entry values with type validation
                    try:
                        entry_plugin_id = entry.get("plugin_id")
                        entry_item_id = entry.get("item_id")
                        entry_user_input = entry.get("user_input", "")
                    except Exception as get_error:
                        logger.warning(f"Error accessing entry {i} data: {get_error} - skipping")
                        entries_with_errors += 1
                        continue

                    # Validate entry data types
                    if not isinstance(entry_plugin_id, str) or not isinstance(entry_item_id, str):
                        logger.debug(f"Entry {i} has invalid plugin_id/item_id types - skipping")
                        entries_with_errors += 1
                        continue

                    # Match by plugin_id and item_id
                    if entry_plugin_id == plugin_id and entry_item_id == item_id:
                        # If user_input is specified, also match on that
                        if user_input:
                            if not isinstance(entry_user_input, str):
                                logger.debug(f"Entry {i} has invalid user_input type - skipping user_input match")
                                continue
                            if entry_user_input.lower() != user_input.lower():
                                logger.debug(f"Entry {i} user_input mismatch: '{entry_user_input}' != '{user_input}'")
                                continue

                        # Validate and increment usage count
                        try:
                            current_count = entry.get("usage_count", 0)
                            if not isinstance(current_count, (int, float)):
                                logger.warning(f"Entry {i} has invalid usage_count type ({type(current_count)}): {current_count} - resetting to 0")
                                current_count = 0

                            new_count = int(current_count) + 1
                            entry["usage_count"] = new_count

                            # Update timestamp to reflect recent usage
                            entry["timestamp"] = time.time()

                            logger.debug(f"Incremented usage count for {plugin_id}:{item_id} from {current_count} to {new_count}")

                            # Save the updated history with error handling
                            save_success = self.save_history()
                            if not save_success:
                                logger.warning(f"Failed to save history after incrementing usage count for {plugin_id}:{item_id}")
                                # Still return True since the increment succeeded in memory

                            return True

                        except Exception as increment_error:
                            logger.error(f"Error incrementing usage count for entry {i}: {increment_error}")
                            entries_with_errors += 1
                            continue

                except KeyError as e:
                    logger.warning(f"KeyError processing entry {i}: {e} - skipping")
                    entries_with_errors += 1
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error processing entry {i}: {e} - skipping")
                    entries_with_errors += 1
                    continue

            # Log search results
            logger.debug(f"Searched {entries_checked} history entries, {entries_with_errors} had errors")
            logger.debug(f"No existing history entry found for {plugin_id}:{item_id}" +
                        (f" with user_input='{user_input}'" if user_input else ""))
            return False

        except TypeError as e:
            logger.error(f"TypeError incrementing usage count for {plugin_id}:{item_id}: {e}")
            return False
        except AttributeError as e:
            logger.error(f"AttributeError incrementing usage count for {plugin_id}:{item_id}: {e}")
            return False
        except MemoryError as e:
            logger.error(f"MemoryError incrementing usage count for {plugin_id}:{item_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Critical error incrementing usage count for {plugin_id}:{item_id}: {e}")
            logger.debug(f"Error context - plugin_id: {repr(plugin_id)}, item_id: {repr(item_id)}, user_input: {repr(user_input)}")
            return False
