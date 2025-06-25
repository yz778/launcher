#!/usr/bin/env python3

import os
import sys

os.environ["GDK_BACKEND"] = "x11"
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Only import absolutely essential modules at startup
import logging
import signal
from .singleton import SingletonManager
from .utils.config_utils import arg_parser

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


def rescan_callback(plugin_id: str = None):
    """Callback to handle rescan commands"""
    global launcher_window
    if launcher_window and launcher_window.plugin_manager:
        if plugin_id:
            # Rescan specific plugin
            plugin = launcher_window.plugin_manager.plugins.get(plugin_id)
            if plugin and hasattr(plugin, "rescan"):
                logger.info(f"Rescanning {plugin_id} plugin via IPC")
                plugin.rescan()
            else:
                logger.warning(
                    f"Plugin {plugin_id} not found or doesn't support rescanning"
                )
        else:
            # Rescan all plugins
            logger.info("Rescanning all plugins via IPC")
            launcher_window._trigger_rescan()


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


def signal_handler(signum, frame):
    """Handle termination signals"""
    global singleton_manager
    logger.info(f"Received signal {signum}, shutting down...")
    if singleton_manager:
        singleton_manager.stop_server()
    try:
        # Lazy import Gtk only if needed
        from gi.repository import Gtk

        Gtk.main_quit()
    except ImportError:
        pass  # Gtk not loaded yet
    except:
        pass  # Gtk might not be running
    sys.exit(0)


def main() -> None:
    """Run the launcher application"""
    global singleton_manager, launcher_window

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
            sys.exit(1)
        sys.exit(0)

    if args.create_css:
        from .utils.config_utils import create_default_css_file
        from .core.config_manager import ConfigManager

        config_manager = ConfigManager()
        plugins_dir = os.path.join(current_dir, "plugins")

        if not create_default_css_file(config_manager, plugins_dir):
            sys.exit(1)
        sys.exit(0)

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Skip singleton behavior if running in foreground mode
    if not args.foreground:
        logger.info("Running in singleton mode")

        # Initialize singleton manager
        singleton_manager = SingletonManager("launcher")

        # Handle rescan commands
        if args.rescan or args.rescan_plugin:
            if singleton_manager.is_running():
                if args.rescan:
                    logger.info("Sending rescan command to running instance...")
                    if singleton_manager.send_rescan_command():
                        logger.info("Successfully triggered rescan")
                        return
                elif args.rescan_plugin:
                    logger.info(
                        f"Sending rescan command for {args.rescan_plugin} to running instance..."
                    )
                    if singleton_manager.send_rescan_command(args.rescan_plugin):
                        logger.info(
                            f"Successfully triggered rescan for {args.rescan_plugin}"
                        )
                        return
                logger.error("Failed to send rescan command")
                sys.exit(1)
            else:
                logger.error("No running instance found to rescan")
                sys.exit(1)

        # Check if another instance is already running
        if singleton_manager.is_running():
            logger.info("Another instance is already running, sending show command...")
            if singleton_manager.send_show_command():
                logger.info("Successfully showed existing instance")
                return  # Fast exit path - no heavy imports needed!
            else:
                logger.warning(
                    "Failed to communicate with existing instance, starting new one..."
                )

        # Start singleton server for this instance
        if not singleton_manager.start_server(show_window, rescan_callback):
            logger.error("Failed to start singleton server")
            sys.exit(1)
    else:
        logger.info("Running in foreground mode (singleton disabled)")

        # In foreground mode, rescan commands should just exit with error
        if args.rescan or args.rescan_plugin:
            logger.error("Rescan commands not supported in foreground mode")
            sys.exit(1)

    # Only import heavy modules when we actually need to start the GUI
    logger.debug("Loading GUI modules...")
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
        launcher_window.show_all()
        launcher_window.scrolled.hide()
        launcher_window.resize(
            config["general"]["window_width"],
            config["general"]["window_height"],
        )

        while Gtk.events_pending():
            Gtk.main_iteration()

        GLib.idle_add(
            lambda: complete_initialization(
                launcher_window, config_manager, plugins_dir, args
            )
        )
        Gtk.main()

    except Exception as e:
        logger.error(f"Error starting GUI: {e}")
        if singleton_manager:
            singleton_manager.stop_server()
        raise
    finally:
        # Always clean up singleton server on exit
        if singleton_manager:
            singleton_manager.stop_server()

        # Clean up plugin manager resources
        if launcher_window and launcher_window.plugin_manager:
            launcher_window.plugin_manager.cleanup()


def complete_initialization(
    win,  # Don't need type hints for better import speed
    config_manager,
    plugins_dir: str,
    args,
) -> bool:
    """Finish async initialization tasks after UI is visible"""

    # Lazy import heavy modules
    from .ui.css_manager import CssManager
    from .core.plugin_manager import PluginManager
    from .core.history_manager import HistoryManager

    # Load the full configuration
    config = config_manager.get_config(args.config)

    # Initialize plugin manager and load plugins
    plugin_manager = PluginManager(config_manager)
    plugin_manager.load_plugins(plugins_dir, config)

    # Load CSS
    CssManager.load_css(config, plugin_manager.plugins)

    # Initialize history manager
    history_manager = HistoryManager(config)

    # Update the window with the full configuration and managers
    win.update_with_full_config(plugin_manager, history_manager, config)

    # Start plugins in the background
    from gi.repository import GLib

    GLib.idle_add(lambda: start_plugins(plugin_manager))

    logger.info("Background initialization completed")
    return False  # Remove from idle queue


def start_plugins(plugin_manager: "PluginManager") -> bool:
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
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
        sys.exit(1)
