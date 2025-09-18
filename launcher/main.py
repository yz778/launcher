#############################################################################
# Immediate singleton & command forwarding
#############################################################################
import sys

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
from launcher.core.bootstrap import Bootstrapper
from launcher.ui.application import LauncherApplication
from launcher.utils.process_manager import process_manager

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


def handle_theme_command(theme_name: str):
    """Handle theme switching command from IPC

    Args:
        theme_name: Name of the theme to switch to
    """
    global services

    available_themes = services.css_manager.get_available_themes()
    theme_names = [t["name"] for t in available_themes]

    if theme_name == "":
        return "\n".join([t["display_name"] for t in available_themes])

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
    signal.signal(signal.SIGCHLD, process_manager._sigchld_handler)

    plugins_dir = os.path.join(current_dir, "plugins")

    # Initialize services using Bootstrapper
    bootstrapper = Bootstrapper(
        config_path=args.config,
        plugins_dir=plugins_dir,
        foreground_mode=args.foreground,
        app_name="launcher",
    )

    try:
        container = bootstrapper.bootstrap()
    except RuntimeError as e:
        logger.error(f"Bootstrap failed: {e}")
        return 1

    # Register IPC handlers if IPC is available
    if (
        not args.foreground
        and hasattr(services, "ipc_manager")
        and services.ipc_manager
    ):
        services.ipc_manager.register_handler("SHOW", show_window)
        services.ipc_manager.register_handler("THEME", handle_theme_command)

    # Create and run the LauncherApplication
    app = LauncherApplication(
        foreground_mode=args.foreground,
        config_path=args.config,
        plugins_dir=plugins_dir,
    )
    app.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
