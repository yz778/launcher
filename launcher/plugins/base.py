import logging
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from launcher import services
from launcher.utils.scoring_system import FieldHighlight

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
    hilight: Optional["FieldHighlight"] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the SearchResult to a dictionary, excluding hilight data."""
        result_dict = asdict(self)
        result_dict.pop("hilight", None)  # don't store in history
        return result_dict

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

    def get_cache_dir(self) -> str:
        return services.config.system.cache_dir

    def get_terminal_command(self) -> str:
        return services.config.system.get("terminal_command")

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
