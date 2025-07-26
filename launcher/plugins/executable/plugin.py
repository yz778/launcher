#!/usr/bin/env python3

import gi
import json
import logging
import os
import re
import shlex
import stat
import threading
from typing import Dict, List, Any


gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # Import GLib at the module level

from ..base import Plugin, SearchResult
from launcher.core.config_manager import ConfigManager
from launcher.utils.string_matcher import StringMatcher

logger = logging.getLogger(__name__)


class ExecutableFile:
    """Class representing an executable file"""

    __slots__ = ("path", "name", "is_executable", "custom_icon")

    def __init__(self, path: str):
        self.path = path
        self.name = os.path.basename(path)
        self.is_executable = False
        self.custom_icon = None
        self._check_executable()
        self._parse_icon_directive()

    def to_dict(self) -> Dict[str, Any]:
        """Convert ExecutableFile object to a dictionary for JSON serialization"""
        return {
            "path": self.path,
            "name": self.name,
            "is_executable": self.is_executable,
            "custom_icon": self.custom_icon,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutableFile":
        """Create an ExecutableFile object from a dictionary (from cache)"""
        instance = object.__new__(cls)
        instance.path = data.get("path", "")
        instance.name = data.get("name", "")
        instance.is_executable = data.get("is_executable", False)
        instance.custom_icon = data.get("custom_icon")
        return instance

    def _check_executable(self) -> None:
        """Check if the file is executable"""
        try:
            if os.path.isfile(self.path):
                st = os.stat(self.path)
                self.is_executable = bool(st.st_mode & stat.S_IXUSR)
        except Exception as e:
            logger.error(f"Error checking executable {self.path}: {e}")
            self.is_executable = False

    def _parse_icon_directive(self) -> None:
        """Parse the #icon directive from the file"""
        if not self.is_executable:
            return

        try:
            with open(self.path, "r", encoding="utf-8", errors="ignore") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= 10:
                        break
                    lines.append(line.strip())

                found_shebang = False
                for line in lines:
                    if line.startswith("#!"):
                        found_shebang = True
                        continue
                    elif found_shebang and line.startswith("#icon "):
                        icon_spec = line[6:].strip()
                        if icon_spec:
                            self.custom_icon = icon_spec
                            logger.debug(
                                f"Found custom icon '{icon_spec}' for {self.path}"
                            )
                        break
                    elif line and not line.startswith("#"):
                        break

        except Exception as e:
            logger.debug(f"Could not parse icon directive from {self.path}: {e}")

    def get_command(self) -> str:
        """Get the command to execute the file"""
        return self.path


class ExecutablePlugin(Plugin):
    """Plugin for searching executable files in custom directories"""

    __slots__ = (
        "executables",
        "locations",
        "include_patterns",
        "exclude_patterns",
        "icon_size",
        "matcher",
        "default_icon",
        "icon_cache",
        "cache_icons",
        "general_config",
        "cache_file",
    )

    def __init__(self):
        super().__init__()
        self.executables = {}
        self.locations = []
        self.include_patterns = []
        self.exclude_patterns = []
        self.icon_size = None
        self.matcher = None
        self.default_icon = None
        self.icon_cache = {}  # Cache for loaded custom icons
        self.cache_icons = True
        self.general_config = {}
        self.cache_file = None

    def get_id(self) -> str:
        return "executable"

    def get_name(self) -> str:
        return "Executables"

    def get_description(self) -> str:
        return "Search for executable files in custom directories with support for custom icons (file paths, URLs, or theme names)"

    def get_config_defaults(self) -> Dict[str, Any]:
        """Get default configuration for this plugin"""
        return {
            "locations": [
                "~/bin",
                "~/.local/bin",
            ],
            "include": [
                ".*",  # Match all files
            ],
            "exclude": [
                "^\\..*",  # Exclude hidden files
                ".*~$",  # Exclude backup files
                ".*\\.bak$",  # Exclude .bak files
            ],
            "cache_icons": True,  # Cache loaded icons for better performance
            "track_history": True,  # Track executable commands in history
        }

    def get_default_css(self) -> str:
        """Get default CSS for this plugin"""
        return """
/* Executable Plugin CSS */
.executable-result #app-list-item {
    padding: 8px;
    border-radius: 8px;
    transition: background-color 0.2s ease;
    min-height: 50px; /* Ensure minimum height */
}

.executable-result #app-list-item:hover {
    background-color: rgba(60, 100, 80, 0.4);
}

.executable-result #app-list-item:selected {
    background-color: rgba(80, 120, 100, 0.6);
}

.executable-result #app-name {
    color: #e0f0e0;
    font-size: 16px;
    font-weight: bold;
}

.executable-result #app-description {
    color: #a0c0a0;
    font-size: 12px;
    font-family: monospace;
}
"""

    def initialize(self, config: Dict[str, Any], config_manager) -> bool:
        """Initialize the plugin with the given configuration"""
        super().initialize(config, config_manager)

        # Get locations from config using helper
        locations = self.get_config_value("locations")
        self.locations = [os.path.expanduser(loc) for loc in locations]

        # Get include patterns from config using helper
        include_patterns = self.get_config_value("include")
        self.include_patterns = [re.compile(pattern) for pattern in include_patterns]

        # Get exclude patterns from config using helper
        exclude_patterns = self.get_config_value("exclude")
        self.exclude_patterns = [re.compile(pattern) for pattern in exclude_patterns]

        # Get icon size using helper
        self.icon_size = self.get_icon_size()

        # Get cache icons setting using helper
        self.cache_icons = self.get_config_value("cache_icons")

        self.cache_file = os.path.join(
            self.config_manager.get_cache_dir(), f"{self.get_id()}_cache.json"
        )

        return True

    def _load_from_cache(self) -> None:
        """Load executables from the cache"""
        if not os.path.exists(self.cache_file):
            logger.info("Executable file cache not found.")
            return

        try:
            with open(self.cache_file, "r") as f:
                cached_data = json.load(f)
                for item_data in cached_data:
                    executable = ExecutableFile.from_dict(item_data)
                    self.executables[executable.path] = executable
            logger.info(f"Loaded {len(self.executables)} executables from cache.")
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Error loading executable file cache: {e}")

    def _save_to_cache(self) -> None:
        """Save executables to the cache"""
        try:
            with open(self.cache_file, "w") as f:
                json.dump([ex.to_dict() for ex in self.executables.values()], f)
            logger.info(f"Saved {len(self.executables)} executables to cache.")
        except IOError as e:
            logger.error(f"Error saving executable file cache: {e}")

    def start(self) -> bool:
        """
        Start the plugin and perform any necessary setup work

        This loads the default icon and starts scanning for executable files in a background thread.
        """
        GLib.idle_add(self._load_default_icon)

        self._load_from_cache()
        self._update_matcher_on_main_thread()  # Initial update from cache

        threading.Thread(target=self._scan_and_update_matcher, daemon=True).start()

        return True

    def _scan_and_update_matcher(self) -> None:
        """Performs the executable file scan and updates the matcher in the main thread"""
        self._scan_executables()
        self._save_to_cache()  # Save the newly scanned files to cache
        GLib.idle_add(self._update_matcher_on_main_thread)

    def _update_matcher_on_main_thread(self) -> bool:
        """Updates the string matcher on the main GTK thread"""
        self.matcher = StringMatcher(
            items=list(self.executables.values()), key_func=lambda ef: ef.name
        )
        logger.info(
            f"Finished loading {len(self.executables)} executable files in background"
        )
        return False  # Remove from idle queue

    def rescan(self) -> None:
        """Rescan executable files (for intelligent rescanning)"""
        logger.info("Rescanning executable files...")
        threading.Thread(target=self._rescan_with_cleanup, daemon=True).start()

    def _rescan_with_cleanup(self) -> None:
        """Perform rescan and cleanup invalid history entries"""
        # First do the normal rescan
        self._scan_and_update_matcher()

        # Then clean up invalid history entries
        try:
            from launcher.launcher import get_history_manager

            history_manager = get_history_manager()
            if history_manager:
                removed_count = self.clean_invalid_history_entries(history_manager)
                if removed_count > 0:
                    logger.info(
                        f"Executable rescan removed {removed_count} invalid history entries"
                    )
        except Exception as e:
            logger.error(f"Error cleaning history during executable rescan: {e}")

    def clean_invalid_history_entries(self, history_manager) -> int:
        """
        Clean invalid history entries for executable files that no longer exist or are no longer executable.

        Args:
            history_manager: The history manager instance

        Returns:
            Number of entries removed
        """
        if not history_manager or not hasattr(history_manager, "user_input_history"):
            return 0

        original_count = len(history_manager.user_input_history)
        valid_entries = []
        removed_count = 0

        logger.info(f"Cleaning executable file history entries...")

        for entry in history_manager.user_input_history:
            if self._is_valid_executable_entry(entry):
                valid_entries.append(entry)
            else:
                if entry.get("plugin_id") == self.get_id():
                    removed_count += 1
                    logger.debug(
                        f"Removing invalid executable entry: {entry.get('user_input', 'unknown')}"
                    )
                else:
                    # Keep entries from other plugins
                    valid_entries.append(entry)

        history_manager.user_input_history = valid_entries

        if removed_count > 0:
            logger.info(
                f"Executable plugin cleaned {removed_count} invalid history entries"
            )
            history_manager.save_history()

        return removed_count

    def _is_valid_executable_entry(self, entry) -> bool:
        """
        Check if an executable history entry is still valid.

        Args:
            entry: History entry to validate

        Returns:
            True if entry is valid, False otherwise
        """
        try:
            # Only validate entries for this plugin
            if not isinstance(entry, dict) or entry.get("plugin_id") != self.get_id():
                return True  # Let other plugins handle their own entries

            # Use common structural validation
            if not self.is_structurally_valid(entry):
                return False

            # Check if the executable file still exists
            if not os.path.isfile(item_id):
                logger.debug(f"Executable file no longer exists: {item_id}")
                return False

            # Check if the file is still executable
            try:
                st = os.stat(item_id)
                if not (st.st_mode & stat.S_IXUSR):
                    logger.debug(f"File no longer executable: {item_id}")
                    return False
            except Exception as e:
                logger.debug(f"Cannot check executable status for {item_id}: {e}")
                return False

            return True

        except Exception as e:
            logger.debug(f"Error validating executable entry: {e}")
            return False

    def get_scan_directories(self) -> List[str]:
        """Get directories that should be watched for changes"""
        return self.locations

    def _load_default_icon(self) -> bool:
        """Load the default icon for executables"""
        from launcher.utils.icon_utils import load_theme_icon

        self.default_icon = load_theme_icon("utilities-terminal", self.icon_size)
        return False

    def _load_custom_icon(self, icon_spec: str):
        """Load a custom icon based on the icon specification"""
        if not icon_spec:
            return self.default_icon

        from launcher.utils.icon_utils import load_custom_icon

        cache = self.icon_cache if self.cache_icons else None
        cache_dir = os.path.join(self.config_manager.get_cache_dir(), "url_icons")
        loaded_icon = load_custom_icon(icon_spec, self.icon_size, cache, cache_dir)

        return loaded_icon or self.default_icon

    def _scan_executables(self) -> None:
        """Scan for executable files in the configured locations"""
        self.executables = {}

        for location in self.locations:
            self._scan_executable_location(location)

        logger.info(f"Loaded {len(self.executables)} executable files")

    def _scan_executable_location(self, location: str) -> None:
        """Scan a single location for executable files"""
        if not os.path.isdir(location):
            return

        try:
            for filename in os.listdir(location):
                if self._should_include_file(filename):
                    self._process_executable_file(location, filename)
        except Exception as e:
            logger.error(f"Error scanning directory {location}: {e}")

    def _should_include_file(self, filename: str) -> bool:
        """Check if file should be included based on patterns"""
        return any(
            pattern.match(filename) for pattern in self.include_patterns
        ) and not any(pattern.match(filename) for pattern in self.exclude_patterns)

    def _process_executable_file(self, location: str, filename: str) -> None:
        """Process a single executable file"""
        path = os.path.join(location, filename)
        executable = ExecutableFile(path)
        if executable.is_executable:
            self.executables[path] = executable

    def cleanup(self) -> None:
        """Clean up plugin resources"""
        self.executables.clear()
        self.icon_cache.clear()

        if self.matcher:
            self.matcher = None

    def search(self, query: str) -> List[SearchResult]:
        """Search for executable files matching the query"""
        if not query:
            return []

        parts = shlex.split(query)
        search_query = parts[0] if parts else ""
        args = parts[1:] if len(parts) > 1 else []

        matches = self.matcher.match(search_query, limit=20)

        results = []
        for executable, score in matches:
            icon = (
                self._load_custom_icon(executable.custom_icon)
                if executable.custom_icon
                else self.default_icon
            )

            result = SearchResult(
                plugin_id=self.get_id(),
                item_id=executable.path,
                name=executable.name,
                description=executable.path,
                icon=icon,
                score=score,
                metadata={
                    "command": executable.get_command(),
                    "args": args,
                    "custom_icon": executable.custom_icon,  # Store for debugging
                    "track_history": self.should_track_history(),
                },
            )
            results.append(result)

        return results

    def execute(self, result: SearchResult) -> bool:
        """Execute the executable file"""
        if result.plugin_id != self.get_id():
            return False

        command = result.metadata.get("command")
        if not command:
            return False

        cmd_parts = shlex.split(command) + result.metadata.get("args")
        use_terminal = not result.metadata.get("shift_pressed", False)

        try:
            import subprocess

            if use_terminal:
                terminal_command = self.get_terminal_command()
                cmd_parts = terminal_command.split() + cmd_parts

            logger.info(f"Executing command: {' '.join(cmd_parts)}")
            subprocess.Popen(cmd_parts)

            return True
        except Exception as e:
            logger.error(f"Error executing command {command}: {e}")
            return False
