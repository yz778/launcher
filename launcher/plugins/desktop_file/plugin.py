#!/usr/bin/env python3

import gi
import glob
import json
import logging
import os
import re
import shlex
import threading
from typing import Dict, List, Any, Optional
from xdg_base_dirs import xdg_data_home, xdg_data_dirs
from xdg.DesktopEntry import DesktopEntry

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf, GLib

from ..base import Plugin, SearchResult
from launcher.core.config_manager import ConfigManager
from launcher.utils.string_matcher import StringMatcher

logger = logging.getLogger(__name__)


class DesktopFile:
    """Class representing a parsed .desktop file"""

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
        self._icon_cache = {}
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
        instance._icon_cache = {}
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

    def _get_fallback_icon(self, size: int) -> Optional[GdkPixbuf.Pixbuf]:
        """Get fallback icon when primary icon loading fails"""
        try:
            icon_theme = Gtk.IconTheme.get_default()
            pixbuf = icon_theme.load_icon("application-x-executable", size, 0)
            return pixbuf
        except Exception:
            return None

    def get_icon_pixbuf(self, size: int) -> Optional[GdkPixbuf.Pixbuf]:
        """Load the icon as a pixbuf with exact size using pyxdg for icon lookup"""
        if size in self._icon_cache:
            return self._icon_cache[size]

        try:
            pixbuf = self._load_icon_pixbuf(size)
            pixbuf = self._ensure_correct_size(pixbuf, size)
            self._icon_cache[size] = pixbuf
            return pixbuf
        except Exception as e:
            logger.error(f"Error loading icon {self.icon}: {e}")
            pixbuf = self._get_fallback_icon(size)
            self._icon_cache[size] = pixbuf
            return pixbuf

    def _load_icon_pixbuf(self, size: int) -> Optional[GdkPixbuf.Pixbuf]:
        """Load icon pixbuf from various sources"""
        # Try direct file path first
        if os.path.isfile(self.icon):
            return GdkPixbuf.Pixbuf.new_from_file_at_size(self.icon, size, size)

        # Try XDG icon theme lookup
        pixbuf = self._load_from_xdg_theme(size)
        if pixbuf:
            return pixbuf

        # Try GTK icon theme
        pixbuf = self._load_from_gtk_theme(size)
        if pixbuf:
            return pixbuf

        # Fallback to default icon
        return self._get_fallback_icon(size)

    def _load_from_xdg_theme(self, size: int) -> Optional[GdkPixbuf.Pixbuf]:
        """Load icon from XDG icon theme"""
        from xdg.IconTheme import getIconPath

        icon_path = getIconPath(self.icon, size)

        # Try without extension if not found
        if not icon_path and "." in self.icon:
            icon_name = os.path.splitext(self.icon)[0]
            icon_path = getIconPath(icon_name, size)

        if icon_path:
            try:
                return GdkPixbuf.Pixbuf.new_from_file_at_size(icon_path, size, size)
            except GLib.Error:
                pass

        return None

    def _load_from_gtk_theme(self, size: int) -> Optional[GdkPixbuf.Pixbuf]:
        """Load icon from GTK icon theme"""
        icon_theme = Gtk.IconTheme.get_default()

        # Try original icon name
        if icon_theme.has_icon(self.icon):
            try:
                return icon_theme.load_icon(self.icon, size, 0)
            except GLib.Error:
                pass

        # Try without extension
        if "." in self.icon:
            icon_name = os.path.splitext(self.icon)[0]
            if icon_theme.has_icon(icon_name):
                try:
                    return icon_theme.load_icon(icon_name, size, 0)
                except GLib.Error:
                    pass

        return None

    def _ensure_correct_size(
        self, pixbuf: Optional[GdkPixbuf.Pixbuf], size: int
    ) -> Optional[GdkPixbuf.Pixbuf]:
        """Ensure pixbuf is the correct size"""
        if not pixbuf:
            return pixbuf

        if pixbuf.get_width() != size or pixbuf.get_height() != size:
            return pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)

        return pixbuf

    def cleanup(self) -> None:
        """Clean up cached pixbufs to prevent memory leaks"""
        self._icon_cache.clear()

    def is_visible(self) -> bool:
        """Check if the application should be visible in menus"""
        if self.desktop_entry:
            return not (
                self.desktop_entry.getHidden() or self.desktop_entry.getNoDisplay()
            )
        return not (self.hidden or self.no_display)


