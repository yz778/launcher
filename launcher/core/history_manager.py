#!/usr/bin/env python3

import os
import json
import logging
import time
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class HistoryManager:
    """Manager for tracking and persisting launch history"""

    def __init__(self, config=None):
        self.user_input_history: List[Dict[str, Any]] = (
            []
        )  # List of user input entries with timestamps
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
                    data = json.load(f)
                
                # Expect only the new format: a list of history entries
                if isinstance(data, list):
                    self.user_input_history = data
                else:
                    # Invalid format, start fresh
                    logger.warning(f"Invalid history format in {self.history_file}, starting fresh")
                    self.user_input_history = []
                    
                logger.info(f"Loaded history from {self.history_file}")
            except Exception as e:
                logger.error(f"Error loading history from {self.history_file}: {e}")
                self.user_input_history = []
        else:
            logger.info(f"History file not found, starting with empty history")
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
        count = 0
        for entry in self.user_input_history:
            if (entry.get("plugin_id") == plugin_id and 
                entry.get("item_id") == item_id):
                count += 1
        return count

    def add_execution(self, plugin_id: str, item_id: str, user_input: str, result_name: str = None) -> None:
        """
        Record a successful execution in history.

        Args:
            plugin_id: Plugin ID that was executed
            item_id: Item ID that was executed
            user_input: The exact text that the user typed before submitting
            result_name: Display name of the executed item
        """
        current_time = time.time()
        
        # Add to user input history
        self.add_user_input_history(user_input, plugin_id, item_id, current_time, result_name)

    def add_user_input_history(self, user_input: str, plugin_id: str, item_id: str, timestamp: float = None, result_name: str = None) -> None:
        """
        Add user input to history, removing duplicates and maintaining order.
        
        Args:
            user_input: The exact text that the user typed
            plugin_id: Plugin ID that was executed
            item_id: Item ID that was executed  
            timestamp: Timestamp when executed (defaults to current time)
            result_name: Display name of the executed item
        """
        if timestamp is None:
            timestamp = time.time()
            
        # Remove any existing entry with the same user input
        self.user_input_history = [
            entry for entry in self.user_input_history 
            if entry.get("user_input", "").lower() != user_input.lower()
        ]
        
        # Add new entry at the beginning (most recent first)
        entry = {
            "user_input": user_input,
            "plugin_id": plugin_id,
            "item_id": item_id,
            "timestamp": timestamp,
            "result_name": result_name
        }
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
            if user_input.lower().startswith(partial_lower) and user_input.lower() != partial_lower:
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
            entry for entry in self.user_input_history 
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
