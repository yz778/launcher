#!/usr/bin/env python3

import logging
from typing import Dict, List, Any, Optional
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from plugins.base import Plugin, SearchResult

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
            "track_history": False,  # Don't track calculator results in history by default
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

    def initialize(self, config: Dict[str, Any]) -> bool:
        """
        Initialize the plugin with the given configuration

        This only loads configuration and CSS, without doing any heavy setup work.
        """
        # Store the general config for later use
        self.general_config = config.get("general", {})

        # Get default config
        defaults = self.get_config_defaults()
        
        # Set track_history setting
        self.track_history = config.get("track_history", defaults["track_history"])

        # Get icon size from general config
        self.icon_size = self.general_config.get("icon_size")

        return True

    def start(self) -> bool:
        """
        Start the plugin and perform any necessary setup work

        This loads the calculator icon. Sympy will be loaded lazily when needed.
        """
        GLib.idle_add(self._load_icon)
        return True

    def _load_icon(self) -> bool:
        """Load the calculator icon"""
        try:
            icon_theme = Gtk.IconTheme.get_default()
            self.icon = icon_theme.load_icon("qalculate", self.icon_size, 0)
        except Exception:
            self.icon = None

        return False

    def _is_calculation(self, query: str) -> bool:
        """Check if the query looks like a calculation"""
        if query and query[0] in "=-0123456789([":
            return True

        # If the query starts with common math functions, it's likely a calculation
        math_funcs = ["sin(", "cos(", "tan(", "log(", "ln(", "sqrt(", "abs(", "exp("]
        if any(query.lower().startswith(func) for func in math_funcs):
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
            logger.error(
                "qalc command not found. Please install it (e.g., 'sudo apt install qalc')."
            )
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
            name=result,
            description=query,
            icon=self.icon,
            score=100.0,
            metadata={
                "result": result,
                "track_history": self.should_track_history(),
            },
        )

        return [search_result]

    def execute(self, result: SearchResult) -> bool:
        """Execute the calculation result (copy to clipboard)"""
        if result.plugin_id != self.get_id():
            return False

        query = result.description
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
