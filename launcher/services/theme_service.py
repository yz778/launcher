"""
ThemeService implementation for dependency injection.
"""

from typing import Dict, List, Optional, Tuple

from launcher.services import ThemeServiceProtocol
from launcher.ui.css_manager import CssManager


class ThemeService(ThemeServiceProtocol):
    """Service wrapper for CssManager implementing the ThemeServiceProtocol."""

    def __init__(self):
        """Initialize the theme service."""
        self._css_manager = CssManager()

    def load_theme(
        self,
        theme_name: str,
        plugins: Optional[Dict] = None,
        with_transition: bool = False,
    ) -> bool:
        """Load and apply a theme.

        Args:
            theme_name: Name of the theme to load
            plugins: Dictionary of loaded plugins (optional)
            with_transition: Whether to apply transition effects

        Returns:
            True if theme loaded successfully, False otherwise
        """
        return self._css_manager.load_all_styles(theme_name, plugins, with_transition)

    def get_available_themes(self) -> List[Dict[str, str]]:
        """Get list of available themes.

        Returns:
            List of dicts with 'name' and 'display_name' keys
        """
        return self._css_manager.get_available_themes()

    def get_highlight_style(self) -> Tuple[str, str]:
        """Get the highlight color and weight from the current theme.

        Returns:
            Tuple of (color, weight)
        """
        return self._css_manager.get_highlight_style()

    def cleanup(self) -> None:
        """Clean up theme resources."""
        self._css_manager.cleanup()

    @property
    def css_manager(self) -> CssManager:
        """Get the underlying CssManager instance."""
        return self._css_manager
