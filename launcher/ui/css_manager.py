import logging
import os
from typing import Dict, List, Optional

from gi.repository import Gdk, GLib, Gtk
from xdg_base_dirs import xdg_config_home

logger = logging.getLogger(__name__)


class CssManager:
    """Manages CSS styles with support for dynamic theme switching"""

    def __init__(self):
        """Initialize the CSS manager"""
        self.base_provider: Optional[Gtk.CssProvider] = None
        self.plugin_provider: Optional[Gtk.CssProvider] = None
        self.theme_provider: Optional[Gtk.CssProvider] = None
        self.transition_provider: Optional[Gtk.CssProvider] = None
        self._transition_timeout_id = None
        self._highlight_color: Optional[str] = None
        self._highlight_weight: Optional[str] = None

    def load_all_styles(
        self, theme_name: str, plugins: dict = None, with_transition: bool = False
    ) -> bool:
        """Load and apply all styles from scratch

        Args:
            theme_name: Name of the theme to apply
            plugins: Dictionary of loaded plugins
            with_transition: Whether to apply a temporary transition style

        Returns:
            True if successful, False otherwise
        """
        try:
            # Clear all previously added application-level CSS providers
            self._clear_providers()

            # If requested, apply a global transition for the theme change
            if with_transition:
                self._apply_transition_styles()

            # Load and apply base styles (default.css)
            self._load_base_styles()

            # Load and apply all plugin styles
            if plugins:
                self._load_plugin_styles(plugins)

            # Load and apply the specified theme
            self._load_theme_styles(theme_name)

            logger.info(f"Successfully loaded all styles with theme: {theme_name}")
            return True

        except Exception as e:
            logger.error(f"Error loading styles with theme {theme_name}: {e}")
            return False

    def get_available_themes(self) -> List[Dict[str, str]]:
        """Get list of available themes with display names

        Returns:
            List of dicts with 'name' and 'display_name' keys (sorted by name)
        """
        themes: List[Dict[str, str]] = []

        def add_theme_if_unique(theme_name: str, themes_list: List[Dict[str, str]]):
            # Avoid duplicates by name
            if any(t["name"] == theme_name for t in themes_list):
                return

            display_name = theme_name  # Fallback
            path = self.get_theme_path(theme_name)

            if path and os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        first_line = f.readline().strip()
                        if first_line.startswith("/*") and first_line.endswith("*/"):
                            extracted = first_line[2:-2].strip()
                            if extracted:
                                display_name = extracted
                except Exception as e:
                    logger.error(
                        f"Error reading theme display name for {theme_name}: {e}"
                    )

            themes_list.append({"name": theme_name, "display_name": display_name})

        # Check internal themes directory
        internal_themes_dir = os.path.join(os.path.dirname(__file__), "../themes")
        if os.path.exists(internal_themes_dir):
            for file in os.listdir(internal_themes_dir):
                if file.endswith(".css"):
                    add_theme_if_unique(file[:-4], themes)

        # Check user themes directory (user themes override internal by adding last)
        user_themes_dir = os.path.join(xdg_config_home(), "launcher", "themes")
        if os.path.exists(user_themes_dir):
            for file in os.listdir(user_themes_dir):
                if file.endswith(".css"):
                    add_theme_if_unique(file[:-4], themes)

        return sorted(themes, key=lambda x: x["name"])

    def get_theme_path(self, theme_name: str) -> Optional[str]:
        """Find the path to a theme file

        Args:
            theme_name: Name of the theme (without .css extension)

        Returns:
            Path to the theme file, or None if not found
        """
        theme_filename = f"{theme_name}.css"

        user_themes_dir = os.path.join(xdg_config_home(), "launcher", "themes")
        user_theme_path = os.path.join(user_themes_dir, theme_filename)
        if os.path.exists(user_theme_path):
            return user_theme_path

        internal_themes_dir = os.path.join(os.path.dirname(__file__), "../themes")
        internal_theme_path = os.path.join(internal_themes_dir, theme_filename)
        if os.path.exists(internal_theme_path):
            return internal_theme_path

        return None

    def get_highlight_style(self) -> tuple[str, str]:
        """Get the highlight color and weight from the current theme.

        Returns:
            A tuple containing the highlight color and weight.
        """
        if self._highlight_color and self._highlight_weight:
            return self._highlight_color, self._highlight_weight

        label = Gtk.Label()
        label.get_style_context().add_class("highlight")

        win = Gtk.Window()
        win.add(label)
        win.show_all()

        style_context = label.get_style_context()
        color = style_context.get_color(Gtk.StateFlags.NORMAL)
        weight = style_context.get_property("font-weight", Gtk.StateFlags.NORMAL)

        self._highlight_color = "#%02x%02x%02x" % (
            int(color.red * 255),
            int(color.green * 255),
            int(color.blue * 255),
        )
        self._highlight_weight = "bold" if weight > 400 else "normal"

        # Fallback if the theme doesn't specify a highlight color
        if self._highlight_color == "#000000":
            logger.warning("No highlight color found in theme, using fallback")
            self._highlight_color = "#87CEFA"
            self._highlight_weight = "bold"

        win.destroy()

        return self._highlight_color, self._highlight_weight

    def _clear_providers(self):
        """Remove all CSS providers from the screen"""
        screen = Gdk.Screen.get_default()

        if self.base_provider:
            Gtk.StyleContext.remove_provider_for_screen(screen, self.base_provider)
            self.base_provider = None

        if self.plugin_provider:
            Gtk.StyleContext.remove_provider_for_screen(screen, self.plugin_provider)
            self.plugin_provider = None

        if self.theme_provider:
            Gtk.StyleContext.remove_provider_for_screen(screen, self.theme_provider)
            self.theme_provider = None

        if self._transition_timeout_id:
            GLib.source_remove(self._transition_timeout_id)
            self._transition_timeout_id = None

        if self.transition_provider:
            Gtk.StyleContext.remove_provider_for_screen(
                screen, self.transition_provider
            )
            self.transition_provider = None

        # Clear cached highlight styles
        self._highlight_color = None
        self._highlight_weight = None

    def _apply_transition_styles(self):
        """Applies a global CSS transition and sets a timer to remove it."""
        transition_css = "* { transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease; }"
        self.transition_provider = Gtk.CssProvider()
        self.transition_provider.load_from_data(transition_css.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            self.transition_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_USER,
        )

        self._transition_timeout_id = GLib.timeout_add(
            300, self._remove_transition_styles
        )

    def _remove_transition_styles(self) -> bool:
        """Removes the global transition CSS provider."""
        if self.transition_provider:
            Gtk.StyleContext.remove_provider_for_screen(
                Gdk.Screen.get_default(), self.transition_provider
            )
            self.transition_provider = None
        self._transition_timeout_id = None
        return False  # Stop the timeout from running again

    def _load_base_styles(self):
        """Load base default styles"""
        default_theme_path = self._find_theme_file("default")
        if default_theme_path and os.path.exists(default_theme_path):
            self.base_provider = Gtk.CssProvider()
            self.base_provider.load_from_path(default_theme_path)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                self.base_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                - 1,  # Lower priority than plugins and themes
            )
            logger.info(f"Loaded base CSS: default.css from {default_theme_path}")
        else:
            logger.warning("Default theme file not found for base styles")

    def _load_plugin_styles(self, plugins: dict):
        """Load and apply plugin styles"""
        plugin_css = self._combine_plugin_css(plugins)
        if plugin_css:
            self.plugin_provider = Gtk.CssProvider()
            self.plugin_provider.load_from_data(plugin_css.encode())
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                self.plugin_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
            logger.info("Loaded plugin CSS styles")

    def _load_theme_styles(self, theme_name: str):
        """Load and apply theme styles"""
        if theme_name == "default":
            logger.info(
                "Skipping theme load for 'default' as it's already loaded as base styles"
            )
            return

        theme_path = self._find_theme_file(theme_name)
        if theme_path and os.path.exists(theme_path):
            self.theme_provider = Gtk.CssProvider()
            self.theme_provider.load_from_path(theme_path)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                self.theme_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                + 1,  # Higher priority than plugins
            )
            logger.info(f"Loaded theme CSS: {theme_name} from {theme_path}")
        else:
            logger.warning(f"Theme file not found: {theme_name}")

    def _find_theme_file(self, theme_name: str) -> Optional[str]:
        """Find the path to a theme file

        Args:
            theme_name: Name of the theme (without .css extension)

        Returns:
            Path to the theme file, or None if not found
        """
        theme_filename = f"{theme_name}.css"

        user_themes_dir = os.path.join(xdg_config_home(), "launcher", "themes")
        user_theme_path = os.path.join(user_themes_dir, theme_filename)
        if os.path.exists(user_theme_path):
            return user_theme_path

        internal_themes_dir = os.path.join(os.path.dirname(__file__), "../themes")
        internal_theme_path = os.path.join(internal_themes_dir, theme_filename)
        if os.path.exists(internal_theme_path):
            return internal_theme_path

        return None

    @staticmethod
    def _combine_plugin_css(plugins: dict = None) -> str:
        """Combine and return CSS from all plugins"""
        if not plugins:
            return ""

        combined_css = []

        for plugin_id, plugin in plugins.items():
            try:
                plugin_css = plugin.get_default_css()
                if plugin_css:
                    combined_css.append(f"/* CSS from plugin: {plugin_id} */")
                    combined_css.append(plugin_css)
            except Exception as e:
                logger.error(f"Error getting CSS from plugin {plugin_id}: {e}")

        return "\n\n".join(combined_css)

    def cleanup(self):
        """Clean up CSS providers and resources"""
        self._clear_providers()

    # Legacy methods for backward compatibility
    @classmethod
    def load_css(cls, config, plugins: dict = None) -> None:
        """Legacy method for backward compatibility"""
        manager = cls()
        theme_name = getattr(config.system, "theme", "default")
        manager.load_all_styles(theme_name, plugins)
