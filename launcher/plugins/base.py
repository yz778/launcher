#!/usr/bin/env python3

from abc import ABC, abstractmethod
from typing import List, Any, Dict, Optional


class SearchResult:
    """Class representing a search result from any plugin"""
    
    __slots__ = ('plugin_id', 'item_id', 'name', 'description', 'icon', 'score', 'metadata')

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

    __slots__ = ('config', 'track_history')

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
        self.track_history = True  # Default value, will be set from config

    def get_general_config(self, key: str, default: Any = None) -> Any:
        """Helper to get a value from the [general] config section."""
        return self.config.get("general", {}).get(key, default)
    
    def should_track_history(self) -> bool:
        """
        Check if this plugin should track executions in history
        
        Returns:
            True if executions should be tracked in history, False otherwise
        """
        return getattr(self, 'track_history', True)

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

    def initialize(self, config: Dict[str, Any]) -> bool:
        """
        Initialize the plugin with the given configuration.
        Base implementation stores the config. Subclasses should call super().

        This method should only load configuration and CSS, without doing any heavy setup work.
        Use the start() method for actual setup work that should be done after the GUI is started.

        Args:
            config: Plugin-specific configuration

        Returns:
            True if initialization was successful, False otherwise
        """
        self.config = config
        return True

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
