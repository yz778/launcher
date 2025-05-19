#!/usr/bin/env python3

import os
import importlib
import inspect
import logging
from typing import Dict, List, Any, Type

from plugins.base import Plugin, SearchResult

logger = logging.getLogger(__name__)


class PluginManager:
    """Manager for loading and managing plugins"""

    def __init__(self, config_manager=None):
        self.plugins: Dict[str, Plugin] = {}
        self.enabled_plugins: Dict[str, bool] = {}
        self.config: Dict[str, Any] = {}
        self.config_manager = config_manager

    def load_plugins(self, plugins_dir: str, config: Dict[str, Any]) -> None:
        """Discover and load all plugins from the specified directory"""
        self.config = config

        plugin_files = [
            f[:-3]
            for f in os.listdir(plugins_dir)
            if f.endswith(".py") and f != "__init__.py" and f != "base.py"
        ]

        for plugin_file in plugin_files:
            try:
                module_name = f"plugins.{plugin_file}"
                module = importlib.import_module(module_name)
                for name, obj in inspect.getmembers(module):
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, Plugin)
                        and obj != Plugin
                        and not inspect.isabstract(obj)
                    ):
                        self._register_plugin(obj, config)
            except Exception as e:
                logger.error(f"Error loading plugin {plugin_file}: {e}")

    def _register_plugin(
        self, plugin_class: Type[Plugin], config: Dict[str, Any]
    ) -> None:
        """Register and initialize a single plugin"""
        try:
            plugin = plugin_class()
            plugin_id = plugin.get_id()

            try:
                plugin_defaults = plugin.get_config_defaults()

                if self.config_manager:
                    self.config_manager.register_plugin_defaults(
                        plugin_id, plugin_defaults
                    )
            except Exception as e:
                logger.error(
                    f"Error getting config defaults for plugin {plugin_id}: {e}"
                )
                plugin_defaults = {}

            plugin_config = config.get("plugins", {}).get(plugin_id, {})

            enabled = plugin_config.get("enabled", True)

            if enabled:
                combined_config = config.copy()

                for key, value in plugin_defaults.items():
                    if key not in plugin_config:
                        plugin_config[key] = value

                for key, value in plugin_config.items():
                    combined_config[key] = value

                if plugin.initialize(combined_config):
                    self.plugins[plugin_id] = plugin
                    self.enabled_plugins[plugin_id] = True
                    logger.info(
                        f"Initialized plugin: {plugin.get_name()} ({plugin_id})"
                    )
                else:
                    logger.warning(
                        f"Failed to initialize plugin: {plugin.get_name()} ({plugin_id})"
                    )
            else:
                logger.info(f"Plugin disabled: {plugin.get_name()} ({plugin_id})")
                self.enabled_plugins[plugin_id] = False
        except Exception as e:
            logger.error(f"Error registering plugin {plugin_class.__name__}: {e}")

    def search(self, query: str) -> List[SearchResult]:
        """Search across all enabled plugins and return sorted results"""
        if not query or not query.strip():
            return []

        results = []

        for plugin_id, plugin in self.plugins.items():
            if self.enabled_plugins.get(plugin_id, False):
                try:
                    plugin_results = plugin.search(query)
                    results.extend(plugin_results)
                except Exception as e:
                    logger.error(f"Error searching with plugin {plugin_id}: {e}")

        results.sort(key=lambda r: r.score, reverse=True)

        max_results = self.config.get("general", {}).get("max_results")
        return results[:max_results]

    def execute(self, result: SearchResult) -> bool:
        """Execute an action for the given search result"""
        plugin_id = result.plugin_id

        if plugin_id in self.plugins and self.enabled_plugins.get(plugin_id, False):
            try:
                return self.plugins[plugin_id].execute(result)
            except Exception as e:
                logger.error(f"Error executing result with plugin {plugin_id}: {e}")
                return False
        else:
            logger.error(f"Plugin {plugin_id} not found or not enabled")
            return False

        return True

    def cleanup(self) -> None:
        """Release all plugin resources"""
        for plugin_id, plugin in self.plugins.items():
            try:
                plugin.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up plugin {plugin_id}: {e}")
