#!/usr/bin/env python3

import os
import yaml
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manager for loading and managing configuration"""

    __slots__ = ("config", "config_file", "plugin_defaults")

    DEFAULT_CONFIG = {
        "max_results": 15,
        "icon_size": 48,
        "terminal_command": "term",
        "window_width": 600,
        "window_height": 70,
        "window_height_results": 300,
        "item_height": 50,
        "border_width": 10,
        "padding": 20,
        "history_file": "~/.local/share/launcher/history.json",
        "css_file": "~/.config/launcher/launcher.css",
    }

    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.config_file: Optional[str] = None
        self.plugin_defaults: Dict[str, Dict[str, Any]] = {}

    def register_plugin_defaults(
        self, plugin_id: str, defaults: Dict[str, Any]
    ) -> None:
        """
        Register default configuration for a plugin

        Args:
            plugin_id: ID of the plugin
            defaults: Default configuration for the plugin
        """
        self.plugin_defaults[plugin_id] = defaults
        logger.debug(f"Registered default configuration for plugin {plugin_id}")

    def build_default_config(self) -> Dict[str, Any]:
        """
        Build the default configuration using registered plugin defaults

        Returns:
            Default configuration
        """
        default_config = {
            "general": self.DEFAULT_CONFIG.copy(),
            "plugins": {},
        }

        for plugin_id, plugin_defaults in self.plugin_defaults.items():
            default_config["plugins"][plugin_id] = {"enabled": True}

            for key, value in plugin_defaults.items():
                default_config["plugins"][plugin_id][key] = value

        return default_config

    def get_config(self, config_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Get the full configuration including plugin defaults and user overrides
        Always stores the configuration in the instance

        Args:
            config_file: Path to configuration file to load user overrides (optional)

        Returns:
            Complete configuration dictionary
        """
        config = self.build_default_config()

        if config_file:
            expanded_path = os.path.expanduser(config_file)
            if os.path.isfile(expanded_path):
                try:
                    with open(expanded_path, "r") as f:
                        user_config = yaml.safe_load(f)
                        logger.debug(f"User config loaded: {user_config}")

                    if user_config:
                        self._merge_config(config, user_config)

                    logger.info(f"Loaded user configuration from {expanded_path}")
                except Exception as e:
                    logger.error(
                        f"Error loading configuration from {expanded_path}: {e}"
                    )
            else:
                logger.debug(f"Configuration file not found: {expanded_path}")
                logger.info("Using default configuration")

            self.config_file = expanded_path

        self.config = config

        return config

    def _merge_config(self, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        """
        Recursively merge override configuration into base configuration

        Args:
            base: Base configuration to merge into
            override: Override configuration to merge from
        """
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
