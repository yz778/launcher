"""
ConfigService implementation for dependency injection.
"""

from typing import Any, Optional

from launcher.core.config import ConfigManager
from launcher.services import ConfigServiceProtocol


class ConfigService(ConfigServiceProtocol):
    """Service wrapper for ConfigManager implementing the ConfigServiceProtocol."""

    def __init__(self, config_file: Optional[str] = None):
        """Initialize the config service.

        Args:
            config_file: Path to the configuration file
        """
        self._config_manager = ConfigManager(config_file)

    def get_config(self) -> Any:
        """Get the current configuration object."""
        return self._config_manager.get()

    def update_config(self, key_path: str, value: Any) -> bool:
        """Update a configuration value.

        Args:
            key_path: Dot-separated path to the config key (e.g., "system.theme")
            value: New value to set

        Returns:
            True if update was successful, False otherwise
        """
        return self._config_manager.update_config(key_path, value)

    def get_cache_dir(self) -> str:
        """Get the cache directory path."""
        return self._config_manager.get_cache_dir()

    @property
    def config_manager(self) -> ConfigManager:
        """Get the underlying ConfigManager instance."""
        return self._config_manager
