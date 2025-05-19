#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

import os
import sys
import logging
import argparse

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from .core.config_manager import ConfigManager
from .core.plugin_manager import PluginManager
from .core.history_manager import HistoryManager
from .ui.launcher_window import LauncherWindow
from .utils.config_utils import arg_parser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the launcher application"""

    config_manager = ConfigManager()
    plugins_dir = os.path.join(current_dir, "plugins")

    # Parse and handle arguments
    args = arg_parser()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.create_config:
        from .utils.config_utils import create_default_config_file

        if not create_default_config_file(config_manager, plugins_dir, args.config):
            sys.exit(1)
        sys.exit(0)

    if args.create_css:
        from .utils.config_utils import create_default_css_file

        if not create_default_css_file(config_manager, plugins_dir):
            sys.exit(1)
        sys.exit(0)

    # Create minimal UI immediately for responsiveness
    config = {"general": config_manager.DEFAULT_CONFIG.copy()}
    win = LauncherWindow(None, None, config)
    win.show_all()
    win.scrolled.hide()
    win.resize(
        config["general"]["window_width"],
        config["general"]["window_height"],
    )

    while Gtk.events_pending():
        Gtk.main_iteration()

    GLib.idle_add(
        lambda: complete_initialization(win, config_manager, plugins_dir, args)
    )
    Gtk.main()


def complete_initialization(
    win: LauncherWindow,
    config_manager: ConfigManager,
    plugins_dir: str,
    args: argparse.Namespace,
) -> bool:
    """Finish async initialization tasks after UI is visible"""
    logger.info("Completing initialization in the background...")

    from .ui.css_manager import CssManager

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
    GLib.idle_add(lambda: start_plugins(plugin_manager))

    logger.info("Background initialization completed")
    return False  # Remove from idle queue


def start_plugins(plugin_manager: PluginManager) -> bool:
    """Initialize all enabled plugins"""
    logger.info("Starting plugins in parallel...")

    for plugin_id, plugin in plugin_manager.plugins.items():
        if plugin_manager.enabled_plugins.get(plugin_id, False):
            try:
                plugin.start()
            except Exception as e:
                logger.error(f"Error starting plugin {plugin_id}: {e}")

    logger.info("All plugins started")
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
