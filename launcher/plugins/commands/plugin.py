import logging
from typing import List

from launcher import services
from launcher.plugins.base import Plugin, SearchResult

logger = logging.getLogger(__name__)


class CommandsPlugin(Plugin):
    """
    Launcher plugin to execute internal commands with a colon prefix.
    """

    DEFAULTS = {"max_results": 5000}

    def __init__(self):
        super().__init__()
        self.prefix = ":"
        self.track_history = False
        self.commands = {
            "exit": {
                "name": ":exit",
                "description": "Shutdown the launcher",
                "icon": "https://img.icons8.com/?size=48&id=IwZ4mbmrC5gw&format=png",
            },
            "theme": {
                "name": ":theme",
                "description": "Switch launcher theme",
                "icon": "https://img.icons8.com/?size=80&id=Hs4y0qsqaZ6G&format=png",
            },
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

        command_input = self.strip_prefix(query).lower()
        results = []

        # Handle theme command specially
        if command_input.startswith("theme"):
            theme_part = command_input[5:].strip()  # Remove "theme" and whitespace

            try:
                available_themes = services.css_manager.get_available_themes()

                for theme in available_themes:
                    theme_name = theme["name"]
                    display_name = theme["display_name"]
                    if (
                        not theme_part
                        or theme_part in theme_name.lower()
                        or theme_part in display_name.lower()
                    ):
                        results.append(
                            SearchResult(
                                plugin_id=self.get_id(),
                                item_id=f"theme_{theme_name}",
                                name=f":theme {theme_name}",
                                description=f"Switch to {display_name}",
                                icon_spec="https://img.icons8.com/?size=80&id=Hs4y0qsqaZ6G&format=png",
                                score=95.0 if theme_part else 90.0,
                                metadata={
                                    "command": "apply_theme",
                                    "theme_name": theme_name,
                                },
                            )
                        )
            except Exception as e:
                logger.error(f"Error getting available themes: {e}")
        else:
            # Handle other commands normally
            for cmd_name, cmd_info in self.commands.items():
                if command_input == "" or cmd_name.startswith(command_input):
                    results.append(
                        SearchResult(
                            plugin_id=self.get_id(),
                            item_id=cmd_name,
                            name=cmd_info["name"],
                            description=cmd_info["description"],
                            icon_spec=cmd_info["icon"],
                            score=100.0,
                            metadata={"command": cmd_name},
                        )
                    )

        return results

    def preview(self, result: SearchResult) -> None:
        if result.plugin_id != self.get_id():
            return

        command = result.metadata.get("command")
        if command == "apply_theme":
            theme_name = result.metadata.get("theme_name")
            if theme_name:
                logger.info(f"Previewing theme: {theme_name}")
                self._apply_theme(theme_name, True)

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
            elif command == "apply_theme":
                theme_name = result.metadata.get("theme_name")
                if not theme_name:
                    logger.error("No theme name provided for apply_theme command")
                    return False

                logger.info(f"Applying theme: {theme_name}")
                return self._apply_theme(theme_name, False)
            elif command == "theme":
                return True
            else:
                logger.warning(f"Unknown command: {command}")
                return False

        except Exception as e:
            logger.error(f"Error executing command {command}: {e}")
            return False

    def _apply_theme(self, theme_name: str, is_preview: bool) -> bool:
        """Apply or preview a theme

        Args:
            theme_name: Name of the theme to apply
            is_preview: Preview only or save to config

        Returns:
            True if successful, False otherwise
        """
        try:
            # Create a new CSS manager instance and apply the theme
            plugins = getattr(services.plugin_manager, "plugins", None)

            if services.css_manager.load_all_styles(
                theme_name, plugins, with_transition=is_preview
            ):
                if not is_preview:
                    if services.config_manager:
                        services.config_manager.update_config(
                            "system.theme", theme_name
                        )
                        logger.info(
                            f"Theme '{theme_name}' applied and saved to configuration"
                        )
                        return True
                    else:
                        logger.warning(
                            "Config manager not available, theme applied but not saved"
                        )
                        return True
                else:
                    return True
            else:
                logger.error(f"Failed to apply theme: {theme_name}")
                return False

        except Exception as e:
            logger.error(f"Error applying theme {theme_name}: {e}")
            return False
