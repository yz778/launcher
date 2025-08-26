#!/usr/bin/env python3

from ..base import Plugin, SearchResult
from gi.repository import GLib
from launcher.utils.scoring_system import calculate_match_score
from typing import Dict, Any, List
import logging
import shlex

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

    def initialize(self, config: Dict[str, Any], config_manager) -> bool:
        super().initialize(config, config_manager)

        # Get configuration using helpers
        self.prefix = self.get_config_value("prefix")
        self.icon_size = self.get_icon_size()
        return True

    def start(self) -> bool:
        GLib.idle_add(self._load_icon)
        return True

    def _load_icon(self) -> bool:
        from launcher.utils.icon_utils import load_custom_icon

        icon_url = "https://img.icons8.com/?size=80&id=v8LYQxpvZ4xX&format=png"
        icon_size = self.icon_size or 48  # Fallback to 48 if icon_size is None
        self.default_icon = load_custom_icon(icon_url, icon_size)
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
                score=calculate_match_score(query, command, is_name=True),
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
            import os
            import subprocess

            terminal_command = self.get_terminal_command()
            cmd_parts = terminal_command.split() + shlex.split(command)

            logger.info(f"Executing command: {' '.join(cmd_parts)}")

            # Create a copy of the environment and remove GDK_BACKEND
            env = os.environ.copy()
            if "GDK_BACKEND" in env:
                del env["GDK_BACKEND"]
                logger.debug("Removed GDK_BACKEND from environment")

            subprocess.Popen(cmd_parts, env=env, start_new_session=True)

            return True
        except Exception as e:
            logger.error(f"Error executing command {command}: {e}")
            return False
