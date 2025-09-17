import json
import logging
import os
import re
import shlex
import stat
import threading
from typing import Any, Dict, List

from launcher.plugins.base import Plugin, SearchResult
from launcher.utils.icon_utils import normalize_icon_spec
from launcher.utils.process_manager import process_manager
from launcher.utils.string_matcher import StringMatcher

logger = logging.getLogger(__name__)
home = os.path.expanduser("~")
homelen = len(home)


class ExecutableFile:
    """Class representing an executable file"""

    __slots__ = (
        "path",
        "name",
        "description",
        "is_executable",
        "custom_icon",
        "use_terminal",
    )

    def __init__(self, path: str):
        self.path = path
        self.name = os.path.basename(path)
        self.description = (
            "~" + self.path[homelen:]
            if self.path.startswith(home + os.sep)
            else self.path
        )
        self.is_executable = False
        self.custom_icon = None
        self.use_terminal = True
        self._check_executable()
        self._parse_directives()

    def to_dict(self) -> Dict[str, Any]:
        """Convert ExecutableFile object to a dictionary for JSON serialization"""
        return {
            "path": self.path,
            "name": self.name,
            "description": self.description,
            "is_executable": self.is_executable,
            "custom_icon": self.custom_icon,
            "use_terminal": self.use_terminal,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutableFile":
        """Create an ExecutableFile object from a dictionary (from cache)"""
        instance = object.__new__(cls)
        instance.path = data.get("path", "")
        instance.name = data.get("name", "")
        instance.description = data.get("description", "")
        instance.is_executable = data.get("is_executable", False)
        instance.custom_icon = data.get("custom_icon")
        instance.use_terminal = data.get("use_terminal", True)
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

    def _parse_directives(self) -> None:
        """Parse special directives from the file"""
        if not self.is_executable:
            return

        try:
            with open(self.path, "r", encoding="utf-8", errors="ignore") as f:
                found_shebang = False
                for i, line in enumerate(f):
                    if i >= 10:
                        break

                    if line.startswith("#!"):
                        found_shebang = True
                        continue

                    elif not found_shebang:
                        continue

                    elif line.startswith("#") or line.startswith("--"):
                        stripped_line = line.lstrip("#").lstrip("--").strip()

                        if stripped_line.startswith("icon "):
                            value = stripped_line[5:].strip()
                            if value:
                                self.custom_icon = value

                        elif stripped_line.startswith("name "):
                            value = stripped_line[5:].strip()
                            if value:
                                self.name = value

                        elif stripped_line.startswith("desc "):
                            value = stripped_line[5:].strip()
                            if value:
                                self.description = value

                        elif stripped_line.startswith("noterm"):
                            self.use_terminal = False

        except Exception:
            pass

    def get_command(self) -> str:
        """Get the command to execute the file"""
        return self.path


class ExecutablePlugin(Plugin):
    """Plugin for searching executable files in custom directories"""

    __slots__ = (
        "_matcher_lock",
        "cache_file",
        "executables",
        "matcher",
        "include_patterns",
        "exclude_patterns",
    )

    DEFAULTS = {
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
        "cache_icons": True,
    }

    def __init__(self):
        super().__init__()
        self._matcher_lock = threading.Lock()
        self.cache_file = None
        self.executables = {}
        self.matcher = None
        self.include_patterns = None
        self.exclude_patterns = None

    def get_id(self) -> str:
        return "executable"

    def get_name(self) -> str:
        return "Executables"

    def get_description(self) -> str:
        return "Search for executable files in custom directories with support for custom icons (file paths, URLs, or theme names)"

    def initialize(self, user_config) -> bool:
        """Initialize the plugin with the given configuration"""
        super().initialize(user_config)

        # Access cache dir through services
        from launcher import services

        cache_dir = services.config_manager.get_cache_dir()
        self.cache_file = os.path.join(cache_dir, f"{self.get_id()}_cache.json")
        self.include_patterns = [re.compile(pattern) for pattern in self.config.include]
        self.exclude_patterns = [re.compile(pattern) for pattern in self.config.exclude]
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

        This starts scanning for executable files in a background thread.
        """
        self._load_from_cache()
        self._update_matcher()  # Initial update from cache

        threading.Thread(target=self._scan_and_update_matcher, daemon=True).start()

        return True

    def _scan_and_update_matcher(self) -> None:
        """Performs the executable file scan and updates the matcher"""
        self._scan_executables()
        self._save_to_cache()  # Save the newly scanned files to cache
        self._update_matcher()

    def _update_matcher(self) -> None:
        """Updates the string matcher in a thread-safe manner"""
        # Create new matcher with current executables
        new_matcher = StringMatcher(
            items=list(self.executables.values()), key_func=lambda ef: ef.name
        )

        # Atomically replace the matcher
        with self._matcher_lock:
            self.matcher = new_matcher

        logger.info(
            f"Finished loading {len(self.executables)} executable files in background"
        )

    def _scan_executables(self) -> None:
        """Scan for executable files in the configured locations"""
        self.executables = {}

        for location in self.config.locations:
            expanded_location = os.path.expanduser(location)
            self._scan_executable_location(expanded_location)

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

    def validate_item(self, item_id: str) -> bool:
        """Check if the executable file still exists and is executable."""
        return os.path.isfile(item_id) and os.access(item_id, os.X_OK)

    def cleanup(self) -> None:
        """Clean up plugin resources"""
        self.executables.clear()

        if self.matcher:
            self.matcher = None

    def search(self, query: str) -> List[SearchResult]:
        """Search for executable files matching the query"""
        if not query:
            return []

        parts = shlex.split(query)
        search_query = parts[0] if parts else ""
        args = parts[1:] if len(parts) > 1 else []

        # Get a thread-safe reference to the current matcher
        with self._matcher_lock:
            current_matcher = self.matcher

        matches = current_matcher.match(search_query, limit=20)

        results = []
        for executable, score, field_highlight in matches:
            # Use custom icon if specified, otherwise use fallback
            if executable.custom_icon:
                icon_spec = normalize_icon_spec(executable.custom_icon)
            else:
                icon_spec = "theme://utilities-terminal"

            result = SearchResult(
                plugin_id=self.get_id(),
                item_id=executable.path,
                name=executable.name,
                description=executable.description,
                icon_spec=icon_spec,
                score=score,
                hilight=field_highlight,
                metadata={
                    "command": executable.get_command(),
                    "args": args,
                    "executable_data": executable.to_dict(),  # Store dictionary representation
                },
            )
            results.append(result)

        return results

    def execute(self, result: SearchResult) -> bool:
        """Execute the executable file"""
        if result.plugin_id != self.get_id():
            return False

        executable_data: Dict[str, Any] = result.metadata.get("executable_data")
        if not executable_data:
            logger.error("Executable data not found in result metadata.")
            return False
        executable: ExecutableFile = ExecutableFile.from_dict(executable_data)
        command: str = result.metadata.get("command")
        if not command:
            return False

        cmd_parts = shlex.split(command) + result.metadata.get("args", [])
        use_terminal = executable.use_terminal and not result.metadata.get(
            "shift_pressed", False
        )

        try:
            if use_terminal:
                terminal_command = self.get_terminal_command()
                cmd_parts = terminal_command.split() + cmd_parts

            # Store the actual executed command in metadata for history tracking
            actual_executed_command = " ".join(cmd_parts)
            result.metadata["actual_executed_command"] = actual_executed_command
            logger.info(f"Executing command: {actual_executed_command}")
            success = process_manager.launch_detached(cmd_parts)
            return success

        except Exception as e:
            logger.error(f"Error executing command {command}: {e}")
            return False
