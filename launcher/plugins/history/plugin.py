#!/usr/bin/env python3

from ..base import Plugin, SearchResult
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class HistoryPlugin(Plugin):
    """Plugin for searching through command history"""

    def register_with_launcher(self, launcher_window=None):
        """Register the history handler for empty input globally."""
        self.__class__.register_global_empty_input_handler(
            self._populate_recent_history
        )

    def _populate_recent_history(self, launcher_window):
        """Populate the launcher window with recent history items when input is empty."""
        if not self.history_manager:
            return
        all_history = self.history_manager.get_recent_history(100)
        if not all_history:
            return
        # Clear the list box (should already be done by launcher, but safe)
        launcher_window._clear_list_box()
        for history_entry in all_history:
            if not history_entry.get("user_input"):
                continue
            result = self._create_history_result(history_entry, 0, "")
            if result:
                from ui.launcher_window import AppListItem

                list_item = AppListItem(
                    result,
                    icon_size=launcher_window.icon_size or 48,
                    launch_count=history_entry.get("usage_count", 0),
                    query="",
                )
                list_item.set_name("history-item")
                list_item.user_input = history_entry.get("user_input", "")
                list_item.history_entry = history_entry
                launcher_window.list_box.add(list_item)
        launcher_window.list_box.show_all()
        launcher_window.scrolled.show()

        count_text = (
            f"{len(all_history)} history item{'s' if len(all_history) != 1 else ''}"
        )
        launcher_window._setup_results_display(all_history, count_text)

    def __init__(self):
        super().__init__()
        self.history_manager = None

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
        }

    def initialize(self, config: Dict[str, Any], config_manager=None) -> bool:
        """Initialize the history plugin"""
        try:
            self.config = config

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
        min_length = self.get_config_value("min_query_length", 2)
        return len(query) >= min_length

    def _get_validated_history(self) -> List[Dict[str, Any]]:
        """Get and validate history data"""
        all_history = self.history_manager.user_input_history

        if not isinstance(all_history, list):
            logger.warning(
                f"History data is not a list ({type(all_history)}) - returning empty results"
            )
            return []

        return all_history

    def _search_history_entries(
        self, all_history: List[Dict[str, Any]], query: str
    ) -> List[SearchResult]:
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
                result = self._create_history_result(entry, best_score, query)
                if result:
                    results.append(result)

        return results

    def _is_valid_entry(self, entry: Dict[str, Any]) -> bool:
        """Validate entry structure"""
        try:
            if not isinstance(entry, dict):
                return False

            user_input = entry.get("user_input", "")
            if not isinstance(user_input, str):
                return False

            return True
        except Exception:
            return False

    def _extract_search_fields(self, entry: Dict[str, Any]) -> Dict[str, str]:
        """Extract searchable fields from entry"""
        try:
            return {
                "user_input": entry.get("user_input", ""),
                "actual_command": entry.get("actual_command", ""),
                "result_name": entry.get("result_name", ""),
                "description": entry.get("description", ""),
            }
        except Exception:
            return None

    def _calculate_best_match_score(
        self, query: str, entry_data: Dict[str, str]
    ) -> float:
        from launcher.utils.scoring_system import calculate_match_score

        # Check if user input has arguments (spaces) - this gets priority
        user_input = entry_data["user_input"]
        user_input_with_args = user_input if " " in user_input.strip() else None

        # Priority 1: History with user arguments match
        if user_input_with_args:
            args_score = calculate_match_score(
                query,
                entry_data["user_input"],
                is_name=True,
                user_input_with_args=user_input_with_args,
            )
            if args_score > 0:
                return args_score

        # Priority 2: Name matches (user input, result name, actual command)
        name_scores = []
        name_scores.append(
            calculate_match_score(query, entry_data["user_input"], is_name=True)
        )

        # Result name (if different from user input)
        if (
            entry_data["result_name"]
            and entry_data["result_name"] != entry_data["user_input"]
        ):
            name_scores.append(
                calculate_match_score(query, entry_data["result_name"], is_name=True)
            )

        # Actual command (if different from user input)
        if (
            entry_data["actual_command"]
            and entry_data["actual_command"] != entry_data["user_input"]
        ):
            name_scores.append(
                calculate_match_score(query, entry_data["actual_command"], is_name=True)
            )

        # Priority 3: Description match
        description_score = 0
        if entry_data["description"]:
            description_score = calculate_match_score(
                query, entry_data["description"], is_name=False
            )

        # Return the best score
        all_scores = name_scores + [description_score]
        best_score = (
            max(score for score in all_scores if score > 0)
            if any(score > 0 for score in all_scores)
            else 0
        )

        # Apply argument mismatch penalty
        return self._apply_argument_mismatch_penalty(query, entry_data, best_score)

    def _sort_and_limit_results(
        self, results: List[SearchResult]
    ) -> List[SearchResult]:
        """Sort results by score and limit to max results"""
        max_results = self.get_config_value("max_results", 10)
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:max_results]

    def _validate_original_plugin_id(self, entry: Dict[str, Any]) -> str:
        """Validate and return original plugin ID with fallback behavior"""
        try:
            plugin_id = entry.get("plugin_id", "")

            # Return empty string if None or not a string
            if not isinstance(plugin_id, str):
                return ""

            # Return the plugin_id (could be empty string, which is valid for fallback)
            return plugin_id.strip()

        except Exception:
            return ""

    def _validate_original_item_id(self, entry: Dict[str, Any]) -> str:
        """Validate and return original item ID with fallback behavior"""
        try:
            item_id = entry.get("item_id", "")

            # Return empty string if None or not a string
            if not isinstance(item_id, str):
                return ""

            # Return the item_id (could be empty string, which is valid for fallback)
            return item_id.strip()

        except Exception:
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
            icon_spec = self._get_history_icon_spec(entry)
            item_id = self._create_item_id(entry)

            return self._create_search_result_object(
                entry_data, metadata, icon_spec, item_id, score
            )

        except MemoryError as e:
            logger.error(f"MemoryError creating history result: {e}")
            return None
        except Exception as e:
            logger.error(f"Critical error creating history result: {e}")
            return None

    def _validate_result_inputs(
        self, entry: Dict[str, Any], score: float, query: str
    ) -> bool:
        """Validate inputs for result creation"""
        if not isinstance(entry, dict):
            logger.error(f"History entry is not a dict ({type(entry)}): {repr(entry)}")
            return False

        if not isinstance(score, (int, float)):
            logger.warning(
                f"Score is not numeric ({type(score)}): {repr(score)} - using 0.0"
            )
            score = 0.0

        if not isinstance(query, str):
            logger.warning(
                f"Query is not a string ({type(query)}): {repr(query)} - using empty string"
            )
            query = ""

        return True

    def _extract_entry_data_safely(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Safely extract and validate entry data"""
        try:
            user_input = self._get_string_field(entry, "user_input", "")
            result_name = self._get_string_field(entry, "result_name", "")
            actual_command = self._get_string_field(entry, "actual_command", user_input)
            description = self._get_string_field(entry, "description", "")
            usage_count = self._get_numeric_field(entry, "usage_count", 1)

            original_plugin_id = self._validate_original_plugin_id(entry)
            original_item_id = self._validate_original_item_id(entry)

            # Hybrid display logic: use canonical name + args if user input has args, otherwise original input
            display_name = self._build_hybrid_display_name(user_input, result_name)
            display_description = description

            return {
                "user_input": user_input,
                "result_name": result_name,
                "actual_command": actual_command,
                "description": description,
                "usage_count": usage_count,
                "original_plugin_id": original_plugin_id,
                "original_item_id": original_item_id,
                "display_name": display_name,
                "display_description": display_description,
            }
        except Exception as e:
            logger.error(f"Error extracting entry data: {e}")
            return None

    def _get_string_field(
        self, entry: Dict[str, Any], field_name: str, default: str
    ) -> str:
        """Safely get string field from entry"""
        try:
            value = entry.get(field_name, default)
            if not isinstance(value, str):
                logger.warning(
                    f"{field_name} is not a string ({type(value)}): {repr(value)} - using default"
                )
                return default
            return value
        except Exception as e:
            logger.warning(
                f"Error getting {field_name} from entry: {e} - using default"
            )
            return default

    def _get_numeric_field(
        self, entry: Dict[str, Any], field_name: str, default: int
    ) -> int:
        """Safely get numeric field from entry"""
        try:
            value = entry.get(field_name, default)
            if not isinstance(value, (int, float)):
                logger.warning(
                    f"{field_name} is not numeric ({type(value)}): {repr(value)} - using default"
                )
                return default
            return int(value)
        except Exception as e:
            logger.warning(
                f"Error getting {field_name} from entry: {e} - using default"
            )
            return default

    def _build_hybrid_display_name(self, user_input: str, result_name: str) -> str:
        """
        Build hybrid display name:
        - If result_name available: use canonical name + any args (e.g., "Firefox" or "Firefox --new-window")
        - If no result_name: use original input (e.g., "fire")
        """
        try:
            if not user_input:
                return "Unknown Command"

            # If we have a canonical result name, use it
            if result_name and result_name != user_input:
                # Check if user input has arguments (contains spaces)
                user_parts = user_input.split()
                if len(user_parts) > 1:
                    # User input has arguments, use canonical name + args
                    args = " ".join(user_parts[1:])
                    display_name = f"{result_name} {args}"
                else:
                    # No arguments, just use canonical name
                    display_name = result_name
            else:
                # No result_name available, use original input
                display_name = user_input

            return display_name

        except Exception as e:
            logger.warning(
                f"Error building hybrid display name: {e} - using user_input"
            )
            return user_input if user_input else "Unknown Command"

    def _apply_argument_mismatch_penalty(
        self, query: str, entry_data: Dict[str, str], base_score: float
    ) -> float:
        """
        Apply penalty when query and history entry have mismatched argument patterns.
        - If query has no args but history entry has args: penalize
        - If query has args but history entry has no args: penalize less
        - If both have args or both have no args: no penalty
        """
        try:
            if base_score <= 0:
                return base_score

            query_parts = query.strip().split()
            user_input_parts = entry_data["user_input"].strip().split()

            query_has_args = len(query_parts) > 1
            entry_has_args = len(user_input_parts) > 1

            # No penalty if both have same argument pattern
            if query_has_args == entry_has_args:
                return base_score

            # Moderate penalty if query has no args but entry has args
            # (user wants simple command, but history has complex command with args)
            if not query_has_args and entry_has_args:
                penalty_factor = 0.8  # Reduce score to 80%
                return base_score * penalty_factor

            # Light penalty if query has args but entry has no args
            # (user wants complex command, but history has simple command)
            elif query_has_args and not entry_has_args:
                penalty_factor = 0.9  # Reduce score to 90%
                return base_score * penalty_factor

            return base_score

        except Exception as e:
            logger.warning(f"Error applying argument mismatch penalty: {e}")
            return base_score

    def _build_result_metadata(
        self, entry: Dict[str, Any], entry_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build metadata for the search result"""
        try:
            return {
                "original_plugin_id": entry_data["original_plugin_id"],
                "original_item_id": entry_data["original_item_id"],
                "history_entry": entry,
                "usage_count": entry_data["usage_count"],
                "track_history": False,
            }
        except Exception as metadata_create_error:
            logger.error(
                f"Error creating metadata dict: {metadata_create_error} - using minimal metadata"
            )
            return {
                "original_plugin_id": "",
                "original_item_id": "",
                "usage_count": entry_data.get("usage_count", 1),
                "track_history": False,
            }

    def _create_item_id(self, entry: Dict[str, Any]) -> str:
        """Create item ID for the result"""
        try:
            timestamp = entry.get("timestamp", 0)
            if not isinstance(timestamp, (int, float)):
                logger.warning(
                    f"timestamp is not numeric ({type(timestamp)}): {repr(timestamp)} - using 0"
                )
                timestamp = 0
            return f"history_{timestamp}"
        except Exception as id_error:
            logger.warning(f"Error creating item_id: {id_error} - using fallback")
            import time

            return f"history_{int(time.time())}"

    def _create_search_result_object(
        self,
        entry_data: Dict[str, Any],
        metadata: Dict[str, Any],
        icon_spec: str,
        item_id: str,
        score: float,
    ) -> SearchResult:
        """Create the final SearchResult object"""
        try:
            result = SearchResult(
                plugin_id="history",
                item_id=item_id,
                name=entry_data["display_name"],
                description=entry_data["display_description"],
                icon_spec=icon_spec,
                score=score,
                metadata=metadata,
            )

            return result

        except Exception as result_error:
            logger.error(f"Error creating SearchResult object: {result_error}")
            return None

    def _get_history_icon_spec(self, entry: Dict[str, Any]) -> str:
        """Get icon specification for history entry"""
        try:
            icon_spec = entry.get("icon_spec")
            if icon_spec:
                # If icon_spec doesn't have a URI scheme, assume it's a theme icon for backward compatibility
                if not any(
                    icon_spec.startswith(scheme)
                    for scheme in [
                        "theme://",
                        "desktop://",
                        "file://",
                        "http://",
                        "https://",
                    ]
                ):
                    return f"theme://{icon_spec}"
                return icon_spec
            return "theme://document-open-recent"

        except Exception:
            return "theme://document-open-recent"

    def execute(self, result: SearchResult) -> bool:
        """Execute a history result by re-running the original command"""
        try:
            history_entry = result.metadata.get("history_entry")
            if not history_entry:
                logger.error("No history entry found in result metadata")
                return False

            # Reconstruct the original SearchResult from the history entry
            # Copy the original metadata to ensure all necessary context is preserved
            reconstructed_result = SearchResult(
                plugin_id=history_entry.get("plugin_id"),
                item_id=history_entry.get("item_id"),
                name=history_entry.get("result_name"),
                description=history_entry.get("description"),
                icon_spec="theme://document-open-recent",  # Use fallback icon spec
                score=0,  # Score is not relevant for re-execution
                metadata=history_entry.get(
                    "original_metadata", {}
                ).copy(),  # Copy original metadata
            )

            # Explicitly add actual_command to metadata if it exists in history_entry
            actual_command = history_entry.get("actual_command")
            if actual_command:
                reconstructed_result.metadata["actual_command"] = actual_command

            if not reconstructed_result.plugin_id or not reconstructed_result.item_id:
                logger.error(
                    "Missing original plugin/item information in history entry"
                )
                return False

            # Use the plugin manager that was set during initialization
            if not hasattr(self, "plugin_manager") or not self.plugin_manager:
                logger.error("Plugin manager not available")
                return False

            # We need to reconstruct the arguments for the command
            user_input = history_entry.get("user_input", "")
            parts = user_input.split(" ")
            if len(parts) > 1:
                reconstructed_result.metadata["args"] = parts[1:]

            # Execute the original command
            success = self.plugin_manager.execute(reconstructed_result)

            # If execution was successful, increment the usage count for this history entry
            if success and self.history_manager:
                original_plugin_id = history_entry.get("plugin_id")
                original_item_id = history_entry.get("item_id")
                if original_plugin_id and original_item_id:
                    self.history_manager.increment_usage_count(
                        original_plugin_id, original_item_id, user_input
                    )

            return success

        except Exception as e:
            logger.error(f"Error executing history result: {e}")
            return False

    def cleanup(self) -> None:
        """Clean up resources"""
        self.history_manager = None

    def get_recent_history_as_results(self, max_items: int = 100) -> List[SearchResult]:
        """Get recent history entries as SearchResults for display in launcher window"""
        if not self.history_manager:
            return []

        all_history = self.history_manager.get_recent_history(max_items)
        if not all_history:
            return []

        results = []
        for history_entry in all_history:
            if not history_entry.get("user_input"):
                continue

            try:
                result = self._create_history_search_result(history_entry)
                if result:
                    results.append(result)
            except Exception:
                continue

        return results

    def _create_history_search_result(
        self, history_entry: Dict[str, Any]
    ) -> SearchResult:
        """Create a SearchResult from a history entry"""
        user_input = history_entry.get("user_input", "")
        result_name = history_entry.get("result_name", "")
        plugin_id = history_entry.get("plugin_id", "")
        item_id = history_entry.get("item_id", "")
        description = history_entry.get("description", user_input)

        # Hybrid display logic: use canonical name + args if user input has args, otherwise original input
        display_name = self._build_hybrid_display_name(user_input, result_name)

        # Get the appropriate icon specification
        display_icon_spec = self._get_history_icon_spec_for_entry(
            plugin_id, item_id, history_entry
        )

        # Create SearchResult
        result = SearchResult(
            plugin_id="history",  # Mark as coming from history plugin
            item_id=f"history_{plugin_id}_{item_id}",  # Unique ID for history item
            name=display_name,
            description=description,
            icon_spec=display_icon_spec,
            score=0,
        )

        # Store original metadata for execution
        result.metadata = {
            "original_plugin_id": plugin_id,
            "original_item_id": item_id,
            "user_input": user_input,
            "usage_count": history_entry.get("usage_count", 0),
            "history_entry": history_entry,
        }

        return result

    def _get_history_icon_spec_for_entry(
        self, plugin_id: str, item_id: str, history_entry: Dict[str, Any]
    ) -> str:
        """Get the appropriate icon specification for a history entry"""
        return self._get_history_icon_spec(history_entry)
