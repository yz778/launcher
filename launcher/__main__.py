#!/usr/bin/env python3

from .singleton import SingletonManager
from .utils.config_utils import arg_parser
import logging
import os
import signal
import sys

# add current dir to path to load modules
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

# Global variables for singleton behavior
singleton_manager = None
launcher_window = None

# Global references for plugins to access
_history_manager = None
_plugin_manager = None


def get_history_manager():
    """Get the global history manager instance"""
    return _history_manager


def get_plugin_manager():
    """Get the global plugin manager instance"""
    return _plugin_manager


def rescan_callback(plugin_id: str = None):
    """Callback to handle rescan commands"""
    global launcher_window
    if launcher_window and launcher_window.plugin_manager:
        if plugin_id:
            logger.info(f"Reloading {plugin_id} plugin via IPC")
            launcher_window.plugin_manager.reload_plugin(plugin_id)
        else:
            logger.info("Reloading all plugins via IPC")
            launcher_window.plugin_manager.reload_all_plugins()


def show_window():
    """Callback to show the launcher window"""
    global launcher_window
    if launcher_window:
        launcher_window.show_and_focus()


def hide_window():
    """Hide the launcher window instead of quitting"""
    global launcher_window
    if launcher_window:
        launcher_window.hide()


def cleanup_resources():
    """Clean up all resources including process manager, singleton, and plugin managers"""
    global singleton_manager, launcher_window, _history_manager

    # Clean up process manager
    try:
        from .utils.process_manager import get_process_manager

        process_manager = get_process_manager()
        process_manager.cleanup_all()
    except Exception as e:
        logger.error(f"Error cleaning up process manager: {e}")

    # Always clean up singleton server
    if singleton_manager:
        singleton_manager.stop_server()

    # Clean up plugin manager resources
    if launcher_window and launcher_window.plugin_manager:
        launcher_window.plugin_manager.cleanup()

    # Clean up history manager resources
    if _history_manager:
        _history_manager.cleanup()


def signal_handler(signum, frame):
    """Handle termination signals"""
    logger.info(f"Received signal {signum}, shutting down...")

    cleanup_resources()

    try:
        # Lazy import Gtk only if needed
        from gi.repository import Gtk

        Gtk.main_quit()
    except ImportError:
        pass  # Gtk not loaded yet
    except Exception:
        pass  # Gtk might not be running
    sys.exit(0)


def main() -> None:
    """Run the launcher application"""
    global singleton_manager, launcher_window

    # Change to home directory at startup
    os.chdir(os.path.expanduser("~"))

    # Parse arguments first to check for foreground mode
    args = arg_parser()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Handle utility flags that exit immediately (lazy import)
    if args.create_config:
        from .utils.config_utils import create_default_config_file
        from .core.config_manager import ConfigManager

        config_manager = ConfigManager()
        plugins_dir = os.path.join(current_dir, "plugins")

        if not create_default_config_file(config_manager, plugins_dir, args.config):
            return 1
        return 0

    if args.create_css:
        from .utils.config_utils import create_default_css_file
        from .core.config_manager import ConfigManager

        config_manager = ConfigManager()
        plugins_dir = os.path.join(current_dir, "plugins")

        if not create_default_css_file(config_manager, plugins_dir):
            return 1
        return 0

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Skip singleton behavior if running in foreground mode
    if not args.foreground:
        logger.info("Running in singleton mode")
        singleton_manager = SingletonManager("launcher")

        # Handle rescan commands
        if args.rescan or args.rescan_plugin:
            if singleton_manager.is_running():
                logger.info("Sending rescan command to running instance...")
                if not singleton_manager.send_rescan_command(args.rescan_plugin):
                    logger.error("Failed to send rescan command")
                    return 1
            else:
                logger.error("No running instance found to rescan")
                return 1

        # Check if another instance is already running
        if singleton_manager.is_running():
            logger.info("Another instance is already running, sending show command...")
            if singleton_manager.send_show_command():
                return  # Fast exit path - no heavy imports needed!
            else:
                logger.warning(
                    "Failed to communicate with existing instance, starting new one..."
                )

        # Start singleton server for this instance
        if not singleton_manager.start_server(show_window, rescan_callback):
            logger.error("Failed to start singleton server")
            return 1
    else:
        logger.info("Running in foreground mode (singleton disabled)")

        # In foreground mode, rescan commands should just exit with error
        if args.rescan or args.rescan_plugin:
            logger.error("Rescan commands not supported in foreground mode")
            return 1

    # Only import heavy modules when we actually need to start the GUI
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib
    from .core.config_manager import ConfigManager
    from .ui.launcher_window import LauncherWindow

    config_manager = ConfigManager()
    plugins_dir = os.path.join(current_dir, "plugins")

    # Create minimal UI immediately for responsiveness
    config = {"general": config_manager.DEFAULT_CONFIG.copy()}

    try:
        launcher_window = LauncherWindow(
            None, None, config, foreground_mode=args.foreground
        )

        launcher_window.show_and_focus()

        while Gtk.events_pending():
            Gtk.main_iteration()

        GLib.idle_add(
            lambda: complete_initialization(
                launcher_window, config_manager, plugins_dir, args
            )
        )
        Gtk.main()

    finally:
        cleanup_resources()

    return 0


def complete_initialization(
    win,  # Don't need type hints for better import speed
    config_manager,
    plugins_dir: str,
    args,
) -> bool:
    """Finish async initialization tasks after UI is visible"""
    logger.info("Process manager initialized")

    # Lazy import heavy modules
    from .ui.css_manager import CssManager
    from .core.plugin_manager import PluginManager
    from .core.history_manager import HistoryManager

    config = config_manager.get_config(args.config)
    plugin_manager = PluginManager(config_manager)
    history_manager = HistoryManager(config)

    # Set global references for plugins to access
    global _history_manager, _plugin_manager
    _history_manager = history_manager
    _plugin_manager = plugin_manager

    plugin_manager.load_plugins(plugins_dir, config)

    # Set managers on history plugin if it was loaded
    if "history" in plugin_manager.plugins:
        history_plugin = plugin_manager.plugins["history"]
        history_plugin.set_managers(history_manager, plugin_manager)
        history_plugin.register_with_launcher()

    # Load CSS
    CssManager.load_css(config, plugin_manager.plugins)

    # Update the window with the full configuration and managers
    win.update_with_full_config(plugin_manager, history_manager, config)
    start_plugins(plugin_manager)
    logger.info("Background initialization completed")
    return False  # Remove from idle queue


def start_plugins(plugin_manager) -> bool:
    """Initialize all enabled plugins"""
    # Lazy import threading only when needed
    import threading

    logger.info("Starting plugins in parallel...")

    def start_plugin_thread(plugin_id, plugin):
        """Thread function to start a single plugin."""
        try:
            plugin.start()
            logger.info(f"Started plugin: {plugin_id}")
        except Exception as e:
            logger.error(f"Error starting plugin {plugin_id}: {e}")

    # Start each plugin in plugin_manager.plugins.
    threads = []
    for plugin_id, plugin in plugin_manager.plugins.items():
        if plugin_manager.enabled_plugins.get(plugin_id, True):
            thread = threading.Thread(
                target=start_plugin_thread, args=(plugin_id, plugin)
            )
            thread.daemon = True
            thread.start()
            threads.append(thread)
        else:
            logger.info(f"Plugin {plugin_id} is disabled, not starting.")

    logger.info("All enabled plugins started")
    return False


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
        sys.exit(1)
