import sys

#############################################################################
# Immediate singleton & command forwarding
#############################################################################

args = len(sys.argv)
if args == 1 or (args == 3 and sys.argv[1] == "--theme"):
    from launcher.core.ipc import IPCManager

    if len(sys.argv) == 1:
        command = "SHOW"

    elif sys.argv[1] == "--theme":
        theme_name = sys.argv[2]
        command = f"THEME {theme_name}"

    try:
        if IPCManager.send_command("launcher", command):
            print(f"Command '{command}' sent to running instance. Exiting.")
            exit(0)
    except (ImportError, IndexError, ValueError):
        pass

#############################################################################
# Main Application Code
#############################################################################

import argparse
import logging
import os
import signal

from launcher import services

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)


class ErrorLineFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.ERROR:
            self._style._fmt = "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
        else:
            self._style._fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        return super().format(record)


handler = logging.StreamHandler()
handler.setFormatter(ErrorLineFormatter())
logging.basicConfig(
    level=logging.INFO,
    handlers=[handler],
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

    if services.ipc_manager:
        services.ipc_manager.stop_server()


def show_window(args):
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
    parser.add_argument(
        "--theme",
        help="Switch theme of running launcher instance",
        nargs="?",
        const="",
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

    elif args.theme is not None:
        from launcher.ui.css_manager import CssManager

        css_manager = CssManager()
        available_themes = css_manager.get_available_themes()
        print("Available themes:")
        print("\n".join(available_themes))
        exit(0)

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Start up the launcher
    from launcher.core.config import ConfigManager
    from launcher.ui import idle_add, process_pending_events, run_main_loop
    from launcher.ui.launcher_window import LauncherWindow

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
    from launcher.core.history_manager import HistoryManager
    from launcher.core.ipc import IPCManager
    from launcher.core.plugin_manager import PluginManager
    from launcher.ui.css_manager import CssManager

    global services
    services.history_manager = HistoryManager(services.config)
    services.plugin_manager = PluginManager(services.config)
    services.plugin_manager.load_plugins(plugins_dir)

    # Initialize CSS manager with current theme
    services.css_manager = CssManager()
    theme_name = getattr(services.config.system, "theme", "default")
    services.css_manager.load_all_styles(theme_name, services.plugin_manager.plugins)

    # Set up and start the IPC server for the primary instance
    if not args.foreground:
        services.ipc_manager = IPCManager("launcher")
        services.ipc_manager.register_handler("SHOW", show_window)
        services.ipc_manager.register_handler("THEME", handle_theme_command)
        if not services.ipc_manager.start_server():
            logger.error(
                "Failed to start IPC server. Singleton and IPC will be disabled."
            )

    services.launcher_window.start()
    start_plugins(services.plugin_manager)

    # Schedule background history cleanup after all services are initialized
    services.history_manager.schedule_background_cleanup()

    logger.info("Background initialization completed")
    return False  # Remove from idle queue


def handle_theme_command(theme_name: str):
    """Handle theme switching command from IPC

    Args:
        theme_name: Name of the theme to switch to
    """
    global services

    try:
        if services.css_manager and services.plugin_manager:
            plugins = getattr(services.plugin_manager, "plugins", None)
            if services.css_manager.load_all_styles(theme_name, plugins):
                if services.config_manager:
                    services.config_manager.update_config("system.theme", theme_name)
                logger.info(f"Theme switched to '{theme_name}' via IPC")
            else:
                logger.error(f"Failed to switch to theme: {theme_name}")
        else:
            logger.error("CSS manager or plugin manager not available")
    except Exception as e:
        logger.error(f"Error handling theme command '{theme_name}': {e}")


def start_plugins(plugin_manager) -> bool:
    """Initialize all enabled plugins"""
    import threading

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
