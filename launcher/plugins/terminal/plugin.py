from ..base import Plugin, SearchResult
from launcher.utils.scoring_system import calculate_match_score
from launcher.utils.process_manager import process_manager
from typing import Dict, Any, List
import logging
import shlex

logger = logging.getLogger(__name__)


class TerminalPlugin(Plugin):
    """
    Launcher plugin to execute shell commands directly in a terminal.
    """

    defaults = {
        "prefix": ">",
        "track_history": True,
    }

    def __init__(self):
        super().__init__()
        self.prefix = ">"

    def get_id(self) -> str:
        return "terminal"

    def get_name(self) -> str:
        return "Terminal"

    def get_description(self) -> str:
        return "Execute shell commands directly."

    def initialize(self, config: Dict[str, Any], config_manager) -> bool:
        super().initialize(config, config_manager)
        self.prefix = config.get("prefix")
        return True

    def start(self) -> bool:
        return True

    def search(self, query: str) -> List[SearchResult]:
        if query.startswith(self.prefix):
            command = query[len(self.prefix) :].strip()
            if not command:
                return []

            # Extract base command for display name
            base_command = command.split()[0] if command else command

            result = SearchResult(
                plugin_id=self.get_id(),
                item_id=command,
                name=base_command,
                description="Execute in terminal",
                icon_spec="https://img.icons8.com/?size=80&id=v8LYQxpvZ4xX&format=png",
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
            terminal_command = self.get_terminal_command()
            cmd_parts = terminal_command.split() + shlex.split(command)
            logger.info(f"Executing command: {' '.join(cmd_parts)}")
            success = process_manager.launch_detached(cmd_parts)
            return success

        except Exception as e:
            logger.error(f"Error executing command {command}: {e}")
            return False
