from launcher import services
from launcher.singleton import SingletonManager
import argparse
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


def arg_parser():
    parser = argparse.ArgumentParser(description="Launcher with plugins")

    parser.add_argument(
        "--config",
        "-c",
        help="Path to configuration file",
        default="~/.config/launcher/config.json",
    )
    parser.add_argument(
        "--create-config",
        help="Create a default configuration file if it doesn't exist",
        action="store_true",
    )
    parser.add_argument(
        "--debug",
        "-d",
        help="Enable debug logging",
        action="store_true",
    )
    parser.add_argument(
        "--foreground",
        "-f",
        help="Run in foreground mode (disable singleton behavior)",
        action="store_true",
    )
    return parser.parse_args()


def main() -> int:
    """Run the launcher application"""
    os.chdir(os.path.expanduser("~"))  # Change to home directory at startup

    args = arg_parser()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.create_config:
        from launcher.core.config import ConfigManager
        from launcher.core.plugin_manager import PluginManager

        config_manager = ConfigManager(args.config)
        plugins_dir = os.path.join(current_dir, "plugins")

        # Load plugins to register their defaults
        plugin_manager = PluginManager(config_manager.get())
        plugin_manager.load_plugins(plugins_dir)

        if not config_manager.create_default_config(args.config):
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
    from launcher.core.config import ConfigManager
    from launcher.ui.launcher_window import LauncherWindow
    from launcher.ui import run_main_loop, process_pending_events, idle_add

    services.config_manager = ConfigManager(args.config)
    services.config = services.config_manager.get()

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
    from launcher.ui.css_manager import CssManager
    from launcher.core.plugin_manager import PluginManager
    from launcher.core.history_manager import HistoryManager

    global services
    services.history_manager = HistoryManager(services.config)
    services.plugin_manager = PluginManager(services.config)
    services.plugin_manager.load_plugins(plugins_dir)

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
