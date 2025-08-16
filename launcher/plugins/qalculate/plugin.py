#!/usr/bin/env python3

import logging
from typing import Dict, List, Any, Optional
import subprocess

import pyperclip
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from ..base import Plugin, SearchResult
from launcher.utils.scoring_system import calculate_match_score

logger = logging.getLogger(__name__)


class QalculatePlugin(Plugin):
    """Plugin for calculating mathematical expressions"""

    def __init__(self):
        super().__init__()
        self.icon_size = None
        self.icon = None
        self._last_valid_result = None

    def get_id(self) -> str:
        return "qalculate"

    def get_name(self) -> str:
        return "Qalculate"

    def get_description(self) -> str:
        return "Calculate expressions with Qalculate"

    def get_config_defaults(self) -> Dict[str, Any]:
        """Get default configuration for this plugin"""
        return {
            "track_history": True,  # Track calculator results in history
        }

    def get_default_css(self) -> str:
        """Get default CSS for this plugin"""
        return """
/* Qalculate Plugin CSS */
.qalculate-result #app-list-item {
    padding: 8px;
    border-radius: 8px;
    transition: background-color 0.2s ease;
    min-height: 50px; /* Ensure minimum height */
}

.qalculate-result #app-list-item:hover {
    background-color: rgba(130, 90, 70, 0.4);
}

.qalculate-result #app-list-item:selected {
    background-color: rgba(150, 110, 90, 0.6);
}

.qalculate-result #app-name {
    color: #f0e0d0;
    font-size: 18px;
    font-weight: bold;
    font-family: monospace;
}

.qalculate-result #app-description {
    color: #c0b0a0;
    font-size: 14px;
    font-family: monospace;
}
"""

    def initialize(self, config: Dict[str, Any], config_manager) -> bool:
        """Initialize the plugin with the given configuration"""
        super().initialize(config, config_manager)

        # Check if qalc is available before proceeding with initialization
        try:
            subprocess.run(
                ["qalc", "--version"], check=True, capture_output=True, text=True
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            logger.warning("qalc command not found. Qalculate plugin will be disabled.")
            return False

        # Get icon size using helper
        self.icon_size = self.get_icon_size()

        return True

    def start(self) -> bool:
        GLib.idle_add(self._load_icon)
        return True

    def _load_icon(self) -> bool:
        from launcher.utils.icon_utils import load_theme_icon

        self.icon = load_theme_icon("accessories-calculator", self.icon_size)
        return False

    def _is_calculation(self, query: str) -> bool:
        """Check if the query looks like a calculation using simple heuristics"""
        if not query:
            return False

        query = query.strip()

        # 1. Explicit calculation trigger
        if query.startswith("="):
            return True

        # 2. Starts with a number (most calculations do)
        if query and query[0].isdigit():
            return True

        # 3. Contains conversion keywords
        conversion_keywords = [" to ", " in ", " as ", " into "]
        if any(keyword in query.lower() for keyword in conversion_keywords):
            return True

        # 4. Contains function call pattern (something followed by parentheses)
        if "(" in query and ")" in query:
            return True

        return False

    def _calculate(self, expression: str) -> Optional[str]:
        """
        Calculate the result of the expression using qalc CLI

        Returns None if calculation fails
        """
        # Strip leading = if present
        if expression.startswith("="):
            expression = expression[1:].strip()

        try:
            # Use qalc for calculation
            # The -t option provides a terse output (just the result)
            process = subprocess.run(
                ["qalc", "-t", expression], capture_output=True, text=True, check=True
            )
            result = process.stdout.strip()
            return result

        except FileNotFoundError:
            logger.debug("qalc command not found during calculation")
            return None
        except subprocess.CalledProcessError as e:
            logger.debug(f"Error calculating with qalc: {e.stderr}")
            return None
        except Exception as e:
            logger.debug(f"Error processing qalc output: {e}")
            return None

    def search(self, query: str) -> List[SearchResult]:
        """Search for calculations matching the query"""
        # Check if this is a calculation
        if not query or not self._is_calculation(query):
            return []

        result = self._calculate(query)

        if result is None:
            if self._last_valid_result is None:
                return []

            result = self._last_valid_result

        else:
            self._last_valid_result = result

        display_query = query
        if display_query.startswith("="):
            display_query = display_query[1:].strip()

        search_result = SearchResult(
            plugin_id=self.get_id(),
            item_id=query,
            name=query,
            description=result,
            icon=self.icon,
            score=calculate_match_score(query, query, is_name=True),
            metadata={
                "result": result,
                "track_history": self.should_track_history(),
            },
        )

        return [search_result]

    def execute(self, result: SearchResult) -> bool:
        """Execute the calculation result - copy to clipboard or launch qalc based on modifiers"""
        if result.plugin_id != self.get_id():
            return False

        # Check if shift was pressed (for launching qalc)
        shift_pressed = result.metadata.get("shift_pressed", False)

        if shift_pressed:
            # Shift+Enter: Launch qalculate-gtk
            return self._launch_qalculate_gui(result)
        else:
            # Enter: Copy result to clipboard
            return self._copy_to_clipboard(result)

    def _launch_qalculate_gui(self, result: SearchResult) -> bool:
        """Launch qalculate-gtk with the expression"""
        query = result.name
        if not query:
            return False

        try:
            if query.startswith("="):
                expression = query[1:].strip()
            else:
                expression = query.strip()

            subprocess.Popen(["qalculate-gtk", expression])
            logger.info(f"Launched qalculate-gtk with expression: {expression}")
            return True

        except FileNotFoundError:
            logger.error(
                "qalculate-gtk command not found. Please install qalculate-gtk."
            )
            return False

        except Exception as e:
            logger.error(f"Error launching qalculate-gtk: {e}")
            return False

    def _copy_to_clipboard(self, result: SearchResult) -> bool:
        """Copy the calculation result to clipboard using pyperclip"""
        calculation_result = result.metadata.get("result")
        if not calculation_result:
            return False

        try:
            pyperclip.copy(calculation_result)
            logger.info(f"Copied calculation result to clipboard: {calculation_result}")
            return True

        except Exception as e:
            logger.error(f"Error copying to clipboard: {e}")
            return False
