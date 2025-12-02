#############################################################################
# Immediate singleton & command forwarding
#############################################################################
import sys

args = len(sys.argv)
if args == 1 or (args == 3 and sys.argv[1] == "--theme"):
    from launcher.core.ipc import IPCManager

    show_error = True

    if len(sys.argv) == 1:
        command = "SHOW"
        show_error = False

    elif sys.argv[1] == "--theme":
        theme_name = sys.argv[2]
        command = f"THEME {theme_name}"

    if IPCManager.send_command("launcher", command):
        print(f"Command '{command}' sent to running instance. Exiting.")
        exit(0)
    elif show_error:
        print(f"Unable to send '{command}' command. Exiting.")
        exit(1)


#############################################################################
# Main Application Code
#############################################################################
# ruff: noqa: E402
import argparse
import logging
import os
import signal
import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))


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
    from launcher import services

    if reason:
        logger.info(f"Quit requested: {reason}")
    else:
        logger.info("Quit requested")

    if services.instance.launcher_window:
        services.instance.launcher_window.shutdown()

    if services.instance.plugin_manager:
        services.instance.plugin_manager.cleanup()

    if services.instance.history_manager:
        services.instance.history_manager.cleanup()

    if services.instance.ipc_manager:
        services.instance.ipc_manager.stop_server()


def show_window(args):
    from launcher import services

    if services.instance.launcher_window:
        services.instance.launcher_window.show_and_focus()


def signal_handler(signum, frame):
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
    os.chdir(os.path.expanduser("~"))  # Change to home directory at startup

    args = arg_parser()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.create_config:
        from launcher.core.config import ConfigManager
        from launcher.core.plugin_manager import PluginManager

        config_manager = ConfigManager(args.config)
        plugins_dir = current_dir / "plugins"

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
        for theme in available_themes:
            print(theme)
        exit(0)

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    from launcher import services
    from launcher.core.config import ConfigManager
    from launcher.ui import idle_add, process_pending_events, run_main_loop
    from launcher.ui.css_manager import CssManager
    from launcher.ui.launcher_window import LauncherWindow

    # Start up the launcher
    logger.info("Loading configuration and initial CSS")
    services.instance.config_manager = ConfigManager(args.config)
    services.instance.config = services.instance.config_manager.get()
    services.instance.css_manager = CssManager()
    services.instance.css_manager.load_all_styles(
        services.instance.config.system.theme, None
    )

    try:
        services.instance.launcher_window = LauncherWindow(
            foreground_mode=args.foreground
        )
        services.instance.launcher_window.show_and_focus()
        process_pending_events()
        plugins_dir = current_dir / "plugins"
        idle_add(lambda: complete_initialization(plugins_dir, args))
        run_main_loop()

    finally:
        shutdown()

    return 0


def complete_initialization(
    plugins_dir: Path,
    args,
) -> bool:
    from launcher import services
    from launcher.core.history_manager import HistoryManager
    from launcher.core.ipc import IPCManager
    from launcher.core.plugin_manager import PluginManager

    services.instance.history_manager = HistoryManager(services.instance.config)
    services.instance.plugin_manager = PluginManager(services.instance.config)
    services.instance.plugin_manager.load_plugins(plugins_dir)
    services.instance.css_manager.load_all_styles(
        services.instance.config.system.theme, services.instance.plugin_manager.plugins
    )

    # Set up and start the IPC server for the primary instance
    if not args.foreground:
        logger.info("Loading IPC manager")
        services.instance.ipc_manager = IPCManager("launcher")
        services.instance.ipc_manager.register_handler("SHOW", show_window)
        services.instance.ipc_manager.register_handler("THEME", handle_theme_command)
        if not services.instance.ipc_manager.start_server():
            logger.error(
                "Failed to start IPC server. Singleton and IPC will be disabled."
            )

    logger.info("Starting background processes")
    services.instance.launcher_window.start()
    start_plugins(services.instance.plugin_manager)
    services.instance.history_manager.schedule_background_cleanup()

    return False  # Remove from idle queue


def handle_theme_command(theme_name: str):
    from launcher import services

    try:
        if services.instance.css_manager and services.instance.plugin_manager:
            plugins = getattr(services.instance.plugin_manager, "plugins", None)
            if services.instance.css_manager.load_all_styles(theme_name, plugins):
                if services.instance.config_manager:
                    services.instance.config_manager.update_config(
                        "system.theme", theme_name
                    )
                logger.info(f"Theme switched to '{theme_name}' via IPC")
            else:
                logger.error(f"Failed to switch to theme: {theme_name}")
        else:
            logger.error("CSS manager or plugin manager not available")
    except Exception as e:
        logger.error(f"Error handling theme command '{theme_name}': {e}")


def start_plugins(plugin_manager) -> bool:
    import threading

    def start_plugin_thread(plugin_id, plugin):
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
