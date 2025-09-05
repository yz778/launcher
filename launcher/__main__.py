#!/usr/bin/env python3

from .singleton import SingletonManager
from .utils.config_utils import arg_parser
import services
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


def shutdown(reason: str = ""):
    global services

    if reason:
        logger.info(f"Quit requested: {reason}")
    else:
        logger.info("Quit requested")

    if services.launcher_window:
        services.launcher_window.shutdown()

    if services.plugin_manager:
        services.plugin_manager.cleanup()

    if services.history_manager:
        services.history_manager.cleanup()

    if services.singleton_manager:
        services.singleton_manager.stop_server()


def show_window():
    """Callback to show the launcher window"""
    global services
    if services.launcher_window:
        services.launcher_window.show_and_focus()


def signal_handler(signum, frame):
    """Handle termination signals"""
    shutdown(reason=f"signal {signum}")


def main() -> int:
    """Run the launcher application"""
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
        services.singleton_manager = SingletonManager("launcher")

        if services.singleton_manager.is_running():
            logger.info("Another instance is already running, sending show command...")
            if services.singleton_manager.send_show_command():
                return 0
            else:
                logger.warning(
                    "Failed to communicate with existing instance, starting new one..."
                )

        if not services.singleton_manager.start_server(show_window):
            logger.error("Failed to start singleton server")
            return 1
    else:
        logger.info("Running in foreground mode (singleton disabled)")

    # Start up the launcher
    from .core.config_manager import ConfigManager
    from .ui.launcher_window import LauncherWindow
    from .ui import run_main_loop, process_pending_events, idle_add

    services.config_manager = ConfigManager()
    services.config = services.config_manager.get_config(args.config)

    try:
        services.launcher_window = LauncherWindow(foreground_mode=args.foreground)
        services.launcher_window.show_and_focus()
        process_pending_events()
        plugins_dir = os.path.join(current_dir, "plugins")
        idle_add(lambda: complete_initialization(plugins_dir, args))
        run_main_loop()

    finally:
        shutdown()

    return 0


def complete_initialization(
    plugins_dir: str,
    args,
) -> bool:
    """Finish async initialization tasks after UI is visible"""

    # Lazy import heavy modules
    from .ui.css_manager import CssManager
    from .core.plugin_manager import PluginManager
    from .core.history_manager import HistoryManager

    global services
    services.history_manager = HistoryManager(services.config)
    services.plugin_manager = PluginManager(services.config_manager)
    services.plugin_manager.load_plugins(plugins_dir, services.config)

    CssManager.load_css(services.config, services.plugin_manager.plugins)
    services.launcher_window.start()
    start_plugins(services.plugin_manager)
    logger.info("Background initialization completed")
    return False  # Remove from idle queue


def start_plugins(plugin_manager) -> bool:
    """Initialize all enabled plugins"""
    import threading

    logger.info("Starting plugins in parallel...")

    def start_plugin_thread(plugin_id, plugin):
        """Thread function to start a single plugin."""
        try:
            plugin.start()
            logger.info(f"Started plugin: {plugin_id}")
        except Exception as e:
            logger.error(f"Error starting plugin {plugin_id}: {e}")

    threads = []
    for plugin_id, plugin in plugin_manager.plugins.items():
        thread = threading.Thread(target=start_plugin_thread, args=(plugin_id, plugin))
        thread.daemon = True
        thread.start()
        threads.append(thread)

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
