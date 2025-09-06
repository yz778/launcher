from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, field
from typing import List, Any, Dict, Optional
import logging
import os
import sys

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Class representing a search result from any plugin"""

    plugin_id: str
    item_id: str
    name: str
    description: str = ""
    icon_spec: Optional[str] = None
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the SearchResult to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SearchResult":
        """Create a SearchResult from a dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class Plugin(ABC):
    """Base class for all launcher plugins"""

    __slots__ = ("config", "prefix")
    DEFAULTS = {}

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
        self.config = None
        self.prefix: Optional[str] = None

    def get_prefix(self) -> Optional[str]:
        """
        Get the prefix for this plugin, if any.

        Returns:
            The prefix string (e.g., ">") or None if no prefix is used
        """
        return self.prefix

    def has_prefix(self) -> bool:
        """
        Check if this plugin uses a prefix.

        Returns:
            True if plugin has a prefix, False otherwise
        """
        return self.prefix is not None and self.prefix != ""

    def get_general_config(self, key: str, default: Any = None) -> Any:
        """Helper to get a value from the system config section."""
        # Access system config through global services
        from launcher import services

        if services.config and hasattr(services.config, "system"):
            return getattr(services.config.system, key, default)
        return default

    def should_track_history(self) -> bool:
        """
        Check if this plugin should track executions in history

        Returns:
            True if executions should be tracked in history, False otherwise
        """
        return getattr(self.config, "track_history", True) if self.config else True

    def get_default_css(self) -> str:
        """Return the contents of 'default.css' from the plugin's directory, or an empty string if not found."""
        module = sys.modules[self.__class__.__module__]
        subclass_file = getattr(module, "__file__", None)
        if not subclass_file:
            return ""
        file_path = os.path.join(
            os.path.dirname(os.path.abspath(subclass_file)), "default.css"
        )
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except (OSError, IOError):
            return ""

    def initialize(self, config) -> bool:
        """
        Initialize the plugin with the given configuration.
        Base implementation stores the config. Subclasses should call super().

        This method should only load configuration and CSS, without doing any heavy setup work.
        Use the start() method for actual setup work that should be done after the GUI is started.

        Args:
            config: Plugin-specific configuration object (AttrDict)

        Returns:
            True if initialization was successful, False otherwise
        """
        self.config = config
        return True

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
                return False

            # Required fields validation
            required_fields = [
                "plugin_id",
                "item_id",
                "name",
                "result",
                "last_execution_time",
                "usage_count",
            ]
            for field in required_fields:
                if field not in entry:
                    logger.debug(f"Missing required field: {field}")
                    return False

            # Type validation
            plugin_id = entry.get("plugin_id")
            item_id = entry.get("item_id")
            name = entry.get("name")
            result = entry.get("result")
            last_execution_time = entry.get("last_execution_time")
            usage_count = entry.get("usage_count")

            if not isinstance(plugin_id, str) or not plugin_id.strip():
                logger.debug(f"Invalid plugin_id: {plugin_id}")
                return False

            if not isinstance(item_id, str) or not item_id.strip():
                logger.debug(f"Invalid item_id: {item_id}")
                return False

            if not isinstance(name, str):
                logger.debug(f"Invalid name: {name}")
                return False

            if not isinstance(result, dict):
                logger.debug(f"Invalid result: {result}")
                return False

            if (
                not isinstance(last_execution_time, (int, float))
                or last_execution_time <= 0
            ):
                logger.debug(f"Invalid last_execution_time: {last_execution_time}")
                return False

            if not isinstance(usage_count, int) or usage_count <= 0:
                logger.debug(f"Invalid usage_count: {usage_count}")
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
            Terminal command string
        """
        return self.get_general_config("terminal_command")

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

    _empty_input_handlers = []
