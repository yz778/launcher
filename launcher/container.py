"""
Dependency Injection Container for managing service instances.
"""

from typing import Any, Dict, Type, TypeVar

from launcher.services import (
    ConfigServiceProtocol,
    IPCServiceProtocol,
    ThemeServiceProtocol,
)

T = TypeVar("T")


class DIContainer:
    """Simple dependency injection container for managing service instances."""

    def __init__(self):
        self._services: Dict[Type, Any] = {}

    def register(self, service_type: Type[T], instance: T) -> None:
        """Register a service instance.

        Args:
            service_type: The protocol/interface type
            instance: The service instance implementing the protocol
        """
        self._services[service_type] = instance

    def resolve(self, service_type: Type[T]) -> T:
        """Resolve a service instance by type.

        Args:
            service_type: The protocol/interface type to resolve

        Returns:
            The registered service instance

        Raises:
            ValueError: If the service type is not registered
        """
        if service_type not in self._services:
            raise ValueError(f"Service {service_type.__name__} not registered")
        return self._services[service_type]

    def has_service(self, service_type: Type[T]) -> bool:
        """Check if a service type is registered.

        Args:
            service_type: The protocol/interface type to check

        Returns:
            True if the service is registered, False otherwise
        """
        return service_type in self._services

    def get_config_service(self) -> ConfigServiceProtocol:
        """Get the config service instance."""
        return self.resolve(ConfigServiceProtocol)

    def get_ipc_service(self) -> IPCServiceProtocol:
        """Get the IPC service instance."""
        return self.resolve(IPCServiceProtocol)

    def get_theme_service(self) -> ThemeServiceProtocol:
        """Get the theme service instance."""
        return self.resolve(ThemeServiceProtocol)

    def clear(self) -> None:
        """Clear all registered services."""
        self._services.clear()
