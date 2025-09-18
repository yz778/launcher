import logging
import os
import subprocess
from typing import List

from launcher.plugins.base import Plugin, SearchResult
from launcher.utils.icon_utils import normalize_icon_spec
from launcher.utils.process_manager import process_manager

logger = logging.getLogger(__name__)


class FilesystemPlugin(Plugin):
    """Plugin for browsing the filesystem with path prefixes / . ~"""

    DEFAULTS = {
        "show_hidden": False,
        "max_results": 20,
    }

    def get_id(self) -> str:
        return "filesystem"

    def get_name(self) -> str:
        return "Filesystem"

    def get_description(self) -> str:
        return "Browse files and directories using path prefixes / . ~"

    def search(self, query: str) -> List[SearchResult]:
        if not query or not any(query.startswith(prefix) for prefix in ["/", ".", "~"]):
            return []

        try:
            # Expand ~ to home directory
            query_path = os.path.expanduser(query)

            # Get the directory and basename
            dir_path = os.path.dirname(query_path) or "."
            basename = os.path.basename(query_path) or ""

            if not os.path.isdir(dir_path):
                return []

            # List directory contents
            items = []
            try:
                items = os.listdir(dir_path)
            except PermissionError:
                return []

            # Filter items starting with basename, exclude hidden if configured
            matching_items = []
            for item in items:
                if self.config.show_hidden or not item.startswith("."):
                    if not basename or item.lower().startswith(basename.lower()):
                        matching_items.append(item)

            matching_items.sort()

            results = []
            for item in matching_items[: self.config.max_results]:
                full_path = os.path.join(dir_path, item)
                is_dir = os.path.isdir(full_path)
                is_executable = os.access(full_path, os.X_OK)

                if is_dir:
                    icon = "theme://folder"
                    description = f"Directory: {full_path}"
                else:
                    if is_executable:
                        icon = "theme://utilities-terminal"
                        description = f"Executable: {full_path}"
                    else:
                        icon = "theme://text-x-generic"
                        description = f"File: {full_path}"

                result = SearchResult(
                    plugin_id=self.get_id(),
                    item_id=full_path,
                    name=item,
                    description=description,
                    icon_spec=normalize_icon_spec(icon),
                    score=1.0,  # All results have same score, or compute based on match length
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
                import subprocess

                subprocess.Popen(["xdg-open", full_path])
            elif is_executable:
                # Execute the file using process_manager for consistency
                logger.info(f"Executing executable: {full_path}")
                return process_manager.launch_detached([full_path])
            else:
                # Open file with default application
                import subprocess

                subprocess.Popen(["xdg-open", full_path])
            return True
        except Exception as e:
            logger.error(f"Error executing filesystem item {full_path}: {e}")
            return False
