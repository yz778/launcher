"""
Service bootstrapper for orchestrating service initialization in dependency order.
"""

import concurrent.futures
import logging
from typing import Optional

from xdg_base_dirs import xdg_data_home

from launcher import services
from launcher.container import DIContainer
from launcher.core.config import ConfigManager
from launcher.core.history_manager import HistoryManager
from launcher.core.ipc import IPCManager
from launcher.core.plugin_manager import PluginManager
from launcher.services.config_service import ConfigService
from launcher.services.ipc_service import IPCService
from launcher.services.theme_service import ThemeService
from launcher.ui.css_manager import CssManager

logger = logging.getLogger(__name__)


class Bootstrapper:
    """Orchestrates service initialization in dependency order with proper error handling."""

    def __init__(
        self,
        config_path: Optional[str] = None,
        plugins_dir: str = "plugins",
        foreground_mode: bool = False,
        app_name: str = "launcher",
    ):
        """Initialize the bootstrapper.

        Args:
            config_path: Path to configuration file
            plugins_dir: Directory containing plugins
            foreground_mode: Whether to run in foreground mode (disables IPC)
            app_name: Application name for IPC
        """
        self.config_path = config_path
        self.plugins_dir = plugins_dir
        self.foreground_mode = foreground_mode
        self.app_name = app_name
        self.container = DIContainer()
        self._initialized = False

    def bootstrap(self) -> DIContainer:
        """Execute the complete bootstrap process.

        Returns:
            The initialized DI container with all services

        Raises:
            RuntimeError: If bootstrap fails
        """
        if self._initialized:
            logger.warning("Bootstrap already completed")
            return self.container

        try:
            logger.info("Starting service bootstrap process")

            # Phase 1: Core services
            self._bootstrap_core_services()

            # Phase 2: Infrastructure services
            self._bootstrap_infrastructure_services()

            # Phase 3: Business services
            self._bootstrap_business_services()

            # Phase 4: Start background processes
            self._start_background_processes()

            self._initialized = True
            logger.info("Service bootstrap completed successfully")
            return self.container

        except Exception as e:
            logger.error(f"Bootstrap failed: {e}")
            self._cleanup_on_failure()
            raise RuntimeError(f"Service bootstrap failed: {e}") from e

    def _bootstrap_core_services(self) -> None:
        """Phase 1: Initialize core services (configuration)."""
        logger.info("Phase 1: Initializing core services")

        try:
            # Initialize config manager
            services.config_manager = ConfigManager(self.config_path)
            services.config = services.config_manager.get()

            # Register config service in DI container (reuse the same ConfigManager)
            config_service = ConfigService(services.config_manager)
            self.container.register(ConfigService, config_service)

            logger.info("Core services initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize core services: {e}")
            raise

    def _bootstrap_infrastructure_services(self) -> None:
        """Phase 2: Initialize infrastructure services (IPC, theme)."""
        logger.info("Phase 2: Initializing infrastructure services")

        try:
            # Initialize CSS manager for theming
            services.css_manager = CssManager()

            # Register theme service in DI container
            theme_service = ThemeService()
            self.container.register(ThemeService, theme_service)

            # Initialize IPC manager (only if not in foreground mode)
            if not self.foreground_mode:
                services.ipc_manager = IPCManager(self.app_name)

                # Register IPC service in DI container
                ipc_service = IPCService(self.app_name)
                self.container.register(IPCService, ipc_service)

                logger.info("IPC service initialized")
            else:
                logger.info("IPC service skipped (foreground mode)")

            # Load initial theme
            theme_name = getattr(services.config.system, "theme", "default")
            services.css_manager.load_all_styles(
                theme_name, None
            )  # Plugins not loaded yet

            logger.info("Infrastructure services initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize infrastructure services: {e}")
            raise

    def _bootstrap_business_services(self) -> None:
        """Phase 3: Initialize business services (plugins, history)."""
        logger.info("Phase 3: Initializing business services")

        try:
            # Initialize history manager (depends on config)
            services.history_manager = HistoryManager(services.config)

            # Load history
            if services.history_manager.history_file:
                services.history_manager.load_history(
                    services.history_manager.history_file
                )

            # Initialize plugin manager (depends on config)
            services.plugin_manager = PluginManager(services.config)
            user_dir = str(xdg_data_home() / "launcher" / "plugins")
            services.plugin_manager.async_load_plugins(self.plugins_dir, user_dir)
            logger.info("Business services initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize business services: {e}")
            raise

    def _start_background_processes(self) -> None:
        """Phase 4: Start background processes and services."""
        logger.info("Phase 4: Starting background processes")

        try:
            # Start IPC server if available
            if hasattr(services, "ipc_manager") and services.ipc_manager:
                if not services.ipc_manager.start_server():
                    logger.error("Failed to start IPC server")
                    # Don't raise here, as IPC failure shouldn't stop the application

            # Start plugins
            self._start_plugins()

            # Schedule background history cleanup
            if services.history_manager:
                services.history_manager.schedule_background_cleanup()

            logger.info("Background processes started successfully")

        except Exception as e:
            logger.error(f"Failed to start background processes: {e}")
            raise

    def _start_plugins(self) -> None:
        """Start all enabled plugins."""
        import threading

        def start_plugin_thread(plugin_id: str, plugin):
            """Thread function to start a single plugin."""
            try:
                plugin.start()
                logger.info(f"Started plugin: {plugin_id}")
            except Exception as e:
                logger.error(f"Error starting plugin {plugin_id}: {e}")

        if not services.plugin_manager or not services.plugin_manager.plugins:
            logger.warning("No plugin manager or plugins available")
            return

        threads = []
        for plugin_id, plugin in services.plugin_manager.plugins.items():
            thread = threading.Thread(
                target=start_plugin_thread, args=(plugin_id, plugin)
            )
            thread.daemon = True
            thread.start()
            threads.append(thread)

        logger.info("All enabled plugins started")

    def _cleanup_services(self) -> None:
        """Clean up all major services in reverse dependency order."""
        logger.info("Cleaning up services")
        try:
            # Clean up history manager
            if hasattr(services, "history_manager") and services.history_manager:
                services.history_manager.cleanup()

            # Clean up plugin manager
            if hasattr(services, "plugin_manager") and services.plugin_manager:
                services.plugin_manager.cleanup()

            # Clean up IPC manager
            if hasattr(services, "ipc_manager") and services.ipc_manager:
                services.ipc_manager.stop_server()

            # Clean up CSS manager
            if hasattr(services, "css_manager") and services.css_manager:
                services.css_manager.cleanup()

            logger.info("All services cleaned up")
        except Exception as e:
            logger.error(f"Error during service cleanup: {e}")

    def _cleanup_on_failure(self) -> None:
        """Clean up partially initialized services on bootstrap failure."""
        self._cleanup_services()

    def get_container(self) -> DIContainer:
        """Get the DI container. Bootstrap must be called first.

        Returns:
            The initialized DI container

        Raises:
            RuntimeError: If bootstrap hasn't been completed
        """
        if not self._initialized:
            raise RuntimeError("Bootstrap must be completed before accessing container")
        return self.container

    def shutdown(self) -> None:
        """Shutdown all services in reverse dependency order."""
        logger.info("Shutting down services")
        self._cleanup_services()
