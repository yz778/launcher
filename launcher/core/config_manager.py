#!/usr/bin/env python3

from typing import Dict, Any, Optional
from xdg_base_dirs import xdg_cache_home, xdg_config_home, xdg_state_home
import logging
import os
import json

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manager for loading and managing configuration"""

    # Global defaults for the launcher itself
    defaults = {
        "max_results": 15,
        "icon_size": 48,
        "terminal_command": "footclient",
        "window_width": 600,
        "window_height": 300,
        "window_height_results": 300,
        "item_height": 50,
        "border_width": 10,
        "padding": 20,
        "history_file": str(xdg_state_home() / "launcher/history.json"),
        "css_file": str(xdg_config_home() / "launcher/launcher.css"),
        "cache_dir": str(xdg_cache_home() / "launcher"),
        "window_position_vertical_percent": 25,
        "window_position_force_center": True,
        "window_position_debug": False,
    }

    def __init__(self):
        self.user_config: Dict[str, Any] = {}
        self.config_file: Optional[str] = None
        self.plugin_defaults: Dict[str, Dict[str, Any]] = {}

    def load_user_config(self, config_file: Optional[str] = None) -> None:
        """Load user configuration from file"""
        if not config_file:
            self.user_config = {}
            return

        expanded_path = os.path.expanduser(config_file)
        if not os.path.isfile(expanded_path):
            logger.info("No user configuration file found, using defaults")
            self.user_config = {}
            return

        try:
            with open(expanded_path, "r") as f:
                self.user_config = json.load(f) or {}
            logger.info(f"Loaded user configuration from {expanded_path}")
        except Exception as e:
            logger.error(f"Error loading configuration from {expanded_path}: {e}")
            self.user_config = {}

        self.config_file = expanded_path

    def get_general_config(self) -> Dict[str, Any]:
        """Get the general launcher configuration (defaults + user overrides)"""
        config = self.defaults.copy()
        user_general = self.user_config.get("general", {})
        config.update(user_general)
        return config

    def get_plugin_config(
        self, plugin_id: str, plugin_defaults: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get merged configuration for a plugin (plugin defaults + user overrides)

        Args:
            plugin_id: ID of the plugin
            plugin_defaults: Default configuration dictionary for the plugin

        Returns:
            Merged configuration dictionary
        """
        config = plugin_defaults.copy()
        user_plugin_config = self.user_config.get("plugins", {}).get(plugin_id, {})
        config.update(user_plugin_config)
        return config

    def get_cache_dir(self) -> str:
        """Get the cache directory, creating it if it doesn't exist"""
        cache_dir = self.get_general_config()["cache_dir"]
        cache_dir = os.path.expanduser(cache_dir)
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    def register_plugin_defaults(
        self, plugin_id: str, defaults: Dict[str, Any]
    ) -> None:
        """Register plugin defaults for template generation"""
        self.plugin_defaults[plugin_id] = defaults

    def build_default_config(self) -> Dict[str, Any]:
        """Build complete default config structure for template generation"""
        default_config = {
            "general": self.defaults.copy(),
            "plugins": {},
        }

        for plugin_id, plugin_defaults in self.plugin_defaults.items():
            default_config["plugins"][plugin_id] = {"enabled": True}
            for key, value in plugin_defaults.items():
                default_config["plugins"][plugin_id][key] = value

        return default_config

    def get_config(self, config_file: Optional[str] = None) -> Dict[str, Any]:
        """Load config and return complete structure (used by main app and template generation)"""
        self.load_user_config(config_file)
        config = self.build_default_config()
        if self.user_config:
            self._merge_config(config, self.user_config)

        return config

    def _merge_config(self, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        """Recursively merge override configuration into base configuration"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
