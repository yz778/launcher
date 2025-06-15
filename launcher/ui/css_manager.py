#!/usr/bin/env python3

import os
import logging
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk

logger = logging.getLogger(__name__)


class CssManager:
    """Manages CSS styling from default, plugin, and custom sources"""

    # Default CSS styling
    DEFAULT_CSS = """/* Window styling */
#launcher-window {
    background: #23272e;
    border: 1.5px solid #44475a;
    padding: 0;
}

/* Entry styling */
#launcher-entry-container {
    background: #23272e;
    padding: 10px;
}

#launcher-entry {
    color: #f8f8f2;
    background: transparent;
    border: none;
    font-size: 20px;
    padding: 0;
    margin: 0;
    box-shadow: none;
    outline: none;
}

#result-count-label {
    background: transparent;
    color: #808080;
    font-size: 10px;
    font-style: italic;
    padding: 0 0 0 5px;
    margin: 0;
    border: none;
    border-radius: 0;
}

/* Results list styling */
#results-scrolled {
    background: transparent;
    border: none;
    margin-top: 5px;
}

#results-list {
    background: transparent;
    border: none;
}

#app-list-item {
    padding: 8px;
    border-radius: 6px;
    transition: background-color 0.15s ease;
    min-height: 40px; /* Ensure minimum height */
}

#app-list-item:hover {
    background-color: rgba(60, 80, 120, 0.4);
}

#app-list-item:selected {
    background-color: rgba(80, 100, 140, 0.6);
}

/* History item styling */
#history-item {
    padding: 8px;
    border-radius: 6px;
    min-height: 40px;
}

#history-item:hover {
    background-color: rgba(100, 100, 100, 0.3);
}

#history-item:selected {
    background-color: rgba(120, 120, 120, 0.4);
}

#history-icon {
    color: #a0a0a0;
    font-size: 18px;
}

#history-text {
    color: #e0e0e0;
    font-size: 16px;
    font-style: italic;
}

#app-name {
    color: #f8f8f2;
    font-size: 16px;
    font-weight: bold;
}

#app-description {
    color: #a0a0a0;
    font-size: 12px;
}

#app-count {
    color: #808080;
    font-size: 10px;
    font-style: italic;
}

/* Scrollbar styling */
scrollbar {
    background-color: transparent;
    border: none;
}

scrollbar slider {
    min-width: 6px;
    min-height: 6px;
    border-radius: 3px;
    background-color: rgba(150, 150, 150, 0.4);
}

scrollbar slider:hover {
    background-color: rgba(150, 150, 150, 0.6);
}

scrollbar slider:active {
    background-color: rgba(150, 150, 150, 0.8);
}"""

    @classmethod
    def load_css(cls, config: dict = None, plugins: dict = None) -> None:
        """Load CSS styling from default, plugin, and custom sources"""
        css_path = None
        if config and "general" in config and "css_file" in config["general"]:
            css_path = os.path.expanduser(config["general"]["css_file"])

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
        else:
            logger.debug("No custom CSS file found or specified")

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
