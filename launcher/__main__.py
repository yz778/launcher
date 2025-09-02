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

# Shutdown coordination
_quit_requested = False


def request_app_quit(reason: str = ""):
    """Request a graceful application shutdown in a centralized, idempotent way.

    This will:
    - Log the quit request once
    - Set a flag so the Gtk main loop exit can be scheduled by the launcher window
    - Avoid duplicate cleanup calls
    """

    global _quit_requested

    if _quit_requested:
        return

    _quit_requested = True

    if reason:
        logger.info(f"Quit requested: {reason}")
    else:
        logger.info("Quit requested")

    try:
        global launcher_window
        if launcher_window and hasattr(launcher_window, "request_quit"):
            launcher_window.request_quit(reason)
    except Exception as e:
        logger.debug(f"Launcher window quit request failed: {e}")


def show_window():
    """Callback to show the launcher window"""
    global launcher_window
    if launcher_window:
        launcher_window.show_and_focus()


def cleanup_resources():
    """Clean up all resources including process manager, singleton, and plugin managers"""
    global singleton_manager, launcher_window, _history_manager

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
    request_app_quit(reason=f"signal {signum}")


def main() -> None:
    """Run the launcher application"""
    global singleton_manager, launcher_window

    os.chdir(os.path.expanduser("~"))  # Change to home directory at startup

    args = arg_parser()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

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

    if not args.foreground:
        logger.info("Running in singleton mode")
        singleton_manager = SingletonManager("launcher")

        if singleton_manager.is_running():
            logger.info("Another instance is already running, sending show command...")
            if singleton_manager.send_show_command():
                return
            else:
                logger.warning(
                    "Failed to communicate with existing instance, starting new one..."
                )

        if not singleton_manager.start_server(show_window):
            logger.error("Failed to start singleton server")
            return 1
    else:
        logger.info("Running in foreground mode (singleton disabled)")

    # Only import heavy modules when we actually need to start the GUI
    from .core.config_manager import ConfigManager
    from .ui.launcher_window import LauncherWindow
    from .ui import run_main_loop, process_pending_events, idle_add

    config_manager = ConfigManager()
    plugins_dir = os.path.join(current_dir, "plugins")
    config = {"general": config_manager.DEFAULT_CONFIG.copy()}

    try:
        launcher_window = LauncherWindow(
            None, None, config, foreground_mode=args.foreground
        )

        launcher_window.show_and_focus()
        process_pending_events()
        idle_add(
            lambda: complete_initialization(
                launcher_window, config_manager, plugins_dir, args
            )
        )

        if _quit_requested:
            return 0

        run_main_loop()

    finally:
        cleanup_resources()

    return 0


def complete_initialization(
    win,
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
