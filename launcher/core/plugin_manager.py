import importlib
import inspect
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Callable, List, Optional, Type, Iterable

from gi.repository import GLib
from xdg_base_dirs import xdg_data_home

from launcher.plugins.base import Plugin, SearchResult

logger = logging.getLogger(__name__)


class PluginManager:
    """Manager for loading and managing plugins"""

    __slots__ = (
        "plugins",
        "config",
        "active_search_threads",
        "active_search_threads_lock",
        "plugins_dir",
        "prefix_registry",
        "_executor",
        "_current_prefix_plugins",
        "is_loading",
    )

    def __init__(self, config):
        self.plugins = {}
        self.config = config
        self.active_search_threads = 0
        self.active_search_threads_lock = threading.Lock()
        self.plugins_dir = ""
        self.prefix_registry = {}  # prefix -> list of plugin instances mapping
        self._executor = None
        self._current_prefix_plugins = []  # List of plugin instances currently being searched via prefix
        self.is_loading = False

    def _get_executor(self):
        """Get or create thread pool executor"""
        if self._executor is None:
            import concurrent.futures

            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=os.cpu_count() or 4, thread_name_prefix="plugin-search"
            )
        return self._executor

    def load_plugins(self, plugins_dir: str) -> None:
        """Discover and load all plugins from the specified directory and user directory."""
        self.plugins_dir = plugins_dir

        # 1. Load built-in plugins
        self._load_plugins_from_dir(plugins_dir, is_user_plugin=False)

        # 2. Load user plugins under XDG config
        user_plugins_dir = xdg_data_home() / "launcher" / "plugins"
        if user_plugins_dir.is_dir():
            self._load_plugins_from_dir(str(user_plugins_dir), is_user_plugin=True)

    def async_load_plugins(
        self,
        base_plugins_dir: str,
        user_dir: str,
        extra_dirs: Optional[Iterable[str]] = None,
        completion_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        """Asynchronously load plugins from multiple dirs using ThreadPoolExecutor."""
        self.is_loading = True
        executor = self._get_executor()

        # Prepare directory list with flags for "is_user"
        dir_specs = []
        dir_specs.append((Path(base_plugins_dir), False))
        if user_dir:
            dir_specs.append((Path(user_dir), True))
        if extra_dirs:
            dir_specs.extend(
                (Path(p), True) for p in extra_dirs
            )  # mark extra as user-like

        # Filter to existing directories
        dir_specs = [(p, is_user) for p, is_user in dir_specs if p.is_dir()]

        # Submit all loads
        futures = [
            executor.submit(self._load_plugins_from_dir_async, str(path), is_user)
            for path, is_user in dir_specs
        ]

        def internal_completion_callback():
            try:
                results = []
                for fut in futures:
                    try:
                        results.append(fut.result())
                    except Exception as e:
                        logger.error(f"Plugin load failed: {e}")  # continue
                        results.append([])
                # Flatten lists; preserve order of dir_specs
                all_plugins = [p for sub in results for p in sub]
                GLib.idle_add(self._register_loaded_plugins, all_plugins)
            except Exception as e:
                logger.error(f"Error in async plugin loading: {e}")
            finally:
                GLib.idle_add(lambda: setattr(self, "is_loading", False))
                if completion_callback:
                    GLib.idle_add(completion_callback)

        executor.submit(internal_completion_callback)

    def _load_plugins_from_dir(self, plugins_dir: str, is_user_plugin: bool) -> None:
        if is_user_plugin and plugins_dir not in sys.path:
            sys.path.insert(0, plugins_dir)

        for entry in os.scandir(plugins_dir):
            if (
                entry.is_dir()
                and entry.name != "__pycache__"
                and not entry.name.startswith(".")
            ):
                self.load_plugin(entry.name, plugins_dir, is_user_plugin)

    def _load_plugins_from_dir_async(
        self, plugins_dir: str, is_user_plugin: bool
    ) -> List[Type[Plugin]]:
        """Load plugins from directory asynchronously, returning list of plugin classes"""
        if is_user_plugin and plugins_dir not in sys.path:
            sys.path.insert(0, plugins_dir)

        plugin_classes = []
        for entry in os.scandir(plugins_dir):
            if (
                entry.is_dir()
                and entry.name != "__pycache__"
                and not entry.name.startswith(".")
            ):
                plugin_class = self._load_plugin_class(
                    entry.name, plugins_dir, is_user_plugin
                )
                if plugin_class:
                    plugin_classes.append(plugin_class)
        return plugin_classes

    def load_plugin(
        self,
        plugin_dir: str,
        base_dir: Optional[str] = None,
        is_user_plugin: bool = False,
    ) -> bool:
        """Load a single plugin from its directory"""
        try:
            # Use base_dir if provided, otherwise fall back to self.plugins_dir for backward compatibility
            plugin_base_dir = base_dir if base_dir is not None else self.plugins_dir
            plugin_file = os.path.join(plugin_base_dir, plugin_dir, "plugin.py")
            if not os.path.exists(plugin_file):
                return False

            if is_user_plugin:
                # User plugins are in a directory added to sys.path
                module_name = f"{plugin_dir}.plugin"
            else:
                # Built-in plugins are part of the 'plugins' package
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

    def _load_plugin_class(
        self,
        plugin_dir: str,
        base_dir: Optional[str] = None,
        is_user_plugin: bool = False,
    ) -> Optional[Type[Plugin]]:
        """Load a single plugin class from its directory without registering"""
        try:
            # Use base_dir if provided, otherwise fall back to self.plugins_dir for backward compatibility
            plugin_base_dir = base_dir if base_dir is not None else self.plugins_dir
            plugin_file = os.path.join(plugin_base_dir, plugin_dir, "plugin.py")
            if not os.path.exists(plugin_file):
                return None

            if is_user_plugin:
                # User plugins are in a directory added to sys.path
                module_name = f"{plugin_dir}.plugin"
            else:
                # Built-in plugins are part of the 'plugins' package
                module_name = f"plugins.{plugin_dir}.plugin"

            module = importlib.import_module(module_name)

            for name, obj in inspect.getmembers(module):
                if (
                    inspect.isclass(obj)
                    and issubclass(obj, Plugin)
                    and obj != Plugin
                    and not inspect.isabstract(obj)
                ):
                    return obj
        except Exception as e:
            logger.error(f"Error loading plugin {plugin_dir}: {e}")
            return None
        return None

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
                    prefixes = plugin.get_prefix()
                    if isinstance(prefixes, list):
                        for prefix in prefixes:
                            if prefix not in self.prefix_registry:
                                self.prefix_registry[prefix] = []
                            self.prefix_registry[prefix].append(plugin)
                            logger.info(
                                f"Registered prefix '{prefix}' for plugin {plugin_id}"
                            )
                    else:
                        prefix = prefixes
                        if prefix not in self.prefix_registry:
                            self.prefix_registry[prefix] = []
                        self.prefix_registry[prefix].append(plugin)
                        logger.info(
                            f"Registered prefix '{prefix}' for plugin {plugin_id}"
                        )

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

    def _register_loaded_plugins(self, plugin_classes: List[Type[Plugin]]) -> None:
        """Register a list of loaded plugin classes"""
        for plugin_class in plugin_classes:
            self._register_plugin(plugin_class)

    def unload_plugin(self, plugin_id: str) -> bool:
        """Unload a single plugin"""
        if plugin_id not in self.plugins:
            return False

        logger.info(f"Unloading plugin: {plugin_id}")
        plugin = self.plugins.pop(plugin_id, None)
        if plugin:
            try:
                if plugin.has_prefix():
                    prefixes = plugin.get_prefix()
                    if isinstance(prefixes, list):
                        for prefix in prefixes:
                            if (
                                prefix in self.prefix_registry
                                and plugin in self.prefix_registry[prefix]
                            ):
                                self.prefix_registry[prefix].remove(plugin)
                                if not self.prefix_registry[
                                    prefix
                                ]:  # Remove empty list
                                    del self.prefix_registry[prefix]
                                logger.info(
                                    f"Unregistered prefix '{prefix}' for plugin {plugin_id}"
                                )
                    else:
                        prefix = prefixes
                        if (
                            prefix in self.prefix_registry
                            and plugin in self.prefix_registry[prefix]
                        ):
                            self.prefix_registry[prefix].remove(plugin)
                            if not self.prefix_registry[prefix]:  # Remove empty list
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
        query = query.strip()
        if not query:
            GLib.idle_add(finished_callback, search_id)
            return

        target_plugins = self._get_plugins_for_prefix(query)

        if target_plugins:
            plugins_to_search = [
                (plugin.get_id(), plugin)
                for plugin in target_plugins
                if plugin.get_id() in self.plugins
            ]
            if not plugins_to_search:
                GLib.idle_add(finished_callback, search_id)
                return

            self._current_prefix_plugins = target_plugins
        else:
            plugins_to_search = [
                (plugin_id, plugin_instance)
                for plugin_id, plugin_instance in self.plugins.items()
                if not plugin_instance.has_prefix() or not plugin_instance.prefix_only
            ]
            self._current_prefix_plugins = []

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

        For non-symbol prefixes (alphanumeric), requires a space delimiter after the prefix
        to avoid overmatching (e.g., "calc" should match "calc 2+2" but not "calculator").
        Symbol prefixes match immediately without requiring a delimiter.

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
                # Check if this is a symbol prefix (non-alphanumeric characters)
                is_symbol_prefix = not prefix.isalnum()

                if is_symbol_prefix:
                    # Symbol prefixes match immediately
                    return prefix
                else:
                    # Word prefixes require a space delimiter or end of string
                    if len(query) == len(prefix) or query[len(prefix)].isspace():
                        return prefix
        return None

    def _get_plugins_for_prefix(self, query: str) -> List[Plugin]:
        """
        Get the plugin instances that should handle this query based on prefix matching.

        Args:
            query: The search query

        Returns:
            List of plugin instances if query matches a registered prefix, empty list otherwise
        """
        matching_prefix = self._find_matching_prefix(query)
        return self.prefix_registry.get(matching_prefix, []) if matching_prefix else []

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

    def get_current_prefix_plugins(self) -> List[Plugin]:
        """
        Get the plugins currently being searched via prefix matching.

        Returns:
            List of plugin instances that are being searched due to prefix matching,
            empty list if no prefix is being used
        """
        return self._current_prefix_plugins.copy()

    def get_plugin_by_id(self, plugin_id: str) -> Optional[Plugin]:
        """Get a plugin instance by its ID"""
        return self.plugins.get(plugin_id)

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
