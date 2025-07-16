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
        if not self._is_valid_query(query):
            return []

        try:
            all_history = self._get_validated_history()
            if not all_history:
                return []

            results = self._search_history_entries(all_history, query)
            return self._sort_and_limit_results(results)

        except Exception as e:
            logger.error(f"Error searching history: {e}")
            return []

    def _is_valid_query(self, query: str) -> bool:
        """Check if query is valid for searching"""
        min_length = self.config.get("min_query_length", 2)
        return len(query) >= min_length

    def _get_validated_history(self) -> List[Dict[str, Any]]:
        """Get and validate history data"""
        all_history = self.history_manager.user_input_history

        if not isinstance(all_history, list):
            logger.warning(f"History data is not a list ({type(all_history)}) - returning empty results")
            return []

        return all_history

    def _search_history_entries(self, all_history: List[Dict[str, Any]], query: str) -> List[SearchResult]:
        """Search through history entries and create results"""
        results = []

        for entry in all_history:
            if not self._is_valid_entry(entry):
                continue

            entry_data = self._extract_search_fields(entry)
            if not entry_data:
                continue

            best_score = self._calculate_best_match_score(query, entry_data)
            if best_score > 0:
                final_score = self._apply_boosts(entry, best_score)
                result = self._create_history_result(entry, final_score, query)
                if result:
                    results.append(result)

        return results

    def _is_valid_entry(self, entry: Dict[str, Any]) -> bool:
        """Validate entry structure"""
        try:
            if not isinstance(entry, dict):
                logger.debug(f"History entry is not a dict ({type(entry)}) - skipping")
                return False

            user_input = entry.get("user_input", "")
            if not isinstance(user_input, str):
                logger.debug(f"user_input is not a string ({type(user_input)}) - skipping entry")
                return False

            return True
        except Exception as entry_error:
            logger.debug(f"Error processing history entry: {entry_error} - skipping")
            return False

    def _extract_search_fields(self, entry: Dict[str, Any]) -> Dict[str, str]:
        """Extract searchable fields from entry"""
        try:
            return {
                "user_input": entry.get("user_input", ""),
                "executed_command": entry.get("executed_command", ""),
                "description": entry.get("description", "")
            }
        except Exception as e:
            logger.debug(f"Error extracting search fields: {e}")
            return None

    def _calculate_best_match_score(self, query: str, entry_data: Dict[str, str]) -> float:
        """Calculate the best match score from all searchable fields"""
        from launcher.utils.scoring_system import score_name_match, score_description_match
        
        # Name matches (user input and executed command)
        user_input_score = score_name_match(query, entry_data["user_input"])
        
        executed_command_score = 0
        if entry_data["executed_command"] != entry_data["user_input"]:
            executed_command_score = score_name_match(query, entry_data["executed_command"])

        # Description match (gets lower scoring automatically)
        description_score = 0
        if entry_data["description"]:
            description_score = score_description_match(query, entry_data["description"])

        return max(user_input_score, executed_command_score, description_score)

    def _sort_and_limit_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """Sort results by score and limit to max results"""
        max_results = self.config.get("max_results", 10)
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:max_results]


    def _apply_boosts(self, entry: Dict[str, Any], base_score: float) -> float:
        """Apply boosts based on recency and frequency"""
        from launcher.utils.scoring_system import apply_history_boost, apply_usage_boost, apply_recency_boost
        
        score = base_score

        # Apply history boost (this is a history plugin, so always boost)
        score = apply_history_boost(score)

        # Boost for frequency (usage count)
        if self.config.get("boost_frequent", True):
            usage_count = entry.get("usage_count", 1)
            score = apply_usage_boost(score, usage_count)

        # Boost for recency
        if self.config.get("boost_recent", True):
            timestamp = entry.get("timestamp", 0)
            current_time = time.time()
            age_hours = (current_time - timestamp) / 3600
            score = apply_recency_boost(score, age_hours)

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
            if not self._validate_result_inputs(entry, score, query):
                return None

            entry_data = self._extract_entry_data_safely(entry)
            if not entry_data:
                return None

            metadata = self._build_result_metadata(entry, entry_data)
            icon = self._get_history_icon_safely(entry)
            item_id = self._create_item_id(entry)

            return self._create_search_result_object(entry_data, metadata, icon, item_id, score)

        except MemoryError as e:
            logger.error(f"MemoryError creating history result: {e}")
            return None
        except Exception as e:
            logger.error(f"Critical error creating history result: {e}")
            logger.debug(f"Error context - entry: {repr(entry)}, score: {repr(score)}, query: {repr(query)}")
            return None

    def _validate_result_inputs(self, entry: Dict[str, Any], score: float, query: str) -> bool:
        """Validate inputs for result creation"""
        if not isinstance(entry, dict):
            logger.error(f"History entry is not a dict ({type(entry)}): {repr(entry)}")
            return False

        if not isinstance(score, (int, float)):
            logger.warning(f"Score is not numeric ({type(score)}): {repr(score)} - using 0.0")
            score = 0.0

        if not isinstance(query, str):
            logger.warning(f"Query is not a string ({type(query)}): {repr(query)} - using empty string")
            query = ""

        return True

    def _extract_entry_data_safely(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Safely extract and validate entry data"""
        try:
            user_input = self._get_string_field(entry, "user_input", "")
            executed_command = self._get_string_field(entry, "executed_command", user_input)
            description = self._get_string_field(entry, "description", "")
            usage_count = self._get_numeric_field(entry, "usage_count", 1)

            original_plugin_id = self._validate_original_plugin_id(entry)
            original_item_id = self._validate_original_item_id(entry)

            display_name = user_input if user_input else "Unknown Command"
            display_description = self._build_display_description(executed_command, description, user_input)

            return {
                "user_input": user_input,
                "executed_command": executed_command,
                "description": description,
                "usage_count": usage_count,
                "original_plugin_id": original_plugin_id,
                "original_item_id": original_item_id,
                "display_name": display_name,
                "display_description": display_description
            }
        except Exception as e:
            logger.error(f"Error extracting entry data: {e}")
            return None

    def _get_string_field(self, entry: Dict[str, Any], field_name: str, default: str) -> str:
        """Safely get string field from entry"""
        try:
            value = entry.get(field_name, default)
            if not isinstance(value, str):
                logger.warning(f"{field_name} is not a string ({type(value)}): {repr(value)} - using default")
                return default
            return value
        except Exception as e:
            logger.warning(f"Error getting {field_name} from entry: {e} - using default")
            return default

    def _get_numeric_field(self, entry: Dict[str, Any], field_name: str, default: int) -> int:
        """Safely get numeric field from entry"""
        try:
            value = entry.get(field_name, default)
            if not isinstance(value, (int, float)):
                logger.warning(f"{field_name} is not numeric ({type(value)}): {repr(value)} - using default")
                return default
            return int(value)
        except Exception as e:
            logger.warning(f"Error getting {field_name} from entry: {e} - using default")
            return default

    def _build_display_description(self, executed_command: str, description: str, user_input: str) -> str:
        """Build display description from entry data"""
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

            return display_description
        except Exception as desc_error:
            logger.warning(f"Error building display description: {desc_error} - using empty string")
            return ""

    def _build_result_metadata(self, entry: Dict[str, Any], entry_data: Dict[str, Any]) -> Dict[str, Any]:
        """Build metadata for the search result"""
        try:
            return {
                "original_plugin_id": entry_data["original_plugin_id"],
                "original_item_id": entry_data["original_item_id"],
                "history_entry": entry,
                "usage_count": entry_data["usage_count"],
                "track_history": False,
                "has_original_metadata": bool(entry_data["original_plugin_id"] and entry_data["original_item_id"]),
            }
        except Exception as metadata_create_error:
            logger.error(f"Error creating metadata dict: {metadata_create_error} - using minimal metadata")
            return {
                "original_plugin_id": "",
                "original_item_id": "",
                "usage_count": entry_data.get("usage_count", 1),
                "track_history": False,
            }

    def _get_history_icon_safely(self, entry: Dict[str, Any]) -> object:
        """Safely get history icon"""
        try:
            return self._get_history_icon(entry)
        except Exception as icon_error:
            logger.warning(f"Error getting history icon: {icon_error} - using None")
            return None

    def _create_item_id(self, entry: Dict[str, Any]) -> str:
        """Create item ID for the result"""
        try:
            timestamp = entry.get('timestamp', 0)
            if not isinstance(timestamp, (int, float)):
                logger.warning(f"timestamp is not numeric ({type(timestamp)}): {repr(timestamp)} - using 0")
                timestamp = 0
            return f"history_{timestamp}"
        except Exception as id_error:
            logger.warning(f"Error creating item_id: {id_error} - using fallback")
            import time
            return f"history_{int(time.time())}"

    def _create_search_result_object(self, entry_data: Dict[str, Any], metadata: Dict[str, Any],
                                   icon: object, item_id: str, score: float) -> SearchResult:
        """Create the final SearchResult object"""
        try:
            result = SearchResult(
                plugin_id="history",
                item_id=item_id,
                name=entry_data["display_name"],
                description=entry_data["display_description"],
                icon=icon,
                score=score,
                metadata=metadata,
            )

            logger.debug(f"Created history result: '{entry_data['display_name']}' with score {score}")
            return result

        except Exception as result_error:
            logger.error(f"Error creating SearchResult object: {result_error}")
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
