import logging

from gi.repository import Gio, Gtk

from launcher import services
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

        # Services are already initialized by Bootstrapper
        # Just ensure CSS manager is available
        if not hasattr(services, "css_manager") or not services.css_manager:
            logger.warning("CSS manager not available, creating fallback")
            from launcher.ui.css_manager import CssManager

            services.css_manager = CssManager()

        # Set up application-wide actions
        self.setup_actions()

    def _ipc_show_window(self, args):
        """IPC handler to show the launcher window"""
        if self.window:
            self.window.show_and_focus()

    def _ipc_handle_theme(self, theme_name: str):
        """IPC handler for theme switching"""
        available_themes = services.css_manager.get_available_themes()
        theme_names = [t["name"] for t in available_themes]

        if theme_name == "":
            return "\n".join(t["display_name"] for t in available_themes)

        if theme_name not in theme_names:
            return f"Theme not found: `{theme_name}`"

        success = False
        message = ""

        try:
            plugins = getattr(services.plugin_manager, "plugins", None)
            if services.css_manager.load_all_styles(theme_name, plugins):
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

        self.window.show_and_focus()
        self.window.start()

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
        # Use the centralized cleanup logic from Bootstrapper
        from launcher.core.bootstrap import Bootstrapper

        Bootstrapper()._cleanup_services()
        logger.info("Application resources cleaned up")
