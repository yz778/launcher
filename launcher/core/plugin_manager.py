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
            # Create a temporary instance just to get the plugin ID and defaults
            temp_plugin = plugin_class()
            plugin_id = temp_plugin.get_id()

            # Check if plugin is enabled before doing any real work
            plugins_config = config.get("plugins", {})
            plugin_specific_config = plugins_config.get(plugin_id, {})
            enabled = plugin_specific_config.get("enabled", True)
            
            if not enabled:
                logger.info(f"Plugin disabled: {temp_plugin.get_name()} ({plugin_id}) - skipping registration")
                return

            # Plugin is enabled, proceed with full registration
            try:
                plugin_defaults = temp_plugin.get_config_defaults()
                if self.config_manager:
                    self.config_manager.register_plugin_defaults(
                        plugin_id, plugin_defaults
                    )
            except Exception as e:
                logger.error(
                    f"Error getting config defaults for plugin {plugin_id}: {e}"
                )

            logger.debug(f"Registering enabled plugin '{plugin_id}'")

            # Initialize the plugin
            if temp_plugin.initialize(plugin_specific_config, self.config_manager):
                self.plugins[plugin_id] = temp_plugin
                self.enabled_plugins[plugin_id] = True
                logger.info(f"Initialized plugin: {temp_plugin.get_name()} ({plugin_id})")
            else:
                logger.warning(f"Failed to initialize plugin: {temp_plugin.get_name()} ({plugin_id})")

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

        # Since only enabled plugins are in self.plugins, we can search all of them
        plugins_to_search = list(self.plugins.items())

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

        if plugin_id in self.plugins:
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
