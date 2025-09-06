from launcher.utils.process_manager import process_manager
from launcher.utils.string_matcher import StringMatcher
from launcher.plugins.base import Plugin, SearchResult
from typing import Dict, List, Any
from xdg_base_dirs import xdg_data_home, xdg_data_dirs
from xdg.DesktopEntry import DesktopEntry
import glob
import json
import logging
import os
import re
import shlex
import threading

logger = logging.getLogger(__name__)


class DesktopFile:
    """Class representing a parsed .desktop file"""

    __slots__ = [
        "__dict__",
        "path",
        "name",
        "exec_cmd",
        "icon",
        "comment",
        "hidden",
        "no_display",
        "terminal",
        "desktop_entry",
    ]

    def __init__(self, path: str):
        self.path = path
        self.name = ""
        self.exec_cmd = ""
        self.icon = ""
        self.comment = ""
        self.hidden = False
        self.no_display = False
        self.terminal = False
        self.desktop_entry = None
        self._parse()

    def to_dict(self) -> Dict[str, Any]:
        """Convert DesktopFile object to a dictionary for JSON serialization"""
        return {
            "path": self.path,
            "name": self.name,
            "exec_cmd": self.exec_cmd,
            "icon": self.icon,
            "comment": self.comment,
            "hidden": self.hidden,
            "no_display": self.no_display,
            "terminal": self.terminal,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DesktopFile":
        """Create a DesktopFile object from a dictionary (from cache)"""
        instance = object.__new__(cls)
        instance.path = data.get("path", "")
        instance.name = data.get("name", "")
        instance.exec_cmd = data.get("exec_cmd", "")
        instance.icon = data.get("icon", "")
        instance.comment = data.get("comment", "")
        instance.hidden = data.get("hidden", False)
        instance.no_display = data.get("no_display", False)
        instance.terminal = data.get("terminal", False)
        instance.desktop_entry = None
        return instance

    def _parse(self) -> None:
        """Parse the .desktop file to extract relevant information using xdg.DesktopEntry"""

        try:
            self.desktop_entry = DesktopEntry(self.path)
            self.name = self.desktop_entry.getName()
            self.exec_cmd = self.desktop_entry.getExec() or ""
            self.icon = self.desktop_entry.getIcon() or ""
            self.comment = self.desktop_entry.getComment() or ""
            self.hidden = self.desktop_entry.getHidden()
            self.no_display = self.desktop_entry.getNoDisplay()
            self.terminal = self.desktop_entry.getTerminal()

        except Exception as e:
            logger.error(f"Error parsing {self.path}: {e}")

    def get_icon_spec(self) -> str:
        """Get the icon specification for this desktop file"""
        if self.icon:
            # Use desktop:// URI scheme for desktop file icons
            return f"desktop://{self.icon}"
        else:
            # Fallback to theme icon
            return "theme://application-x-executable"

    def is_visible(self) -> bool:
        """Check if the application should be visible in menus"""
        if self.desktop_entry:
            return not (
                self.desktop_entry.getHidden() or self.desktop_entry.getNoDisplay()
            )
        return not (self.hidden or self.no_display)


class DesktopFileScanner:
    """Class for scanning and caching .desktop files"""

    __slots__ = ["desktop_files", "scan_locations"]

    def __init__(self):
        self.desktop_files: Dict[str, DesktopFile] = {}
        self.scan_locations = [
            os.path.expanduser(loc) for loc in DesktopFilePlugin.defaults["locations"]
        ]

    def scan(self) -> None:
        """Scan for desktop files in standard locations"""
        self.desktop_files = {}

        for location in self.scan_locations:
            if not os.path.isdir(location):
                continue

            pattern = os.path.join(location, "*.desktop")
            for file_path in glob.glob(pattern):
                try:
                    desktop_file = DesktopFile(file_path)

                    if (
                        desktop_file.name
                        and desktop_file.exec_cmd
                        and desktop_file.is_visible()
                    ):
                        # Use basename as key to handle overrides
                        key = os.path.basename(file_path)
                        self.desktop_files[key] = desktop_file
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {e}")

    def get_all_desktop_files(self) -> List[DesktopFile]:
        """Get all desktop files"""
        return list(self.desktop_files.values())


class DesktopFilePlugin(Plugin):
    """Plugin for searching .desktop files"""

    __slots__ = [
        "_matcher_lock",
        "cache_file",
        "config",
        "desktop_files",
        "locations",
        "matcher",
    ]

    DEFAULTS = {
        "locations": [
            str(xdg_data_home() / "applications"),
            *[str(path / "applications") for path in xdg_data_dirs()],
        ],
        "track_history": True,
    }

    def __init__(self):
        super().__init__()
        self._matcher_lock = threading.Lock()
        self.cache_file = None
        self.config = {}
        self.desktop_files = {}
        self.locations = []
        self.matcher = None

    def get_id(self) -> str:
        return "desktop_file"

    def get_name(self) -> str:
        return "Desktop Files"

    def get_description(self) -> str:
        return "Search for applications from .desktop files"

    def initialize(self, config) -> bool:
        """Initialize the plugin with the given configuration"""
        super().initialize(config)

        # Get locations from config
        self.locations = [
            os.path.expanduser(loc)
            for loc in getattr(config, "locations", self.DEFAULTS["locations"])
        ]

        # Initialize with empty data first
        self.desktop_files = {}
        self.matcher = StringMatcher(items=[], key_func=lambda df: df.name)
        # Access cache dir through services
        from launcher import services

        cache_dir = services.config_manager.get_cache_dir()
        self.cache_file = os.path.join(cache_dir, f"{self.get_id()}_cache.json")

        return True

    def _load_from_cache(self) -> None:
        """Load desktop files from the cache"""
        if not os.path.exists(self.cache_file):
            logger.info("Desktop file cache not found.")
            return

        try:
            with open(self.cache_file, "r") as f:
                cached_data = json.load(f)
                for item_data in cached_data:
                    desktop_file = DesktopFile.from_dict(item_data)
                    self.desktop_files[desktop_file.path] = desktop_file
            logger.info(f"Loaded {len(self.desktop_files)} desktop files from cache.")
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Error loading desktop file cache: {e}")

    def _save_to_cache(self) -> None:
        """Save desktop files to the cache"""
        try:
            with open(self.cache_file, "w") as f:
                json.dump([df.to_dict() for df in self.desktop_files.values()], f)
            logger.info(f"Saved {len(self.desktop_files)} desktop files to cache.")
        except IOError as e:
            logger.error(f"Error saving desktop file cache: {e}")

    def start(self) -> bool:
        """Load from cache and then start a background scan to refresh"""
        self._load_from_cache()
        self._update_matcher()  # Initial update from cache

        threading.Thread(target=self._scan_and_update_matcher, daemon=True).start()
        return True

    def _scan_and_update_matcher(self) -> None:
        """Performs the desktop file scan and updates the matcher"""
        self._scan_desktop_files()
        self._save_to_cache()  # Save the newly scanned files to cache
        self._update_matcher()

    def _update_matcher(self) -> None:
        """Updates the string matcher in a thread-safe manner"""
        # Create new matcher with current desktop files
        new_matcher = StringMatcher(
            items=list(self.desktop_files.values()), key_func=lambda df: df.name
        )

        # Atomically replace the matcher
        with self._matcher_lock:
            self.matcher = new_matcher

        logger.info(
            f"Finished loading {len(self.desktop_files)} desktop files in background"
        )

    def _scan_desktop_files(self) -> None:
        """Scan for desktop files in the configured locations"""
        self.desktop_files = {}

        for location in reversed(self.locations):
            self._scan_location(location)

    def _scan_location(self, location: str) -> None:
        """Scan a single location for desktop files"""
        if not os.path.isdir(location):
            return

        pattern = os.path.join(location, "*.desktop")
        for file_path in glob.glob(pattern):
            self._process_desktop_file(file_path)

    def _process_desktop_file(self, file_path: str) -> None:
        """Process a single desktop file"""
        try:
            desktop_file = DesktopFile(file_path)
            key = os.path.basename(file_path)
            self.desktop_files[key] = desktop_file
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")

    def cleanup(self) -> None:
        """Clean up plugin resources"""
        self.desktop_files.clear()

        if self.matcher:
            self.matcher = None

    def search(self, query: str) -> List[SearchResult]:
        """Search for desktop files matching the query"""
        if not query:
            return []

        # split query into search portion and arguments
        parts = shlex.split(query)
        search_query = parts[0] if parts else ""
        args = parts[1:] if len(parts) > 1 else []

        # Get a thread-safe reference to the current matcher
        with self._matcher_lock:
            current_matcher = self.matcher

        # Use string matcher to find matches
        matches = current_matcher.match(search_query, limit=20)

        # Convert matches to search results
        results = []
        for desktop_file, score in matches:
            result = SearchResult(
                plugin_id=self.get_id(),
                item_id=desktop_file.path,
                name=desktop_file.name,
                description=desktop_file.comment,
                icon_spec=desktop_file.get_icon_spec(),
                score=score,
                metadata={
                    "desktop_file": desktop_file,
                    "args": args,
                    "track_history": self.should_track_history(),
                },
            )
            results.append(result)

        return results

    def execute(self, result: SearchResult) -> bool:
        """Execute the desktop file"""
        if result.plugin_id != self.get_id():
            return False

        desktop_file_data = result.metadata.get("desktop_file")
        if not desktop_file_data:
            return False

        if isinstance(desktop_file_data, dict):
            desktop_file = DesktopFile.from_dict(desktop_file_data)
        else:
            desktop_file = desktop_file_data

        if not desktop_file.exec_cmd:
            return False

        args = shlex.join(result.metadata.get("args"))
        cmd_parts = shlex.split(
            re.sub(r"%[fu]", args, desktop_file.exec_cmd, flags=re.IGNORECASE)
        )

        try:
            if desktop_file.terminal:
                terminal_command = self.get_terminal_command()
                cmd_parts = terminal_command.split() + cmd_parts

            # Store the actual executed command in metadata for history tracking
            actual_executed_command = " ".join(cmd_parts)
            result.metadata["actual_executed_command"] = actual_executed_command
            logger.info(f"Executing command: {actual_executed_command}")

            # Create a copy of the environment and remove GDK_BACKEND
            env = os.environ.copy()
            if "GDK_BACKEND" in env:
                del env["GDK_BACKEND"]
            success = process_manager.launch_detached(cmd_parts, env)
            if success:
                result.metadata["desktop_file"] = desktop_file.to_dict()
            return success

        except Exception as e:
            logger.error(f"Error executing command {desktop_file.exec_cmd}: {e}")
            return False
