import logging
import os

from gi.repository import Gio, GLib, Gtk

from launcher import services
from launcher.core.history_manager import HistoryManager
from launcher.core.ipc import IPCManager
from launcher.core.plugin_manager import PluginManager
from launcher.launcher import handle_theme_command, show_window, start_plugins
from launcher.ui.css_manager import CssManager
from launcher.ui.launcher_window import LauncherWindow

logger = logging.getLogger(__name__)


class LauncherApplication(Gtk.Application):
    """Main GTK Application class for the launcher"""

    def __init__(self, foreground_mode=False, config_path=None, plugins_dir=None):
        super().__init__(
            application_id="yz778.launcher",
        )
        self.foreground_mode = foreground_mode
        self.config_path = config_path
        self.plugins_dir = plugins_dir
        self.window = None

    def do_startup(self):
        """Initialize application-wide resources"""
        Gtk.Application.do_startup(self)

        # Initialize CSS and theme management
        self.css_manager = CssManager()

        # Initialize core services
        self._initialize_services()

        # Set up application-wide actions
        self.setup_actions()

    def _initialize_services(self):
        """Initialize core services during startup"""
        # Initialize config and services
        from launcher.core.config import ConfigManager

        services.config_manager = ConfigManager(self.config_path)
        services.config = services.config_manager.get()

        # Initialize history and plugin managers
        services.history_manager = HistoryManager(services.config)
        services.plugin_manager = PluginManager(services.config)
        services.plugin_manager.load_plugins(self.plugins_dir)

        # Load CSS with current theme
        theme_name = getattr(services.config.system, "theme", "default")
        self.css_manager.load_all_styles(theme_name, services.plugin_manager.plugins)

        # Store CSS manager globally for compatibility
        services.css_manager = self.css_manager

        # Initialize IPC if not in foreground mode
        if not self.foreground_mode:
            services.ipc_manager = IPCManager("launcher")
            services.ipc_manager.register_handler("SHOW", self._ipc_show_window)
            services.ipc_manager.register_handler("THEME", self._ipc_handle_theme)
            if not services.ipc_manager.start_server():
                logger.error(
                    "Failed to start IPC server. Singleton and IPC will be disabled."
                )

        # Start plugins
        from launcher.launcher import start_plugins

        start_plugins(services.plugin_manager)

        # Schedule background history cleanup
        services.history_manager.schedule_background_cleanup()

        logger.info("Core services initialized")

    def _ipc_show_window(self, args):
        """IPC handler to show the launcher window"""
        if self.window:
            self.window.show_and_focus()

    def _ipc_handle_theme(self, theme_name: str):
        """IPC handler for theme switching"""
        available_themes = self.css_manager.get_available_themes()
        theme_names = [t["name"] for t in available_themes]

        if theme_name == "":
            return "\n".join(t["display_name"] for t in available_themes)

        if theme_name not in theme_names:
            return f"Theme not found: `{theme_name}`"

        success = False
        message = ""

        try:
            plugins = getattr(services.plugin_manager, "plugins", None)
            if self.css_manager.load_all_styles(theme_name, plugins):
                services.config_manager.update_config("system.theme", theme_name)
                success = True
                message = f"Theme switched to '{theme_name}' via IPC"
            else:
                message = f"Failed to switch to theme: {theme_name}"
        except Exception as e:
            message = f"Error handling theme command '{theme_name}': {e}"

        if success:
            logger.info(message)
        else:
            logger.error(message)

        return message

    def do_activate(self):
        """Handle application activation"""
        if not self.window:
            self.window = LauncherWindow(
                application=self, foreground_mode=self.foreground_mode
            )
            self.add_window(self.window)
            services.launcher_window = self.window  # Set global reference

        self.window.start()
        self.window.show_and_focus()

    def setup_actions(self):
        """Set up application-wide actions"""
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self.on_quit)
        self.add_action(quit_action)

    def do_shutdown(self):
        """Handle application shutdown"""
        self.shutdown_application()
        Gtk.Application.do_shutdown(self)

    def on_quit(self, action, parameter):
        """Handle quit action"""
        self.quit()

    def shutdown_application(self):
        """Clean up application resources"""
        # Clean up IPC manager
        if hasattr(services, "ipc_manager") and services.ipc_manager:
            services.ipc_manager.stop_server()

        # Clean up plugin manager
        if hasattr(services, "plugin_manager") and services.plugin_manager:
            services.plugin_manager.cleanup()

        # Clean up history manager
        if hasattr(services, "history_manager") and services.history_manager:
            services.history_manager.cleanup()

        # Clean up CSS manager
        if hasattr(self, "css_manager"):
            self.css_manager.cleanup()

        logger.info("Application resources cleaned up")
