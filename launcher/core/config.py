import json
import logging
import os
from typing import Any, Dict, Optional

from xdg_base_dirs import xdg_cache_home, xdg_config_home, xdg_state_home

logger = logging.getLogger(__name__)


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self


class ConfigManager:
    def __init__(self, config_file: Optional[str] = None):
        self._system_defaults = {
            "max_results": 15,
            "icon_size": 48,
            "terminal_command": "foot",
            "window_width": 600,
            "window_height": 400,
            "item_height": 50,
            "border_width": 10,
            "history_file": str(xdg_state_home() / "launcher/history.json"),
            "css_file": str(xdg_config_home() / "launcher/launcher.css"),
            "cache_dir": str(xdg_cache_home() / "launcher"),
            "window_position_vertical_percent": 25,
            "window_position_force_center": True,
            "window_position_debug": False,
            "highlight_color": "#8be9fd",
            "highlight_weight": "bold",
        }
        self._plugin_defaults = {}
        self.config_file = config_file
        self._user_config = self._load_user_config(config_file)

        # 1. Start with system defaults
        config_data = {"system": self._system_defaults.copy()}

        # 2. Merge user config, which can override system defaults and provide plugin configs
        self._merge_dicts(config_data, self._user_config)

        # 3. Convert to AttrDict for attribute-style access
        self.config = self._to_attr_dict(config_data)

        # 4. Expose config manager for plugin registration
        self.config._config_manager = self

    def _load_user_config(self, config_file: Optional[str] = None) -> Dict:
        if not config_file:
            return {}

        expanded_path = os.path.expanduser(config_file)
        if not os.path.exists(expanded_path):
            logger.info("No user configuration file found, using defaults")
            return {}

        try:
            with open(expanded_path, "r") as f:
                user_config = json.load(f)
            logger.info(f"Loaded user configuration from {expanded_path}")
            return user_config
        except Exception as e:
            logger.error(f"Error loading configuration from {expanded_path}: {e}")
            return {}

    def register_plugin_defaults(self, plugin_id: str, defaults: Dict[str, Any]):
        self._plugin_defaults[plugin_id] = defaults

        # Merge plugin defaults into the config, without overwriting existing values (from user config)
        plugin_config = self._to_attr_dict({plugin_id: defaults})
        self._merge_defaults(self.config, plugin_config)

    def _merge_defaults(self, base, defaults):
        for key, value in defaults.items():
            if key not in base:
                base[key] = value
            elif isinstance(value, AttrDict) and isinstance(base.get(key), AttrDict):
                self._merge_defaults(base[key], value)

    def _merge_dicts(self, base, override):
        for key, value in override.items():
            if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                self._merge_dicts(base[key], value)
            else:
                base[key] = value

    def _to_attr_dict(self, d):
        if isinstance(d, dict):
            return AttrDict({k: self._to_attr_dict(v) for k, v in d.items()})
        return d

    def get(self):
        return self.config

    def create_default_config(self, config_file: Optional[str] = None):
        """Create a default configuration file with all registered plugin defaults"""
        if not config_file:
            config_file = self.config_file

        if not config_file:
            logger.error("No config file path provided")
            return False

        expanded_path = os.path.expanduser(config_file)

        # Build default config structure
        default_config = {
            "system": self._system_defaults.copy(),
        }

        # Add plugin defaults
        for plugin_id, plugin_defaults in self._plugin_defaults.items():
            default_config[plugin_id] = plugin_defaults.copy()

        try:
            os.makedirs(os.path.dirname(expanded_path), exist_ok=True)
            with open(expanded_path, "w") as f:
                json.dump(default_config, f, indent=2, sort_keys=True)
            logger.info(f"Created default configuration file: {expanded_path}")
            return True
        except Exception as e:
            logger.error(f"Error creating default configuration file: {e}")
            return False

    def get_cache_dir(self) -> str:
        """Get the cache directory, creating it if it doesn't exist"""
        cache_dir = os.path.expanduser(self.config.system.cache_dir)
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir
