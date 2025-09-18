"""
IPCService implementation for dependency injection.
"""

from typing import Callable

from launcher.core.ipc import IPCManager
from launcher.services import IPCServiceProtocol


class IPCService(IPCServiceProtocol):
    """Service wrapper for IPCManager implementing the IPCServiceProtocol."""

    def __init__(self, app_name: str = "launcher"):
        """Initialize the IPC service.

        Args:
            app_name: Application name for IPC
        """
        self._ipc_manager = IPCManager(app_name)

    def register_handler(self, command: str, handler: Callable) -> None:
        """Register a command handler.

        Args:
            command: Command name (e.g., "THEME")
            handler: Function to call when the command is received
        """
        self._ipc_manager.register_handler(command, handler)

    def start_server(self) -> bool:
        """Start the IPC server.

        Returns:
            True if server started successfully, False otherwise
        """
        return self._ipc_manager.start_server()

    def stop_server(self) -> None:
        """Stop the IPC server."""
        self._ipc_manager.stop_server()

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
        return IPCManager.send_command(app_name, command, timeout)

    @property
    def ipc_manager(self) -> IPCManager:
        """Get the underlying IPCManager instance."""
        return self._ipc_manager
