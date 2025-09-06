import logging
import os

from gi.repository import Gdk, Gtk

logger = logging.getLogger(__name__)


class CssManager:
    DEFAULT_CSS = ""

    @staticmethod
    def load_default_css():
        """Load default.css exists"""
        dir_path = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(dir_path, "default.css")
        CssManager._load_css_from_file(file_path)

    @classmethod
    def load_css(cls, config, plugins: dict = None) -> None:
        """Load CSS styling from default, plugin, and custom sources"""
        css_path = None
        if config and hasattr(config, "system"):
            css_path = config.system.css_file

        logger.info("Loading default CSS styling")
        cls._load_css_from_string(cls.DEFAULT_CSS)

        if plugins:
            plugin_css = cls._combine_plugin_css(plugins)
            if plugin_css:
                logger.info("Loading CSS from plugins")
                cls._load_css_from_string(plugin_css)

        if css_path and os.path.isfile(css_path):
            logger.info(f"Loading custom CSS from file: {css_path}")
            cls._load_css_from_file(css_path)

    @classmethod
    def get_css(cls, plugins: dict = None) -> str:
        """Get combined CSS content from all sources"""
        css_content = cls.DEFAULT_CSS

        if plugins:
            plugin_css = cls._combine_plugin_css(plugins)
            if plugin_css:
                css_content += "\n\n" + plugin_css

        return css_content

    @staticmethod
    def _load_css_from_file(css_path: str) -> None:
        """Load and apply CSS from a file"""
        style_provider = Gtk.CssProvider()
        style_provider.load_from_path(css_path)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    @staticmethod
    def _load_css_from_string(css_string: str) -> None:
        """Load and apply CSS from a string"""
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css_string.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

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
