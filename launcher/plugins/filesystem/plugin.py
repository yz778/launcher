import logging
import os
import subprocess
from typing import List

from launcher.plugins.base import Plugin, SearchResult
from launcher.utils.icon_utils import normalize_icon_spec
from launcher.utils.process_manager import process_manager
from launcher.utils.string_matcher import StringMatcher

logger = logging.getLogger(__name__)


class FilesystemPlugin(Plugin):
    """Plugin for browsing the filesystem with path prefixes / . ~"""

    DEFAULTS = {"show_hidden": False, "max_results": 20}

    def __init__(self):
        super().__init__()
        self.prefixes = ["/", ".", "~"]

    def get_id(self) -> str:
        return "filesystem"

    def get_name(self) -> str:
        return "Filesystem"

    def get_description(self) -> str:
        return "Browse files and directories using path prefixes / . ~"

    def _resolve_case_insensitive_dir(self, dir_path: str) -> str | None:
        """Resolve directory path case-insensitively."""
        if dir_path == ".":
            return "."

        is_abs = os.path.isabs(dir_path)
        components = [c for c in os.path.normpath(dir_path).split(os.sep) if c]
        current = os.getcwd() if not is_abs else "/"

        for comp in components:
            try:
                items = os.listdir(current)
            except (OSError, PermissionError):
                return None

            matching_dirs = [
                item
                for item in items
                if os.path.isdir(os.path.join(current, item))
                and item.lower() == comp.lower()
            ]
            if not matching_dirs:
                return None
            current = os.path.join(current, matching_dirs[0])

        return current

    def search(self, query: str) -> List[SearchResult]:
        if not query:
            return []

        try:
            query_path = os.path.expanduser(query)
            dir_path_original = os.path.dirname(query_path) or "."
            basename = os.path.basename(query_path) or ""

            dir_path = self._resolve_case_insensitive_dir(dir_path_original)
            if not dir_path or not os.path.isdir(dir_path):
                return []

            # List directory contents
            items = []
            try:
                items = os.listdir(dir_path)
            except PermissionError:
                return []

            # Filter items starting with basename, exclude hidden if configured
            show_hidden_temp = (
                self.config.get("show_hidden", False)
                or basename.startswith(".")
                or (basename == "" and query.endswith("."))
            )
            matching_items = []
            for item in items:
                if show_hidden_temp or not item.startswith("."):
                    if not basename or item.lower().startswith(basename.lower()):
                        matching_items.append(item)

            # Use StringMatcher for scoring and highlighting
            matcher = StringMatcher(
                items=matching_items, key_func=lambda x: x, history=[]
            )
            matches = matcher.match(basename, limit=self.config.get("max_results", 20))

            results = []
            for item, score, field_highlight in matches:
                full_path = os.path.join(dir_path, item)
                is_dir = os.path.isdir(full_path)
                is_executable = os.access(full_path, os.X_OK)
                is_symlink = os.path.islink(full_path)

                # Determine icon and description
                if is_dir:
                    icon = "theme://folder"
                    description = ""
                elif is_executable:
                    icon = "theme://utilities-terminal"
                    description = "+x"
                else:
                    icon = "theme://text-x-generic"
                    description = ""

                # Add symlink suffix if applicable
                if is_symlink:
                    description = "→ " + os.path.realpath(full_path)

                # Construct display name
                resolved_dir = self._resolve_case_insensitive_dir(
                    os.path.dirname(query) or query
                ) or (os.path.dirname(query) or query)
                if basename:
                    name = os.path.join(resolved_dir, item)
                else:
                    name = os.path.join(resolved_dir, item)

                result = SearchResult(
                    plugin_id=self.get_id(),
                    item_id=full_path,
                    name=name,
                    description=description,
                    icon_spec=normalize_icon_spec(icon),
                    score=score,
                    hilight=field_highlight,
                    metadata={"is_dir": is_dir, "is_executable": is_executable},
                )
                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Error in filesystem search: {e}")
            return []

    def execute(self, result: SearchResult) -> bool:
        if result.plugin_id != self.get_id():
            return False

        full_path = result.item_id
        is_dir = result.metadata.get("is_dir", False)
        is_executable = result.metadata.get("is_executable", False)

        try:
            if is_dir:
                # Open directory in file manager
                subprocess.Popen(["xdg-open", full_path])
            elif is_executable:
                # Execute the file using process_manager for consistency
                logger.info(f"Executing executable: {full_path}")
                return process_manager.launch_detached([full_path])
            else:
                terminal_command = self.get_terminal_command()
                cmd_parts = terminal_command.split() + ["xdg-open", full_path]
                logger.info(f"Executing command: {' '.join(cmd_parts)}")
                return process_manager.launch_detached(cmd_parts)
            return True
        except Exception as e:
            logger.error(f"Error executing filesystem item {full_path}: {e}")
            return False
