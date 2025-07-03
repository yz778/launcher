#!/usr/bin/env python3

import logging
import math
import time
from typing import List, Dict, Any
from plugins.base import Plugin, SearchResult
from utils.string_matcher import StringMatcher

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
            # Get all history entries
            all_history = self.history_manager.user_input_history
            
            # Search through history entries
            for entry in all_history:
                user_input = entry.get("user_input", "")
                executed_command = entry.get("executed_command", "")
                description = entry.get("description", "")
                
                # Calculate best match score from all fields
                best_score = max(
                    self._calculate_match_score(query, user_input),
                    self._calculate_match_score(query, executed_command) if executed_command != user_input else 0,
                    self._calculate_match_score(query, description) * 0.5 if description else 0
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

    def _create_history_result(self, entry: Dict[str, Any], score: float, query: str) -> SearchResult:
        """Create a SearchResult from a history entry"""
        try:
            user_input = entry.get("user_input", "")
            executed_command = entry.get("executed_command", user_input)
            description = entry.get("description", "")
            plugin_id = entry.get("plugin_id", "")
            item_id = entry.get("item_id", "")
            usage_count = entry.get("usage_count", 1)
            
            # Try to get the original icon if available
            icon = self._get_history_icon(entry)
            
            # Create display name and description
            display_name = user_input
            
            # Build description without usage count (usage count will be shown separately)
            if executed_command and executed_command != user_input:
                display_description = executed_command
            else:
                display_description = ""
            
            if description and description != executed_command and description != user_input:
                if display_description:
                    display_description += f" - {description}"
                else:
                    display_description = description
            
            # Create the search result
            result = SearchResult(
                plugin_id="history",
                item_id=f"history_{entry.get('timestamp', 0)}",
                name=display_name,
                description=display_description,
                icon=icon,
                score=score,
                metadata={
                    "original_plugin_id": plugin_id,
                    "original_item_id": item_id,
                    "history_entry": entry,
                    "usage_count": usage_count,  # Store usage count for AppListItem
                    "track_history": False,  # Don't track history searches in history
                }
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error creating history result: {e}")
            return None

    def _get_history_icon(self, entry: Dict[str, Any]) -> object:
        """Get icon for history entry"""
        try:
            # First try to get stored icon data from the history entry
            if self.history_manager:
                stored_icon = self.history_manager.get_stored_icon(entry, self.icon_size)
                if stored_icon:
                    logger.debug(f"Using stored icon for history entry: {entry.get('user_input', '')}")
                    return stored_icon
            
            # If no stored icon, try to get the original plugin's icon
            original_plugin_id = entry.get("plugin_id")
            original_item_id = entry.get("item_id")
            
            if original_plugin_id and original_item_id and hasattr(self, 'plugin_manager') and self.plugin_manager:
                try:
                    # Get the original plugin
                    original_plugin = self.plugin_manager.plugins.get(original_plugin_id)
                    if original_plugin:
                        # Search for the original item to get its current icon
                        user_input = entry.get("user_input", "")
                        search_results = original_plugin.search(user_input)
                        
                        # Find the exact item by item_id
                        for search_result in search_results:
                            if search_result.item_id == original_item_id and search_result.icon:
                                logger.debug(f"Using original plugin icon for history entry: {entry.get('user_input', '')}")
                                return search_result.icon
                except Exception as e:
                    logger.debug(f"Could not get original plugin icon: {e}")
            
            # Fallback to generic history icon only if no original icon found
            try:
                import gi
                gi.require_version("Gtk", "3.0")
                from gi.repository import Gtk
                
                icon_theme = Gtk.IconTheme.get_default()
                logger.debug(f"Using fallback history icon for: {entry.get('user_input', '')}")
                return icon_theme.load_icon("document-open-recent", self.icon_size, 0)
            except Exception:
                # If history icon fails, try clock icon
                try:
                    return icon_theme.load_icon("accessories-history", self.icon_size, 0)
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
                logger.error("Missing original plugin/item information in history entry")
                return False
            
            # Use the plugin manager that was set during initialization
            if not hasattr(self, 'plugin_manager') or not self.plugin_manager:
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
                logger.warning(f"Could not find original item {original_item_id} in plugin {original_plugin_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error executing history result: {e}")
            return False

    def cleanup(self) -> None:
        """Clean up resources"""
        self.history_manager = None