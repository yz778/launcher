#!/usr/bin/env python3

import logging
import os
import re
import shlex
import stat
import threading
from typing import Dict, List, Any

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # Import GLib at the module level

from plugins.base import Plugin, SearchResult
from launcher.utils.string_matcher import StringMatcher

logger = logging.getLogger(__name__)


class ExecutableFile:
    """Class representing an executable file"""

    def __init__(self, path: str):
        self.path = path
        self.name = os.path.basename(path)
        self.is_executable = False
        self._check_executable()

    def _check_executable(self) -> None:
        """Check if the file is executable"""
        try:
            # Check if the file exists and is executable
            if os.path.isfile(self.path):
                # Check if the file has execute permission
                st = os.stat(self.path)
                self.is_executable = bool(st.st_mode & stat.S_IXUSR)
        except Exception as e:
            logger.error(f"Error checking executable {self.path}: {e}")
            self.is_executable = False

    def get_command(self) -> str:
        """Get the command to execute the file"""
        return self.path


class ExecutablePlugin(Plugin):
    """Plugin for searching executable files in custom directories"""

    def __init__(self):
        super().__init__()  # Call super() to initialize the base Plugin class
        self.executables = {}
        self.locations = []
        self.include_patterns = []
        self.exclude_patterns = []
        self.icon_size = None
        self.matcher = None
        self.default_icon = None

    def get_id(self) -> str:
        return "executable"

    def get_name(self) -> str:
        return "Executables"

    def get_description(self) -> str:
        return "Search for executable files in custom directories"

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

    def initialize(self, config: Dict[str, Any]) -> bool:
        """
        Initialize the plugin with the given configuration

        This only loads configuration and CSS, without doing any heavy setup work.
        """
        # Store the general config for later use
        self.general_config = config.get("general", {})

        # Get default config
        defaults = self.get_config_defaults()

        # Get locations from config
        self.locations = [
            os.path.expanduser(loc)
            for loc in config.get("locations", defaults["locations"])
        ]

        # Get include patterns from config
        include_patterns = config.get("include", defaults["include"])
        self.include_patterns = [re.compile(pattern) for pattern in include_patterns]

        # Get exclude patterns from config
        exclude_patterns = config.get("exclude", defaults["exclude"])
        self.exclude_patterns = [re.compile(pattern) for pattern in exclude_patterns]

        # Get icon size from general config
        self.icon_size = self.general_config.get("icon_size")

        return True

    def start(self) -> bool:
        """
        Start the plugin and perform any necessary setup work

        This loads the default icon and starts scanning for executable files in a background thread.
        """
        GLib.idle_add(self._load_default_icon)

        # Start the scan in a separate thread
        import threading

        threading.Thread(target=self._scan_and_update_matcher, daemon=True).start()

        return True

    def _scan_and_update_matcher(self) -> None:
        """Performs the executable file scan and updates the matcher in the main thread"""
        self._scan_executables()
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
        threading.Thread(target=self._scan_and_update_matcher, daemon=True).start()

    def get_scan_directories(self) -> List[str]:
        """Get directories that should be watched for changes"""
        return self.locations

    def _load_default_icon(self) -> bool:
        """Load the default icon for executables"""
        try:
            icon_theme = Gtk.IconTheme.get_default()
            self.default_icon = icon_theme.load_icon(
                "utilities-terminal", self.icon_size, 0
            )
        except Exception as e:
            self.default_icon = None

        return False

    def _scan_executables(self) -> None:
        """Scan for executable files in the configured locations"""
        self.executables = {}

        for location in self.locations:
            if not os.path.isdir(location):
                continue

            try:
                for filename in os.listdir(location):
                    if any(
                        pattern.match(filename) for pattern in self.include_patterns
                    ) and not any(
                        pattern.match(filename) for pattern in self.exclude_patterns
                    ):
                        path = os.path.join(location, filename)
                        executable = ExecutableFile(path)
                        if executable.is_executable:
                            self.executables[path] = executable

            except Exception as e:
                logger.error(f"Error scanning directory {location}: {e}")

        logger.info(f"Loaded {len(self.executables)} executable files")

    def search(self, query: str) -> List[SearchResult]:
        """Search for executable files matching the query"""
        if not query:
            return []

        # split query into search portion and arguments
        parts = shlex.split(query)
        search_query = parts[0] if parts else ""
        args = parts[1:] if len(parts) > 1 else []

        # Use string matcher to find matches
        matches = self.matcher.match(search_query, limit=20)

        # Convert matches to search results
        results = []
        for executable, score in matches:
            result = SearchResult(
                plugin_id=self.get_id(),
                item_id=executable.path,
                name=executable.name,
                description=executable.path,
                icon=self.default_icon,
                score=score,
                metadata={
                    "command": executable.get_command(),
                    "args": args,
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
                terminal_command = self.general_config.get("terminal_command")
                cmd_parts = terminal_command.split() + cmd_parts

            logger.info(f"Executing command: {' '.join(cmd_parts)}")
            subprocess.Popen(cmd_parts)

            return True
        except Exception as e:
            logger.error(f"Error executing command {command}: {e}")
            return False
