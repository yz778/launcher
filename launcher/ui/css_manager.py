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
        self.main_provider: Optional[Gtk.CssProvider] = None
        self.transition_provider: Optional[Gtk.CssProvider] = None
        self._transition_timeout_id = None
        self._highlight_color: Optional[str] = None
        self._highlight_weight: Optional[str] = None
        self._last_final_css: Optional[str] = None  # Cache for last applied CSS

    def load_all_styles(
        self,
        theme_name: str,
        plugins: Optional[dict] = None,
        with_transition: bool = False,
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

            final_css = "\n\n".join(
                [
                    self._load_base_styles(),
                    self._load_plugin_styles(plugins),
                    self._load_theme_styles(theme_name),
                ]
            )

            # Only apply if CSS has changed
            if self._last_final_css != final_css:
                self._apply_css_string(final_css)
                self._last_final_css = final_css
                logger.info(f"Applied consolidated CSS for theme: {theme_name}")
            else:
                logger.info(
                    f"CSS unchanged for theme: {theme_name}, skipping re-apply."
                )

            return True

        except Exception as e:
            logger.error(f"Error loading styles with theme {theme_name}: {e}")
            return False

    def get_available_themes(self) -> List[Dict[str, str]]:
        """Get list of available themes with display names

        Returns:
            List of dicts with 'name' and 'display_name' keys (sorted by name)
        """
        themes_list = []
        theme_paths = [
            os.path.join(os.path.dirname(__file__), "../themes"),
            os.path.join(xdg_config_home(), "launcher", "themes"),
        ]

        for dir in theme_paths:
            if not os.path.exists(dir):
                continue

            for file in os.listdir(dir):
                if not file.endswith(".css"):
                    continue

                theme_name = os.path.splitext(file)[0]
                display_name = theme_name
                try:
                    path = os.path.join(dir, file)
                    with open(path, "r", encoding="utf-8") as f:
                        first_line = f.readline().strip()
                        if first_line.startswith("/*") and first_line.endswith("*/"):
                            extracted = first_line[2:-2].strip()
                            if extracted:
                                display_name = extracted

                except Exception as e:
                    logger.error(f"Unable to read {file}: {e}")
                    pass

                themes_list.append({"name": theme_name, "display_name": display_name})

        return sorted(themes_list, key=lambda x: x["name"])

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
        win.destroy()

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

        return self._highlight_color, self._highlight_weight

    def _clear_providers(self):
        """Remove all CSS providers from the screen"""
        screen = Gdk.Screen.get_default()

        if self.main_provider:
            Gtk.StyleContext.remove_provider_for_screen(screen, self.main_provider)
            self.main_provider = None

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
        # Clear last applied CSS cache
        self._last_final_css = None

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

    def _apply_css_string(self, css: str):
        """Apply the CSS to a single provider."""
        screen = Gdk.Screen.get_default()

        # Remove the old provider if it exists
        if self.main_provider:
            Gtk.StyleContext.remove_provider_for_screen(screen, self.main_provider)

        self.main_provider = Gtk.CssProvider()
        self.main_provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(
            screen, self.main_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _load_base_styles(self) -> str:
        """Load and return the content of the base default styles."""
        default_theme_path = os.path.realpath(self._find_theme_file("default"))
        if default_theme_path and os.path.exists(default_theme_path):
            try:
                with open(default_theme_path, "r", encoding="utf-8") as f:
                    logger.info(f"Loaded base CSS: {default_theme_path}")
                    return f.read()
            except Exception as e:
                logger.error(f"Error reading base style file: {e}")
        else:
            logger.warning("Default theme file not found for base styles")
        return ""

    def _load_plugin_styles(self, plugins: Optional[dict]) -> str:
        """Load and return combined plugin styles."""
        plugin_css = self._combine_plugin_css(plugins)
        if plugin_css:
            logger.info("Loaded plugin CSS styles")
        return plugin_css

    def _load_theme_styles(self, theme_name: str) -> str:
        """Load and return the content of the theme styles."""
        if theme_name == "default":
            logger.info(
                "Skipping theme load for 'default' as it's already included in base styles"
            )
            return ""

        theme_path = os.path.realpath(self._find_theme_file(theme_name))
        if theme_path and os.path.exists(theme_path):
            try:
                with open(theme_path, "r", encoding="utf-8") as f:
                    logger.info(f"Loaded theme CSS: {theme_path}")
                    return f.read()
            except Exception as e:
                logger.error(f"Error reading theme file {theme_name}: {e}")
        else:
            logger.warning(f"Theme file not found: {theme_name}")
        return ""

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
    def _combine_plugin_css(plugins: Optional[dict] = None) -> str:
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