class DesktopFileScanner:
    """Class for scanning and caching .desktop files"""

    def __init__(self):
        self.desktop_files: Dict[str, DesktopFile] = {}
        self.scan_locations = [
            os.path.expanduser(loc)
            for loc in DesktopFilePlugin().get_config_defaults()["locations"]
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

    def __init__(self):
        super().__init__()
        self.desktop_files = {}
        self.locations = []
        self.icon_size = None
        self.matcher = None
        self.config = {}
        self.cache_file = None

    def get_id(self) -> str:
        return "desktop_file"

    def get_name(self) -> str:
        return "Desktop Files"

    def get_description(self) -> str:
        return "Search for applications from .desktop files"

    def get_config_defaults(self) -> Dict[str, Any]:
        """Get default configuration for this plugin"""
        locations = [
            str(xdg_data_home() / "applications"),
            *[str(path / "applications") for path in xdg_data_dirs()],
        ]
        return {
            "locations": locations,
            "track_history": True,  # Track desktop applications in history
        }

    def get_default_css(self) -> str:
        """Get default CSS for this plugin"""
        return """
/* Desktop File Plugin CSS */
.desktop-file-result #app-list-item {
    padding: 8px;
    border-radius: 8px;
    transition: background-color 0.2s ease;
    min-height: 50px; /* Ensure minimum height */
}

.desktop-file-result #app-list-item:hover {
    background-color: rgba(70, 90, 130, 0.4);
}

.desktop-file-result #app-list-item:selected {
    background-color: rgba(90, 110, 150, 0.6);
}

.desktop-file-result #app-name {
    color: #f0f0f0;
    font-size: 16px;
    font-weight: bold;
}

.desktop-file-result #app-description {
    color: #b0b0b0;
    font-size: 12px;
    font-style: italic;
}
"""

    def initialize(self, config: Dict[str, Any], config_manager) -> bool:
        """Initialize the plugin with the given configuration"""
        super().initialize(config, config_manager)

        # Get general config
        self.general_config = self.config_manager.get_config().get("general", {})
        defaults = self.get_config_defaults()

        # Get locations from config
        self.locations = [
            os.path.expanduser(loc)
            for loc in config.get("locations", defaults["locations"])
        ]

        # Get icon size from general config
        self.icon_size = self.get_icon_size()

        # Initialize with empty data first
        self.desktop_files = {}
        self.matcher = StringMatcher(items=[], key_func=lambda df: df.name)

        self.cache_file = os.path.join(
            self.config_manager.get_cache_dir(), f"{self.get_id()}_cache.json"
        )

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
        self._update_matcher_on_main_thread()  # Initial update from cache

        threading.Thread(target=self._scan_and_update_matcher, daemon=True).start()
        return True

    def _scan_and_update_matcher(self) -> None:
        """Performs the desktop file scan and updates the matcher in the main thread"""
        self._scan_desktop_files()
        self._save_to_cache()  # Save the newly scanned files to cache
        GLib.idle_add(self._update_matcher_on_main_thread)

    def _update_matcher_on_main_thread(self) -> bool:
        """Updates the string matcher on the main GTK thread"""
        self.matcher = StringMatcher(
            items=list(self.desktop_files.values()), key_func=lambda df: df.name
        )
        logger.info(
            f"Finished loading {len(self.desktop_files)} desktop files in background"
        )
        return False

    def rescan(self) -> None:
        """Rescan desktop files (for intelligent rescanning)"""
        logger.info("Rescanning desktop files...")
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
                        f"Desktop file rescan removed {removed_count} invalid history entries"
                    )
        except Exception as e:
            logger.error(f"Error cleaning history during desktop file rescan: {e}")

    def clean_invalid_history_entries(self, history_manager) -> int:
        """
        Clean invalid history entries for desktop files that no longer exist.

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

        logger.info(f"Cleaning desktop file history entries...")

        for entry in history_manager.user_input_history:
            if self._is_valid_desktop_file_entry(entry):
                valid_entries.append(entry)
            else:
                if entry.get("plugin_id") == self.get_id():
                    removed_count += 1
                    logger.debug(
                        f"Removing invalid desktop file entry: {entry.get('user_input', 'unknown')}"
                    )
                else:
                    # Keep entries from other plugins
                    valid_entries.append(entry)

        history_manager.user_input_history = valid_entries

        if removed_count > 0:
            logger.info(
                f"Desktop file plugin cleaned {removed_count} invalid history entries"
            )
            history_manager.save_history()

        return removed_count

    def _is_valid_desktop_file_entry(self, entry) -> bool:
        """
        Check if a desktop file history entry is still valid.

        Args:
            entry: History entry to validate

        Returns:
            True if entry is valid, False otherwise
        """
        try:
            # Only validate entries for this plugin
            if not isinstance(entry, dict) or entry.get("plugin_id") != self.get_id():
                return True  # Let other plugins handle their own entries

            # Basic structure validation
            required_fields = ["user_input", "plugin_id", "item_id", "timestamp"]
            for field in required_fields:
                if field not in entry:
                    logger.debug(
                        f"Desktop file entry missing required field '{field}': {entry}"
                    )
                    return False

            # Type validation
            user_input = entry.get("user_input")
            item_id = entry.get("item_id")
            timestamp = entry.get("timestamp")

            if not isinstance(user_input, str) or not user_input.strip():
                logger.debug(f"Invalid user_input in desktop file entry: {user_input}")
                return False

            if not isinstance(item_id, str) or not item_id.strip():
                logger.debug(f"Invalid item_id in desktop file entry: {item_id}")
                return False

            if not isinstance(timestamp, (int, float)) or timestamp <= 0:
                logger.debug(f"Invalid timestamp in desktop file entry: {timestamp}")
                return False

            # Check if the desktop file still exists
            if not os.path.isfile(item_id):
                logger.debug(f"Desktop file no longer exists: {item_id}")
                return False

            # Check if the desktop file is still valid
            try:
                desktop_file = DesktopFile(item_id)
                if not desktop_file.is_visible():
                    logger.debug(f"Desktop file no longer visible: {item_id}")
                    return False
            except Exception as e:
                logger.debug(f"Error validating desktop file {item_id}: {e}")
                return False

            return True

        except Exception as e:
            logger.debug(f"Error validating desktop file entry: {e}")
            return False

    def get_scan_directories(self) -> List[str]:
        """Get directories that should be watched for changes"""
        return self.locations

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
            if self._is_valid_desktop_file(desktop_file):
                key = os.path.basename(file_path)
                self.desktop_files[key] = desktop_file
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")

    def _is_valid_desktop_file(self, desktop_file: DesktopFile) -> bool:
        """Check if desktop file is valid and should be included"""
        return desktop_file.name and desktop_file.exec_cmd and desktop_file.is_visible()

    def cleanup(self) -> None:
        """Clean up plugin resources"""
        for desktop_file in self.desktop_files.values():
            desktop_file.cleanup()
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

        # Use string matcher to find matches
        matches = self.matcher.match(search_query, limit=20)

        # Convert matches to search results
        results = []
        for desktop_file, score in matches:
            result = SearchResult(
                plugin_id=self.get_id(),
                item_id=desktop_file.path,
                name=desktop_file.name,
                description=desktop_file.comment,
                icon=desktop_file.get_icon_pixbuf(size=self.icon_size),
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

        desktop_file = result.metadata.get("desktop_file")

        if not desktop_file.exec_cmd:
            return False

        args = shlex.join(result.metadata.get("args"))
        cmd_parts = shlex.split(
            re.sub(r"%[fu]", args, desktop_file.exec_cmd, flags=re.IGNORECASE)
        )

        try:
            import subprocess

            if desktop_file.terminal:
                terminal_command = self.get_terminal_command()
                cmd_parts = terminal_command.split() + cmd_parts

            logger.info(f"Executing command: {' '.join(cmd_parts)}")
            subprocess.Popen(cmd_parts)

            return True
        except Exception as e:
            logger.error(f"Error executing command {desktop_file.exec_cmd}: {e}")
            return False
