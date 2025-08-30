#!/usr/bin/env python3

from ..base import Plugin, SearchResult
from gi.repository import GLib
from launcher.utils.scoring_system import calculate_match_score
from typing import Dict, List, Any, Optional
import logging
import pyperclip

logger = logging.getLogger(__name__)


class CalculatorPlugin(Plugin):
    """Plugin for calculating mathematical expressions"""

    __slots__ = (
        "icon_size",
        "precision",
        "angle_unit",
        "calculator_icon",
        "_sympy_loaded",
        "_last_valid_result",
        "_sympy",
        "general_config",
    )

    def __init__(self):
        super().__init__()
        self.icon_size = None
        self.precision = 10
        self.angle_unit = "degree"
        self.calculator_icon = None
        self._sympy_loaded = False
        self._last_valid_result = None
        self._sympy = None
        self.general_config = {}

    def get_id(self) -> str:
        return "calculator"

    def get_name(self) -> str:
        return "Calculator"

    def get_description(self) -> str:
        return "Calculate mathematical expressions"

    def get_config_defaults(self) -> Dict[str, Any]:
        """Get default configuration for this plugin"""
        return {
            "precision": 10,
            "angle_unit": "degree",
            "track_history": False,  # Don't track calculator results in history by default
        }

    def initialize(self, config: Dict[str, Any], config_manager) -> bool:
        """Initialize the plugin with the given configuration"""
        super().initialize(config, config_manager)

        # Get icon size using helper
        self.icon_size = self.get_icon_size()

        # Get calculator-specific config using helper
        self.precision = self.get_config_value("precision")
        self.angle_unit = self.get_config_value("angle_unit")

        return True

    def start(self) -> bool:
        """
        Start the plugin and perform any necessary setup work

        This loads the calculator icon. Sympy will be loaded lazily when needed.
        """
        GLib.idle_add(self._load_calculator_icon)
        return True

    def _load_calculator_icon(self) -> bool:
        """Load the calculator icon"""
        from launcher.utils.icon_utils import load_theme_icon

        self.calculator_icon = load_theme_icon("accessories-calculator", self.icon_size)
        return False

    def _is_calculation(self, query: str) -> bool:
        """Check if the query looks like a calculation"""
        if query and query[0] in "=-0123456789()":
            return True

        # If the query starts with common math functions, it's likely a calculation
        math_funcs = ["sin", "cos", "tan", "log", "ln", "sqrt", "abs", "exp"]
        if any(query.lower().startswith(func) for func in math_funcs):
            return True

        return False

    def _get_sympy(self):
        if self._sympy is None:
            try:
                from sympy.parsing.sympy_parser import (
                    parse_expr,
                    standard_transformations,
                    implicit_multiplication_application,
                    function_exponentiation,
                    convert_xor,
                )
                import sympy as _sympy_module  # Import sympy itself for result.has(sympy.sin) etc.

                self._sympy = {
                    "parse_expr": parse_expr,
                    "transformations": (
                        standard_transformations
                        + (implicit_multiplication_application,)
                        + (function_exponentiation,)
                        + (convert_xor,)
                    ),
                    "sympy_module": _sympy_module,  # Store the sympy module itself
                }
                self._sympy_loaded = True
                logger.info("Sympy loaded successfully (lazy).")
            except ImportError:
                logger.error(
                    "Sympy library not found. Please install it with 'pip install sympy'."
                )
                self._sympy_loaded = False
                return None
        return self._sympy

    def _calculate(self, expression: str) -> Optional[str]:
        """
        Calculate the result of the expression using sympy

        Returns None if calculation fails
        """
        sympy_lib = self._get_sympy()
        if sympy_lib is None:
            return None

        # Strip leading = if present
        if expression.startswith("="):
            expression = expression[1:].strip()

        try:
            # Convert ^ to ** for exponentiation
            expression = expression.replace("^", "**")

            # Parse and evaluate the expression with sympy
            result = sympy_lib["parse_expr"](
                expression, transformations=sympy_lib["transformations"]
            )

            # Apply angle unit conversion for trigonometric functions if needed
            if (
                self.angle_unit.lower() == "degree"
                and hasattr(result, "has")
                and (
                    result.has(sympy_lib["sympy_module"].sin)
                    or result.has(sympy_lib["sympy_module"].cos)
                    or result.has(sympy_lib["sympy_module"].tan)
                )
            ):
                # Convert result to radians for sympy (which uses radians by default)
                result = result.evalf()

            # Convert to float for numerical results if possible
            try:
                float_result = float(result.evalf())
                # Format based on whether it's an integer or float
                if float_result.is_integer():
                    return str(int(float_result))
                else:
                    return str(round(float_result, self.precision))
            except Exception:
                # Return the symbolic result if it can't be converted to float
                return str(result)
        except Exception as e:
            return None

    def search(self, query: str) -> List[SearchResult]:
        """Search for calculations matching the query"""
        # Check if this is a calculation
        if not query or not self._is_calculation(query):
            return []

        # Ensure the icon is loaded before creating the result
        if self.calculator_icon is None:
            self._load_calculator_icon()

        # Try to calculate
        result = self._calculate(query)

        # If calculation failed but we have a previous valid result, show that
        if result is None:
            if self._last_valid_result is None:
                return []

            # Use last valid result but maintain current expression
            result = self._last_valid_result
        else:
            # Store this valid result
            self._last_valid_result = result

        # Strip leading = for display if present
        display_query = query
        if display_query.startswith("="):
            display_query = display_query[1:].strip()

        # Create a search result
        search_result = SearchResult(
            plugin_id=self.get_id(),
            item_id=query,
            name=result,
            description=query,
            icon=self.calculator_icon,
            score=calculate_match_score(query, result, is_name=True),
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

        # Get the result from metadata
        calc_result = result.metadata.get("result", "")
        if not calc_result:
            return False

        # Copy the result to clipboard using pyperclip (works better with Wayland)
        try:
            pyperclip.copy(calc_result)
            logger.info(f"Copied calculation result to clipboard: {calc_result}")
            return True
        except Exception as e:
            logger.error(f"Error copying to clipboard: {e}")
            return False
