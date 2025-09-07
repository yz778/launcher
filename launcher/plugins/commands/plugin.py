import logging
from typing import List

from launcher.plugins.base import Plugin, SearchResult

logger = logging.getLogger(__name__)


class CommandsPlugin(Plugin):
    """
    Launcher plugin to execute internal commands with a colon prefix.
    """

    def __init__(self):
        super().__init__()
        self.prefix = ":"
        self.track_history = False
        self.commands = {
            "exit": {
                "name": "Exit",
                "description": "Shutdown the launcher",
                "icon": "https://img.icons8.com/?size=30&id=61022&format=png",
            }
        }

    def get_id(self) -> str:
        return "commands"

    def get_name(self) -> str:
        return "Commands"

    def get_description(self) -> str:
        return "Execute internal launcher commands."

    def start(self) -> bool:
        return True

    def search(self, query: str) -> List[SearchResult]:
        if not query.startswith(self.prefix):
            return []

        command = self.strip_prefix(query).lower()
        if not command:
            results = []
            for cmd_name, cmd_info in self.commands.items():
                result = SearchResult(
                    plugin_id=self.get_id(),
                    item_id=cmd_name,
                    name=cmd_info["name"],
                    description=cmd_info["description"],
                    icon_spec=cmd_info["icon"],
                    score=100.0,
                    metadata={"command": cmd_name},
                )
                results.append(result)
            return results

        # Filter commands that match the query
        results = []
        for cmd_name, cmd_info in self.commands.items():
            if cmd_name.startswith(command):
                # Calculate a simple score based on how well it matches
                score = 100.0 - (len(cmd_name) - len(command)) * 10
                result = SearchResult(
                    plugin_id=self.get_id(),
                    item_id=cmd_name,
                    name=cmd_info["name"],
                    description=cmd_info["description"],
                    icon_spec=cmd_info["icon"],
                    score=score,
                    metadata={"command": cmd_name},
                )
                results.append(result)

        return results

    def execute(self, result: SearchResult) -> bool:
        if result.plugin_id != self.get_id():
            return False

        command = result.metadata.get("command")
        if not command:
            return False

        try:
            if command == "exit":
                logger.info("Exit command executed, shutting down launcher")
                # Import here to avoid circular imports
                from launcher.launcher import shutdown

                shutdown("exit command")
                return True
            else:
                logger.warning(f"Unknown command: {command}")
                return False

        except Exception as e:
            logger.error(f"Error executing command {command}: {e}")
            return False
