#!/usr/bin/env python3

import os
import importlib
import inspect
import logging
import threading
from typing import Dict, List, Any, Type, Callable

from gi.repository import GLib
from plugins.base import Plugin, SearchResult

logger = logging.getLogger(__name__)


class PluginManager:
    """Manager for loading and managing plugins"""

    __slots__ = (
        "plugins",
        "enabled_plugins",
        "config",
        "config_manager",
        "active_search_threads",
        "active_search_threads_lock",
        "_executor",
    )

    def __init__(self, config_manager=None):
        self.plugins: Dict[str, Plugin] = {}
        self.enabled_plugins: Dict[str, bool] = {}
        self.config: Dict[str, Any] = {}
        self.config_manager = config_manager
        self.active_search_threads = 0
        self.active_search_threads_lock = threading.Lock()
        self._executor = None

    def _get_executor(self):
        """Get or create thread pool executor"""
        if self._executor is None:
            import concurrent.futures

            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=8, thread_name_prefix="plugin-search"
            )
        return self._executor

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
            logger.debug(
                f"Registering plugin '{plugin_id}'. Raw plugin_config: {plugin_config}"
            )

            enabled = plugin_config.get("enabled", True)
            logger.debug(f"Plugin '{plugin_id}' enabled flag is {enabled}.")

            if enabled:
                logger.debug(
                    f"Plugin '{plugin_id}' is enabled and will be initialized."
                )
                combined_config = config.copy()

                for key, value in plugin_defaults.items():
                    if key not in plugin_config:
                        plugin_config[key] = value

                for key, value in plugin_config.items():
                    combined_config[key] = value

                if plugin.initialize(combined_config, self.config_manager):
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
                logger.debug(
                    f"Plugin '{plugin_id}' is disabled and will NOT be added to active plugins."
                )
                self.enabled_plugins[plugin_id] = False
        except Exception as e:
            logger.error(f"Error registering plugin {plugin_class.__name__}: {e}")

    def search(
        self,
        query: str,
        search_id: int,
        result_callback: Callable[[int, str, List[SearchResult]], None],
        finished_callback: Callable[[int], None],
    ) -> None:
        """
        Search across enabled plugins non-blockingly using thread pool.
        Results for each plugin are passed via result_callback.
        finished_callback is called once all plugins have been processed.
        Callbacks are executed in the main GTK thread via GLib.idle_add.
        search_id is used to track and ignore stale results.
        """
        if not query or not query.strip():
            GLib.idle_add(finished_callback, search_id)
            return

        plugins_to_search = []
        for plugin_id, plugin_instance in self.plugins.items():
            # Ensure plugin is enabled in the current config
            plugin_config = self.config.get("plugins", {}).get(plugin_id, {})
            if plugin_config.get("enabled", True):
                plugins_to_search.append((plugin_id, plugin_instance))
            else:
                logger.info(f"Plugin {plugin_id} is disabled, skipping search.")

        if not plugins_to_search:
            GLib.idle_add(finished_callback, search_id)
            return

        with self.active_search_threads_lock:
            self.active_search_threads = len(plugins_to_search)

        def search_worker(
            s_id: int,
            p_id: str,
            p_instance: Plugin,
            p_query: str,
            res_cb: Callable[[int, str, List[SearchResult]], None],
            fin_cb: Callable[[int], None],
        ):
            try:
                plugin_results = p_instance.search(p_query)
                if plugin_results:
                    GLib.idle_add(res_cb, s_id, p_id, plugin_results)
            except Exception as e:
                logger.error(
                    f"Error searching with plugin {p_id} for search_id {s_id}: {e}"
                )
            finally:
                with self.active_search_threads_lock:
                    self.active_search_threads -= 1
                    if self.active_search_threads == 0:
                        GLib.idle_add(fin_cb, s_id)

        executor = self._get_executor()
        for plugin_id, plugin_instance in plugins_to_search:
            executor.submit(
                search_worker,
                search_id,
                plugin_id,
                plugin_instance,
                query,
                result_callback,
                finished_callback,
            )

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
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

        for plugin_id, plugin in self.plugins.items():
            try:
                plugin.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up plugin {plugin_id}: {e}")
