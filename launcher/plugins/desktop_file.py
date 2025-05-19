#!/usr/bin/env python3

import os
import glob
import logging
import re
import shlex
from typing import Dict, List, Any, Optional
from xdg_base_dirs import xdg_data_home, xdg_data_dirs
from xdg.DesktopEntry import DesktopEntry

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf, GLib

from plugins.base import Plugin, SearchResult
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
        self._parse()

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

    def get_icon_pixbuf(self, size: int = 24) -> Optional[GdkPixbuf.Pixbuf]:
        """Load the icon as a pixbuf with exact size using pyxdg for icon lookup"""
        from xdg.IconTheme import getIconPath

        try:
            pixbuf = None
            icon_theme = Gtk.IconTheme.get_default()

            if os.path.isfile(self.icon):
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.icon, size, size)

            else:
                icon_path = getIconPath(self.icon, size)

                if not icon_path and "." in self.icon:
                    icon_name = os.path.splitext(self.icon)[0]
                    icon_path = getIconPath(icon_name, size)

                if icon_path:
                    try:
                        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                            icon_path, size, size
                        )
                    except GLib.Error:
                        pass

                if not pixbuf:
                    # Check if icon exists in GTK theme
                    if icon_theme.has_icon(self.icon):
                        try:
                            pixbuf = icon_theme.load_icon(self.icon, size, 0)
                        except GLib.Error:
                            pass

                    # Try without extension in GTK theme
                    elif "." in self.icon:
                        icon_name = os.path.splitext(self.icon)[0]
                        if icon_theme.has_icon(icon_name):
                            try:
                                pixbuf = icon_theme.load_icon(icon_name, size, 0)
                            except GLib.Error:
                                pass

            # Fallback to generic icon if all else fails
            if not pixbuf:
                pixbuf = self._get_fallback_icon(size)

            # Ensure the pixbuf is exactly the requested size
            if pixbuf and (pixbuf.get_width() != size or pixbuf.get_height() != size):
                pixbuf = pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)

            return pixbuf

        except Exception as e:
            logger.error(f"Error loading icon {self.icon}: {e}")

            pixbuf = self._get_fallback_icon(size)
            return pixbuf

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
        self.desktop_files = {}
        self.locations = []
        self.icon_size = 24
        self.matcher = None
        self.config = {}

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
            "icon_size": 24,
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

    def initialize(self, config: Dict[str, Any]) -> bool:
        """Initialize the plugin with the given configuration"""
        # Store the config for later use
        self.config = config

        # Get general config
        self.general_config = config.get("general", {})

        # Get locations from config
        self.locations = [
            os.path.expanduser(loc)
            for loc in config.get("locations", self.get_config_defaults()["locations"])
        ]

        # Get icon size from general config
        self.icon_size = self.general_config.get("icon_size", 24)

        # Initialize with empty data first
        self.desktop_files = {}
        self.matcher = StringMatcher(items=[], key_func=lambda df: df.name)

        return True

    def start(self) -> bool:
        """Scans for desktop files and initializes the string matcher"""
        logger.info("Starting scan of desktop files...")
        self._scan_desktop_files()

        # Update the string matcher with the loaded files
        self.matcher = StringMatcher(
            items=list(self.desktop_files.values()), key_func=lambda df: df.name
        )

        logger.info(f"Finished loading {len(self.desktop_files)} desktop files")
        return True

    def _scan_desktop_files(self) -> None:
        """Scan for desktop files in the configured locations"""
        self.desktop_files = {}

        for location in reversed(self.locations):
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

        logger.info(f"Loaded {len(self.desktop_files)} desktop files")

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
                metadata={"desktop_file": desktop_file, "args": args},
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

        # Replace subsitutions with arguments (%f %F %u %U)
        args = shlex.join(result.metadata.get("args"))
        cmd_parts = shlex.split(
            re.sub(r"%[fu]", args, desktop_file.exec_cmd, flags=re.IGNORECASE)
        )

        try:
            import subprocess

            if desktop_file.terminal:
                terminal_command = self.general_config.get("terminal_command")
                cmd_parts = terminal_command.split() + cmd_parts

            logger.info(f"Executing command: {' '.join(cmd_parts)}")
            subprocess.Popen(cmd_parts)

            return True
        except Exception as e:
            logger.error(f"Error executing command {desktop_file.exec_cmd}: {e}")
            return False
