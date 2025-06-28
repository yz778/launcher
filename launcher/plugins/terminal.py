#!/usr/bin/env python3

import logging
import os
import shlex
import subprocess
from typing import Dict, Any, List

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # GLib might not be strictly needed if no idle_add

from plugins.base import Plugin, SearchResult

logger = logging.getLogger(__name__)


class TerminalPlugin(Plugin):
    """
    Launcher plugin to execute shell commands directly in a terminal.
    """

    def __init__(self):
        super().__init__()
        self.prefix = ">"
        self.default_icon = None
        self.general_config = {}
        self.icon_size = None

    def get_id(self) -> str:
        return "terminal"

    def get_name(self) -> str:
        return "Terminal"

    def get_description(self) -> str:
        return "Execute shell commands directly."

    def get_config_defaults(self) -> Dict[str, Any]:
        return {
            "prefix": ">",
            "track_history": True,  # Track terminal commands in history
        }

    def get_default_css(self) -> str:
        return """
        /* Terminal Plugin CSS */
        .terminal-result #app-list-item {
            padding: 8px;
            border-radius: 8px;
            transition: background-color 0.2s ease;
            min-height: 50px;
        }
        .terminal-result #app-list-item:hover {
            background-color: rgba(70, 90, 110, 0.4);
        }
        .terminal-result #app-list-item:selected {
            background-color: rgba(90, 110, 130, 0.6);
        }
        .terminal-result #app-name {
            color: #d0e0f0;
            font-size: 16px;
            font-weight: bold;
        }
        .terminal-result #app-description {
            color: #a0b0c0;
            font-size: 12px;
            font-family: monospace;
        }
        """

    def initialize(self, config: Dict[str, Any]) -> bool:
        self.general_config = config.get("general", {})
        plugin_specific_config = config.get(
            self.get_id(), {}
        )  # Plugin-specific config is under its ID
        defaults = self.get_config_defaults()

        # Set track_history setting
        self.track_history = plugin_specific_config.get(
            "track_history", defaults["track_history"]
        )

        self.prefix = plugin_specific_config.get("prefix", defaults["prefix"])
        self.icon_size = self.general_config.get("icon_size")
        return True

    def start(self) -> bool:
        GLib.idle_add(self._load_default_icon)
        logger.info("TerminalPlugin started.")
        return True

    def _load_default_icon(self) -> bool:
        """
        Load the default terminal icon from the icon theme.
        This method is scheduled to run on the main GTK thread for thread safety.
        """
        try:
            icon_theme = Gtk.IconTheme.get_default()
            self.default_icon = icon_theme.load_icon(
                "utilities-terminal", self.icon_size, 0
            )
        except Exception as e:
            self.default_icon = None

        # Return False to ensure this function is only called once by idle_add
        return False

    def search(self, query: str) -> List[SearchResult]:
        if query.startswith(self.prefix):
            command = query[len(self.prefix) :].strip()
            if not command:
                return []

            result = SearchResult(
                plugin_id=self.get_id(),
                item_id=command,
                name=command,
                description="Execute in terminal",
                icon=self.default_icon,
                score=100,
                metadata={
                    "command": command,
                    "track_history": self.should_track_history(),
                },
            )
            return [result]
        return []

    def execute(self, result: SearchResult) -> bool:
        if result.plugin_id != self.get_id():
            return False

        command = result.metadata.get("command")
        if not command:
            return False

        try:
            import subprocess

            terminal_command = self.general_config.get("terminal_command")
            cmd_parts = terminal_command.split() + shlex.split(command)

            logger.info(f"Executing command: {' '.join(cmd_parts)}")
            subprocess.Popen(cmd_parts)

            return True
        except Exception as e:
            logger.error(f"Error executing command {command}: {e}")
            return False
