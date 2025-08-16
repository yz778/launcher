#!/usr/bin/env python3

import logging
from abc import ABC, abstractmethod
from typing import List, Any, Dict, Optional

logger = logging.getLogger(__name__)


class SearchResult:
    """Class representing a search result from any plugin"""

    __slots__ = (
        "plugin_id",
        "item_id",
        "name",
        "description",
        "icon",
        "score",
        "metadata",
    )

    def __init__(
        self,
        plugin_id: str,
        item_id: str,
        name: str,
        description: str = "",
        icon: Any = None,
        score: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize a search result

        Args:
            plugin_id: ID of the plugin that provided this result
            item_id: Unique ID for this item within the plugin
            name: Display name of the result
            description: Optional description
            icon: Optional icon (can be a path, pixbuf, or other format depending on the plugin)
            score: Match score (0-100, higher is better)
            metadata: Additional metadata specific to the plugin
        """
        self.plugin_id = plugin_id
        self.item_id = item_id
        self.name = name
        self.description = description
        self.icon = icon
        self.score = score
        self.metadata = metadata or {}


class Plugin(ABC):
    """Base class for all launcher plugins"""

    __slots__ = ("config", "config_manager")

    @abstractmethod
    def get_id(self) -> str:
        """Get the unique ID of the plugin"""

    @abstractmethod
    def get_name(self) -> str:
        """Get the display name of the plugin"""

    @abstractmethod
    def get_description(self) -> str:
        """Get the description of the plugin"""

    def __init__(self):
        """Initialize the plugin base class"""
        self.config: Dict[str, Any] = {}
        self.config_manager = None

    def get_general_config(self, key: str, default: Any = None) -> Any:
        """Helper to get a value from the [general] config section."""
        if self.config_manager:
            config = self.config_manager.get_config()
            general_config = config.get("general", {})
            return general_config.get(key, default)
        return default

    def should_track_history(self) -> bool:
        """
        Check if this plugin should track executions in history

        Returns:
            True if executions should be tracked in history, False otherwise
        """
        return self.config.get("track_history", True)

    @abstractmethod
    def get_config_defaults(self) -> Dict[str, Any]:
        """
        Get the default configuration for this plugin

        Returns:
            Dictionary containing default configuration values for this plugin
        """

    def get_default_css(self) -> str:
        """
        Get the default CSS for this plugin

        Returns:
            String containing default CSS for this plugin
        """
        return ""  # Default implementation returns empty string

    def initialize(self, config: Dict[str, Any], config_manager) -> bool:
        """
        Initialize the plugin with the given configuration.
        Base implementation stores the config. Subclasses should call super().

        This method should only load configuration and CSS, without doing any heavy setup work.
        Use the start() method for actual setup work that should be done after the GUI is started.

        Args:
            config: Plugin-specific configuration
            config_manager: The central config manager instance

        Returns:
            True if initialization was successful, False otherwise
        """
        self.config = config
        self.config_manager = config_manager
        return True

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Helper to get a plugin-specific configuration value with fallback to defaults

        Args:
            key: Configuration key to retrieve
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        defaults = self.get_config_defaults()
        return self.config.get(key, defaults.get(key, default))

    def get_icon_size(self) -> int:
        """
        Helper to get the icon size from general configuration

        Returns:
            Icon size in pixels (default: 48)
        """
        return self.get_general_config("icon_size", 48)

    @staticmethod
    def is_structurally_valid(
        entry: Dict[str, Any], plugin_manager: Optional[Any] = None
    ) -> bool:
        """
        Check if a history entry has valid structure and types.

        This function performs basic structural and type validation that is common
        across all plugins and the history manager.

        Args:
            entry: History entry to validate
            plugin_manager: Optional plugin manager to check if plugins still exist

        Returns:
            True if entry has valid structure and types, False otherwise
        """
        try:
            # Basic structure validation
            if not isinstance(entry, dict):
                logger.debug(f"Entry is not a dict: {type(entry)}")
                return False

            # Required fields validation
            required_fields = ["user_input", "plugin_id", "item_id", "timestamp"]
            for field in required_fields:
                if field not in entry:
                    logger.debug(f"Entry missing required field '{field}': {entry}")
                    return False

            # Type validation
            user_input = entry.get("user_input")
            plugin_id = entry.get("plugin_id")
            item_id = entry.get("item_id")
            timestamp = entry.get("timestamp")

            if not isinstance(user_input, str) or not user_input.strip():
                logger.debug(f"Invalid user_input: {user_input}")
                return False

            if not isinstance(plugin_id, str) or not plugin_id.strip():
                logger.debug(f"Invalid plugin_id: {plugin_id}")
                return False

            if not isinstance(item_id, str) or not item_id.strip():
                logger.debug(f"Invalid item_id: {item_id}")
                return False

            if not isinstance(timestamp, (int, float)) or timestamp <= 0:
                logger.debug(f"Invalid timestamp: {timestamp}")
                return False

            # Plugin existence validation (if plugin_manager provided)
            if plugin_manager and hasattr(plugin_manager, "plugins"):
                if plugin_id not in plugin_manager.plugins:
                    logger.debug(f"Plugin no longer exists: {plugin_id}")
                    return False

            return True

        except Exception as e:
            logger.debug(f"Error validating history entry structure: {e}")
            return False

    def get_terminal_command(self) -> str:
        """
        Helper to get the terminal command from general configuration

        Returns:
            Terminal command string (default: "term")
        """
        return self.get_general_config("terminal_command", "term")

    def start(self) -> bool:
        """
        Start the plugin and perform any necessary setup work

        This method is called after the GUI is started and should perform any
        heavy setup work like loading data, scanning files, etc.

        Returns:
            True if startup was successful, False otherwise
        """
        return True  # Default implementation does nothing

    @abstractmethod
    def search(self, query: str) -> List[SearchResult]:
        """
        Search for items matching the query

        Args:
            query: The search query

        Returns:
            List of search results matching the query
        """

    @abstractmethod
    def execute(self, result: SearchResult) -> bool:
        """
        Execute the given search result

        Args:
            result: The search result to execute

        Returns:
            True if execution was successful, False otherwise
        """

    def cleanup(self) -> None:
        """
        Clean up resources used by the plugin

        This method is called when the plugin is being unloaded.
        Override this method to release any resources used by the plugin.
        """

    def clean_invalid_history_entries(self, history_manager) -> int:
        """
        Clean invalid history entries for this plugin.

        Args:
            history_manager: The history manager instance

        Returns:
            Number of entries removed
        """
        # Default implementation does nothing
        # Plugins that need history cleanup should override this
        return 0

    _empty_input_handlers = []

    @classmethod
    def register_global_empty_input_handler(cls, handler):
        """Register a global handler for empty input population."""
        cls._empty_input_handlers.append(handler)

    @classmethod
    def call_global_empty_input_handlers(cls, launcher_window):
        for handler in cls._empty_input_handlers:
            try:
                handler(launcher_window)
            except Exception as e:
                logger.error(f"Error in global empty input handler: {e}")
