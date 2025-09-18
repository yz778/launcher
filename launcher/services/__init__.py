"""
Service protocols and interfaces for dependency injection.
"""

from typing import Any, Dict, List, Optional, Protocol


class ConfigServiceProtocol(Protocol):
    """Protocol for configuration management service."""

    def get_config(self) -> Any:
        """Get the current configuration object."""
        ...

    def update_config(self, key_path: str, value: Any) -> bool:
        """Update a configuration value.

        Args:
            key_path: Dot-separated path to the config key (e.g., "system.theme")
            value: New value to set

        Returns:
            True if update was successful, False otherwise
        """
        ...

    def get_cache_dir(self) -> str:
        """Get the cache directory path."""
        ...


class IPCServiceProtocol(Protocol):
    """Protocol for IPC (Inter-Process Communication) service."""

    def register_handler(self, command: str, handler: callable) -> None:
        """Register a command handler.

        Args:
            command: Command name (e.g., "THEME")
            handler: Function to call when the command is received
        """
        ...

    def start_server(self) -> bool:
        """Start the IPC server.

        Returns:
            True if server started successfully, False otherwise
        """
        ...

    def stop_server(self) -> None:
        """Stop the IPC server."""
        ...

    @staticmethod
    def send_command(app_name: str, command: str, timeout: float = 0.5) -> bool:
        """Send a command to a running instance.

        Args:
            app_name: Application name
            command: Command to send
            timeout: Timeout in seconds

        Returns:
            True if command was sent successfully, False otherwise
        """
        ...


class ThemeServiceProtocol(Protocol):
    """Protocol for theme management service."""

    def load_theme(
        self,
        theme_name: str,
        plugins: Optional[Dict] = None,
        with_transition: bool = False,
    ) -> bool:
        """Load and apply a theme.

        Args:
            theme_name: Name of the theme to load
            plugins: Dictionary of loaded plugins (optional)
            with_transition: Whether to apply transition effects

        Returns:
            True if theme loaded successfully, False otherwise
        """
        ...

    def get_available_themes(self) -> List[Dict[str, str]]:
        """Get list of available themes.

        Returns:
            List of dicts with 'name' and 'display_name' keys
        """
        ...

    def get_highlight_style(self) -> tuple[str, str]:
        """Get the highlight color and weight from the current theme.

        Returns:
            Tuple of (color, weight)
        """
        ...

    def cleanup(self) -> None:
        """Clean up theme resources."""
        ...
