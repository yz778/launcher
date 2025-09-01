#!/usr/bin/env python3

from ..base import Plugin, SearchResult
from launcher.utils.scoring_system import calculate_match_score
from typing import Dict, List, Any, Optional
import logging
import pyperclip
import subprocess

logger = logging.getLogger(__name__)


class QalculatePlugin(Plugin):
    """Plugin for calculating mathematical expressions"""

    def __init__(self):
        super().__init__()
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

        return True

    def start(self) -> bool:
        return True

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
        Kills qalc if it runs longer than 5 seconds.
        """
        # Strip leading = if present
        if expression.startswith("="):
            expression = expression[1:].strip()

        try:
            # Use qalc for calculation with a timeout
            process = subprocess.run(
                ["qalc", "-t", expression],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            result = process.stdout.strip()
            return result

        except subprocess.TimeoutExpired:
            logger.warning("qalc process timed out and was killed after 5 seconds")
            return None
        except Exception:
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
            icon_spec="theme://qalculate",
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
