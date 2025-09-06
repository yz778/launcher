import importlib
import inspect
import logging
import os
import threading
from typing import Callable, List, Optional, Type

from gi.repository import GLib

from launcher.plugins.base import Plugin, SearchResult

logger = logging.getLogger(__name__)


class PluginManager:
    """Manager for loading and managing plugins"""

    __slots__ = (
        "plugins",
        "config",
        "active_search_threads",
        "active_search_threads_lock",
        "_executor",
        "plugins_dir",
        "prefix_registry",
    )

    def __init__(self, config):
        self.plugins = {}
        self.config = config
        self.active_search_threads = 0
        self.active_search_threads_lock = threading.Lock()
        self._executor = None
        self.plugins_dir = ""
        self.prefix_registry = {}  # prefix -> plugin_id mapping

    def _get_executor(self):
        """Get or create thread pool executor"""
        if self._executor is None:
            import concurrent.futures

            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=os.cpu_count() or 4, thread_name_prefix="plugin-search"
            )
        return self._executor

    def load_plugins(self, plugins_dir: str) -> None:
        """Discover and load all plugins from the specified directory"""
        self.plugins_dir = plugins_dir

        plugin_dirs = [
            d
            for d in os.listdir(plugins_dir)
            if os.path.isdir(os.path.join(plugins_dir, d))
            and d != "__pycache__"
            and not d.startswith(".")
        ]

        for plugin_dir in plugin_dirs:
            self.load_plugin(plugin_dir)

    def load_plugin(self, plugin_dir: str) -> bool:
        """Load a single plugin from its directory"""
        try:
            plugin_file = os.path.join(self.plugins_dir, plugin_dir, "plugin.py")
            if not os.path.exists(plugin_file):
                return False

            module_name = f"plugins.{plugin_dir}.plugin"
            module = importlib.import_module(module_name)

            for name, obj in inspect.getmembers(module):
                if (
                    inspect.isclass(obj)
                    and issubclass(obj, Plugin)
                    and obj != Plugin
                    and not inspect.isabstract(obj)
                ):
                    return self._register_plugin(obj)
        except Exception as e:
            logger.error(f"Error loading plugin {plugin_dir}: {e}")
            return False
        return False

    def _register_plugin(self, plugin_class: Type[Plugin]) -> bool:
        """Register and initialize a single plugin"""
        try:
            plugin = plugin_class()
            plugin_id = plugin.get_id()

            # Check if plugin is enabled - access plugin config from self.config
            plugin_config = getattr(self.config, plugin_id, None)
            enabled = getattr(plugin_config, "enabled", True) if plugin_config else True

            if not enabled:
                logger.info(
                    f"Plugin disabled: {plugin.get_name()} ({plugin_id}) - skipping registration"
                )
                return False

            # Register plugin defaults with config manager if it has DEFAULTS
            plugin_defaults = getattr(plugin_class, "DEFAULTS", {})
            if plugin_defaults and hasattr(self.config, "_config_manager"):
                # Register defaults for potential future config file creation
                self.config._config_manager.register_plugin_defaults(
                    plugin_id, plugin_defaults
                )

            if plugin.initialize(plugin_config):
                self.plugins[plugin_id] = plugin

                if plugin.has_prefix():
                    prefix = plugin.get_prefix()
                    if prefix in self.prefix_registry:
                        logger.warning(
                            f"Prefix '{prefix}' already registered by plugin {self.prefix_registry[prefix]}, "
                            f"overriding with plugin {plugin_id}"
                        )
                    self.prefix_registry[prefix] = plugin_id
                    logger.info(f"Registered prefix '{prefix}' for plugin {plugin_id}")

                logger.info(f"Initialized plugin: {plugin.get_name()} ({plugin_id})")
                return True
            else:
                logger.warning(
                    f"Failed to initialize plugin: {plugin.get_name()} ({plugin_id})"
                )
                return False

        except Exception as e:
            logger.error(f"Error registering plugin {plugin_class.__name__}: {e}")
            return False

    def unload_plugin(self, plugin_id: str) -> bool:
        """Unload a single plugin"""
        if plugin_id not in self.plugins:
            return False

        logger.info(f"Unloading plugin: {plugin_id}")
        plugin = self.plugins.pop(plugin_id, None)
        if plugin:
            try:
                if plugin.has_prefix():
                    prefix = plugin.get_prefix()
                    if (
                        prefix in self.prefix_registry
                        and self.prefix_registry[prefix] == plugin_id
                    ):
                        del self.prefix_registry[prefix]
                        logger.info(
                            f"Unregistered prefix '{prefix}' for plugin {plugin_id}"
                        )

                plugin.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up plugin {plugin_id}: {e}")

        return True

    def search(
        self,
        query: str,
        search_id: int,
        result_callback: Callable[[int, str, List[SearchResult]], None],
        finished_callback: Callable[[int], None],
    ) -> None:
        """
        Search across enabled plugins non-blockingly using thread pool.
        If query starts with a registered prefix, only search that plugin.
        """
        if not query or not query.strip():
            GLib.idle_add(finished_callback, search_id)
            return

        target_plugin_id = self._get_plugin_for_prefix(query)

        if target_plugin_id:
            if target_plugin_id in self.plugins:
                plugins_to_search = [(target_plugin_id, self.plugins[target_plugin_id])]
            else:
                GLib.idle_add(finished_callback, search_id)
                return
        else:
            plugins_to_search = [
                (plugin_id, plugin_instance)
                for plugin_id, plugin_instance in self.plugins.items()
                if not plugin_instance.has_prefix()
                or not self._query_matches_any_prefix(query)
            ]

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

    def _find_matching_prefix(self, query: str) -> Optional[str]:
        """
        Find the longest matching prefix for the given query.

        Sorts prefixes by length in descending order to ensure the most specific
        (longest) prefix is matched first, avoiding non-deterministic behavior
        when one prefix is a substring of another.

        Args:
            query: The search query

        Returns:
            The longest matching prefix or None if no prefix matches
        """
        sorted_prefixes = sorted(self.prefix_registry.keys(), key=len, reverse=True)
        for prefix in sorted_prefixes:
            if query.startswith(prefix):
                return prefix
        return None

    def _get_plugin_for_prefix(self, query: str) -> Optional[str]:
        """
        Get the plugin ID that should handle this query based on prefix matching.

        Args:
            query: The search query

        Returns:
            Plugin ID if query matches a registered prefix, None otherwise
        """
        matching_prefix = self._find_matching_prefix(query)
        return self.prefix_registry.get(matching_prefix) if matching_prefix else None

    def _query_matches_any_prefix(self, query: str) -> bool:
        """
        Check if query starts with any registered prefix.

        Args:
            query: The search query

        Returns:
            True if query matches any prefix, False otherwise
        """
        return self._find_matching_prefix(query) is not None

    def get_prefix_for_query(self, query: str) -> Optional[str]:
        """
        Get the prefix that matches this query.

        Args:
            query: The search query

        Returns:
            The matching prefix or None if no prefix matches
        """
        return self._find_matching_prefix(query)

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
            logger.error(f"Plugin {plugin_id} not found")
            return False

    def cleanup(self) -> None:
        """Release all plugin resources"""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

        for plugin_id in list(self.plugins.keys()):
            self.unload_plugin(plugin_id)
