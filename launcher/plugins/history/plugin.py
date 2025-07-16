#!/usr/bin/env python3

import logging
import math
import time
from typing import List, Dict, Any

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from ..base import Plugin, SearchResult

logger = logging.getLogger(__name__)


class HistoryPlugin(Plugin):
    """Plugin for searching through command history"""

    def __init__(self):
        super().__init__()
        self.history_manager = None
        self.icon_size = 48

    def get_id(self) -> str:
        return "history"

    def get_name(self) -> str:
        return "History Search"

    def get_description(self) -> str:
        return "Search through command execution history"

    def get_config_defaults(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "max_results": 10,
            "min_query_length": 2,
            "boost_recent": True,
            "boost_frequent": True,
        }

    def initialize(self, config: Dict[str, Any], config_manager=None) -> bool:
        """Initialize the history plugin"""
        try:
            self.config = config
            self.icon_size = config.get("icon_size", 48)

            # History manager will be set later via set_managers method
            # For now, just mark as successfully initialized
            logger.info("History plugin initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize history plugin: {e}")
            return False

    def set_managers(self, history_manager, plugin_manager):
        """Set the history and plugin managers after initialization"""
        self.history_manager = history_manager
        self.plugin_manager = plugin_manager
        logger.info("History plugin managers set successfully")

    def search(self, query: str) -> List[SearchResult]:
        """Search through command history"""
        if not self.history_manager:
            return []

        query = query.strip()
        min_length = self.config.get("min_query_length", 2)

        if len(query) < min_length:
            return []

        max_results = self.config.get("max_results", 10)
        results = []

        try:
            # Get all history entries with validation
            all_history = self.history_manager.user_input_history

            if not isinstance(all_history, list):
                logger.warning(f"History data is not a list ({type(all_history)}) - returning empty results")
                return []

            # Search through history entries
            for entry in all_history:
                try:
                    # Validate entry structure
                    if not isinstance(entry, dict):
                        logger.debug(f"History entry is not a dict ({type(entry)}) - skipping")
                        continue

                    user_input = entry.get("user_input", "")
                    executed_command = entry.get("executed_command", "")
                    description = entry.get("description", "")

                    # Validate user_input is a string
                    if not isinstance(user_input, str):
                        logger.debug(f"user_input is not a string ({type(user_input)}) - skipping entry")
                        continue

                except Exception as entry_error:
                    logger.debug(f"Error processing history entry: {entry_error} - skipping")
                    continue

                # Calculate best match score from all fields
                best_score = max(
                    self._calculate_match_score(query, user_input),
                    self._calculate_match_score(query, executed_command)
                    if executed_command != user_input
                    else 0,
                    self._calculate_match_score(query, description) * 0.5
                    if description
                    else 0,
                )

                if best_score > 0:
                    # Apply boosts and create result
                    final_score = self._apply_boosts(entry, best_score)
                    result = self._create_history_result(entry, final_score, query)
                    if result:
                        results.append(result)

            # Sort by score (highest first) and limit results
            results.sort(key=lambda r: r.score, reverse=True)
            return results[:max_results]

        except Exception as e:
            logger.error(f"Error searching history: {e}")
            return []

    def _calculate_match_score(self, query: str, text: str) -> float:
        """Calculate match score between query and text"""
        if not text:
            return 0.0

        query_lower = query.lower()
        text_lower = text.lower()

        # History plugin gets priority scores above all other plugins
        # Base scores are set higher than string matcher's HISTORY_BASE (300.0)

        # Exact match gets highest score
        if query_lower == text_lower:
            return 500.0

        # Prefix match gets high score
        if text_lower.startswith(query_lower):
            return 400.0 + (len(query_lower) / len(text_lower)) * 50

        # Substring match gets medium score
        if query_lower in text_lower:
            return 350.0 + (len(query_lower) / len(text_lower)) * 30

        # Fuzzy match for individual characters
        return self._fuzzy_match_score(query_lower, text_lower)

    def _fuzzy_match_score(self, query: str, text: str) -> float:
        """Calculate fuzzy match score"""
        if not query or not text:
            return 0.0

        query_idx = 0
        text_idx = 0
        matches = 0

        while query_idx < len(query) and text_idx < len(text):
            if query[query_idx] == text[text_idx]:
                matches += 1
                query_idx += 1
            text_idx += 1

        if matches == len(query):
            # All query characters found in order - prioritize over other plugins
            return 320.0 + (matches / len(text)) * 30
        else:
            return 0.0

    def _apply_boosts(self, entry: Dict[str, Any], base_score: float) -> float:
        """Apply boosts based on recency and frequency"""
        score = base_score

        # Boost for frequency (usage count) - increased for history priority
        if self.config.get("boost_frequent", True):
            usage_count = entry.get("usage_count", 1)
            if usage_count > 1:
                frequency_boost = min(50, 10 * math.log2(usage_count))
                score += frequency_boost

        # Boost for recency - increased for history priority
        if self.config.get("boost_recent", True):
            timestamp = entry.get("timestamp", 0)
            current_time = time.time()
            age_hours = (current_time - timestamp) / 3600

            # Boost recent items (within last 24 hours)
            if age_hours < 24:
                recency_boost = max(0, 25 * (1 - age_hours / 24))
                score += recency_boost

        return score

    def _validate_original_plugin_id(self, entry: Dict[str, Any]) -> str:
        """Validate and return original plugin ID with fallback behavior"""
        try:
            plugin_id = entry.get("plugin_id", "")

            # Return empty string if None or not a string
            if not isinstance(plugin_id, str):
                logger.debug(f"Invalid plugin_id type in history entry: {type(plugin_id)}")
                return ""

            # Return the plugin_id (could be empty string, which is valid for fallback)
            return plugin_id.strip()

        except Exception as e:
            logger.debug(f"Error validating original plugin ID: {e}")
            return ""

    def _validate_original_item_id(self, entry: Dict[str, Any]) -> str:
        """Validate and return original item ID with fallback behavior"""
        try:
            item_id = entry.get("item_id", "")

            # Return empty string if None or not a string
            if not isinstance(item_id, str):
                logger.debug(f"Invalid item_id type in history entry: {type(item_id)}")
                return ""

            # Return the item_id (could be empty string, which is valid for fallback)
            return item_id.strip()

        except Exception as e:
            logger.debug(f"Error validating original item ID: {e}")
            return ""

    def _create_history_result(
        self, entry: Dict[str, Any], score: float, query: str
    ) -> SearchResult:
        """Create a SearchResult from a history entry with enhanced metadata handling"""
        try:
            # Enhanced input validation
            if not isinstance(entry, dict):
                logger.error(f"History entry is not a dict ({type(entry)}): {repr(entry)}")
                return None

            if not isinstance(score, (int, float)):
                logger.warning(f"Score is not numeric ({type(score)}): {repr(score)} - using 0.0")
                score = 0.0

            if not isinstance(query, str):
                logger.warning(f"Query is not a string ({type(query)}): {repr(query)} - using empty string")
                query = ""

            # Safely extract entry data with validation
            try:
                user_input = entry.get("user_input", "")
                if not isinstance(user_input, str):
                    logger.warning(f"user_input is not a string ({type(user_input)}): {repr(user_input)} - using empty string")
                    user_input = ""
            except Exception as e:
                logger.warning(f"Error getting user_input from entry: {e} - using empty string")
                user_input = ""

            try:
                executed_command = entry.get("executed_command", user_input)
                if not isinstance(executed_command, str):
                    logger.warning(f"executed_command is not a string ({type(executed_command)}): {repr(executed_command)} - using user_input")
                    executed_command = user_input
            except Exception as e:
                logger.warning(f"Error getting executed_command from entry: {e} - using user_input")
                executed_command = user_input

            try:
                description = entry.get("description", "")
                if description is not None and not isinstance(description, str):
                    logger.warning(f"description is not a string ({type(description)}): {repr(description)} - using empty string")
                    description = ""
                elif description is None:
                    description = ""
            except Exception as e:
                logger.warning(f"Error getting description from entry: {e} - using empty string")
                description = ""

            try:
                usage_count = entry.get("usage_count", 1)
                if not isinstance(usage_count, (int, float)):
                    logger.warning(f"usage_count is not numeric ({type(usage_count)}): {repr(usage_count)} - using 1")
                    usage_count = 1
                else:
                    usage_count = int(usage_count)
            except Exception as e:
                logger.warning(f"Error getting usage_count from entry: {e} - using 1")
                usage_count = 1

            # Enhanced metadata validation and handling
            try:
                original_plugin_id = self._validate_original_plugin_id(entry)
                original_item_id = self._validate_original_item_id(entry)
            except Exception as metadata_error:
                logger.warning(f"Error validating original plugin metadata: {metadata_error} - using empty strings")
                original_plugin_id = ""
                original_item_id = ""

            # Log metadata validation results for debugging
            if not original_plugin_id or not original_item_id:
                logger.debug(
                    f"History entry missing original plugin metadata - "
                    f"plugin_id: '{original_plugin_id}', item_id: '{original_item_id}', "
                    f"user_input: '{user_input}'"
                )

            # Try to get the original icon if available with error handling
            try:
                icon = self._get_history_icon(entry)
            except Exception as icon_error:
                logger.warning(f"Error getting history icon: {icon_error} - using None")
                icon = None

            # Create display name and description with validation
            try:
                display_name = user_input if user_input else "Unknown Command"
            except Exception as e:
                logger.warning(f"Error creating display name: {e} - using fallback")
                display_name = "Unknown Command"

            # Build description without usage count (usage count will be shown separately)
            try:
                display_description = ""
                if executed_command and executed_command != user_input:
                    display_description = executed_command

                if (description and
                    description != executed_command and
                    description != user_input):
                    if display_description:
                        display_description += f" - {description}"
                    else:
                        display_description = description
            except Exception as desc_error:
                logger.warning(f"Error building display description: {desc_error} - using empty string")
                display_description = ""

            # Create enhanced metadata with proper validation and error handling
            try:
                metadata = {
                    "original_plugin_id": original_plugin_id,
                    "original_item_id": original_item_id,
                    "history_entry": entry,
                    "usage_count": usage_count,
                    "track_history": False,  # Don't track history searches in history
                    "has_original_metadata": bool(original_plugin_id and original_item_id),
                }
            except Exception as metadata_create_error:
                logger.error(f"Error creating metadata dict: {metadata_create_error} - using minimal metadata")
                metadata = {
                    "original_plugin_id": "",
                    "original_item_id": "",
                    "usage_count": usage_count,
                    "track_history": False,
                }

            # Create item_id with error handling
            try:
                timestamp = entry.get('timestamp', 0)
                if not isinstance(timestamp, (int, float)):
                    logger.warning(f"timestamp is not numeric ({type(timestamp)}): {repr(timestamp)} - using 0")
                    timestamp = 0
                item_id = f"history_{timestamp}"
            except Exception as id_error:
                logger.warning(f"Error creating item_id: {id_error} - using fallback")
                import time
                item_id = f"history_{int(time.time())}"

            # Create the search result with comprehensive error handling
            try:
                result = SearchResult(
                    plugin_id="history",
                    item_id=item_id,
                    name=display_name,
                    description=display_description,
                    icon=icon,
                    score=score,
                    metadata=metadata,
                )

                logger.debug(f"Created history result: '{display_name}' with score {score}")
                return result

            except Exception as result_error:
                logger.error(f"Error creating SearchResult object: {result_error}")
                return None

        except MemoryError as e:
            logger.error(f"MemoryError creating history result: {e}")
            return None
        except Exception as e:
            logger.error(f"Critical error creating history result: {e}")
            logger.debug(f"Error context - entry: {repr(entry)}, score: {repr(score)}, query: {repr(query)}")
            # Return None to indicate failure, allowing caller to handle gracefully
            return None

    def _get_history_icon(self, entry: Dict[str, Any]) -> object:
        """Get icon for history entry"""
        try:
            # First try to get stored icon data from the history entry
            if self.history_manager:
                stored_icon = self.history_manager.get_stored_icon(
                    entry, self.icon_size
                )
                if stored_icon:
                    logger.debug(
                        f"Using stored icon for history entry: {entry.get('user_input', '')}"
                    )
                    return stored_icon

            # If no stored icon, try to get the original plugin's icon
            original_plugin_id = entry.get("plugin_id")
            original_item_id = entry.get("item_id")

            if (
                original_plugin_id
                and original_item_id
                and hasattr(self, "plugin_manager")
                and self.plugin_manager
            ):
                try:
                    # Get the original plugin
                    original_plugin = self.plugin_manager.plugins.get(
                        original_plugin_id
                    )
                    if original_plugin:
                        # Search for the original item to get its current icon
                        user_input = entry.get("user_input", "")
                        search_results = original_plugin.search(user_input)

                        # Find the exact item by item_id
                        for search_result in search_results:
                            if (
                                search_result.item_id == original_item_id
                                and search_result.icon
                            ):
                                logger.debug(
                                    f"Using original plugin icon for history entry: {entry.get('user_input', '')}"
                                )
                                return search_result.icon
                except Exception as e:
                    logger.debug(f"Could not get original plugin icon: {e}")

            # Fallback to generic history icon only if no original icon found
            try:
                icon_theme = Gtk.IconTheme.get_default()
                logger.debug(
                    f"Using fallback history icon for: {entry.get('user_input', '')}"
                )
                return icon_theme.load_icon("document-open-recent", self.icon_size, 0)
            except Exception:
                # If history icon fails, try clock icon
                try:
                    return icon_theme.load_icon(
                        "accessories-history", self.icon_size, 0
                    )
                except Exception:
                    return None

        except Exception as e:
            logger.debug(f"Could not load icon for history entry: {e}")
            return None

    def execute(self, result: SearchResult) -> bool:
        """Execute a history result by re-running the original command"""
        try:
            history_entry = result.metadata.get("history_entry")
            if not history_entry:
                logger.error("No history entry found in result metadata")
                return False

            original_plugin_id = history_entry.get("plugin_id")
            original_item_id = history_entry.get("item_id")
            user_input = history_entry.get("user_input", "")

            if not original_plugin_id or not original_item_id:
                logger.error(
                    "Missing original plugin/item information in history entry"
                )
                return False

            # Use the plugin manager that was set during initialization
            if not hasattr(self, "plugin_manager") or not self.plugin_manager:
                logger.error("Plugin manager not available")
                return False

            plugin_manager = self.plugin_manager

            # Get the original plugin
            original_plugin = plugin_manager.plugins.get(original_plugin_id)
            if not original_plugin:
                logger.error(f"Original plugin {original_plugin_id} not found")
                return False

            # Search for the original item
            search_results = original_plugin.search(user_input)

            # Find the exact item by item_id
            target_result = None
            for search_result in search_results:
                if search_result.item_id == original_item_id:
                    target_result = search_result
                    break

            if target_result:
                # Execute the original result
                return plugin_manager.execute(target_result)
            else:
                logger.warning(
                    f"Could not find original item {original_item_id} in plugin {original_plugin_id}"
                )
                return False

        except Exception as e:
            logger.error(f"Error executing history result: {e}")
            return False

    def cleanup(self) -> None:
        """Clean up resources"""
        self.history_manager = None
