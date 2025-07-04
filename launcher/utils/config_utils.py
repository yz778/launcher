import os
import logging
import yaml
import argparse
from ..core.plugin_manager import PluginManager
from ..core.config_manager import ConfigManager
from ..ui.css_manager import CssManager

logger = logging.getLogger(__name__)


def arg_parser():
    parser = argparse.ArgumentParser(description="Launcher with plugins")

    parser.add_argument(
        "--config",
        "-c",
        help="Path to configuration file",
        default="~/.config/launcher/config.yaml",
    )
    parser.add_argument(
        "--create-config",
        help="Create a default configuration file if it doesn't exist",
        action="store_true",
    )
    parser.add_argument(
        "--create-css",
        help="Create a default CSS file if it doesn't exist",
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
        "--rescan",
        help="Trigger a rescan of all plugins in running instance",
        action="store_true",
    )
    parser.add_argument(
        "--rescan-plugin",
        help="Trigger a rescan of specific plugin in running instance",
        type=str,
        metavar="PLUGIN_ID",
    )

    return parser.parse_args()


def create_default_config_file(
    config_manager: ConfigManager, plugins_dir: str, user_config_path_str: str
) -> bool:
    default_plugin_manager = PluginManager(config_manager)
    default_plugin_manager.load_plugins(plugins_dir, {})
    default_config_data = config_manager.get_config(None)

    expanded_config_path = os.path.expanduser(user_config_path_str)
    config_dir = os.path.dirname(expanded_config_path)
    base_name = os.path.basename(expanded_config_path)
    name_parts = os.path.splitext(base_name)

    default_config_filename = f"{name_parts[0]}.default{name_parts[1]}"
    default_config_filepath = os.path.join(config_dir, default_config_filename)

    try:
        os.makedirs(os.path.dirname(default_config_filepath), exist_ok=True)
        with open(default_config_filepath, "w") as f:
            yaml.dump(default_config_data, f, default_flow_style=False)
        logger.info(f"Created default configuration file: {default_config_filepath}")
        return True
    except Exception as e:
        logger.error(f"Error creating default configuration file: {e}")
        return False


def create_default_css_file(
    config_manager: ConfigManager,
    plugins_dir: str,
) -> bool:
    default_plugin_manager = PluginManager(config_manager)
    default_plugin_manager.load_plugins(plugins_dir, {})
    default_config = config_manager.get_config(None)

    general_config = default_config.get("general", {})
    css_path = os.path.expanduser(general_config.get("css_file"))
    base_name = os.path.basename(css_path)
    name_parts = os.path.splitext(base_name)
    default_name = f"{name_parts[0]}.default{name_parts[1]}"
    default_css_path = os.path.join(os.path.dirname(css_path), default_name)

    css_content = CssManager.get_css(default_plugin_manager.plugins)

    try:
        os.makedirs(os.path.dirname(default_css_path), exist_ok=True)
        with open(default_css_path, "w") as f:
            f.write(css_content)
        logger.info(f"Created default CSS file with plugin styles: {default_css_path}")
        return True
    except Exception as e:
        logger.error(f"Error creating default CSS file: {e}")
        return False
