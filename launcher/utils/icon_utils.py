#!/usr/bin/env python3

import os
import logging
from typing import Optional, List, Dict, Any

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf

logger = logging.getLogger(__name__)


def load_theme_icon(
    icon_name: str, size: int, fallback_names: List[str] = None
) -> Optional[GdkPixbuf.Pixbuf]:
    """
    Load an icon from the theme with fallback options

    Args:
        icon_name: Primary icon name to load
        size: Icon size in pixels
        fallback_names: List of fallback icon names to try if primary fails

    Returns:
        Loaded icon pixbuf or None if all attempts fail
    """
    if not icon_name or size <= 0:
        return None

    icon_theme = Gtk.IconTheme.get_default()
    fallback_names = fallback_names or []

    # Try primary icon name first
    for name in [icon_name] + fallback_names:
        try:
            return icon_theme.load_icon(name, size, 0)
        except Exception as e:
            logger.debug(f"Failed to load icon '{name}': {e}")
            continue

    logger.warning(
        f"Could not load any icon for '{icon_name}' with fallbacks {fallback_names}"
    )
    return None


def load_custom_icon(
    icon_spec: str, size: int, cache: Dict[str, GdkPixbuf.Pixbuf] = None
) -> Optional[GdkPixbuf.Pixbuf]:
    """
    Load custom icon from file path or theme name with caching

    Args:
        icon_spec: Icon specification (file path or theme name)
        size: Icon size in pixels
        cache: Optional cache dictionary to store loaded icons

    Returns:
        Loaded icon pixbuf or None if loading fails
    """
    if not icon_spec or size <= 0:
        return None

    # Check cache first if provided
    if cache is not None and icon_spec in cache:
        return cache[icon_spec]

    loaded_icon = None

    try:
        # Check if it's a file path (contains / or common image extensions)
        if "/" in icon_spec or icon_spec.endswith(
            (".png", ".svg", ".jpg", ".jpeg", ".ico")
        ):
            loaded_icon = _load_icon_from_file(icon_spec, size)
        else:
            # Try as theme icon name
            loaded_icon = _load_icon_from_theme(icon_spec, size)

        # Cache the result if cache is provided
        if cache is not None and loaded_icon is not None:
            cache[icon_spec] = loaded_icon

    except Exception as e:
        logger.error(f"Error loading custom icon '{icon_spec}': {e}")

    return loaded_icon


def _load_icon_from_file(icon_path: str, size: int) -> Optional[GdkPixbuf.Pixbuf]:
    """Load icon from file path with search in common directories"""
    expanded_path = os.path.expanduser(icon_path)

    # If not absolute path, search in common icon directories
    if not os.path.isabs(expanded_path):
        search_paths = [
            os.path.join(os.path.expanduser("~/.local/share/icons"), expanded_path),
            os.path.join("/usr/share/icons", expanded_path),
            os.path.join("/usr/share/pixmaps", expanded_path),
            expanded_path,
        ]

        for path in search_paths:
            if os.path.isfile(path):
                expanded_path = path
                break
        else:
            logger.warning(f"Icon file not found: {icon_path}")
            return None

    if not os.path.isfile(expanded_path):
        logger.warning(f"Icon file not found: {expanded_path}")
        return None

    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_scale(expanded_path, size, size, True)
    except Exception as e:
        logger.error(f"Error loading icon from file '{expanded_path}': {e}")
        return None


def _load_icon_from_theme(icon_name: str, size: int) -> Optional[GdkPixbuf.Pixbuf]:
    """Load icon from theme with fallback names"""
    fallback_names = [
        f"{icon_name}-symbolic",
        f"application-{icon_name}",
        f"{icon_name}-icon",
    ]

    return load_theme_icon(icon_name, size, fallback_names)


def get_fallback_icon(
    size: int, icon_name: str = "application-x-executable"
) -> Optional[GdkPixbuf.Pixbuf]:
    """
    Get a fallback icon for when specific icons can't be loaded

    Args:
        size: Icon size in pixels
        icon_name: Fallback icon name (default: application-x-executable)

    Returns:
        Fallback icon or None if even fallback fails
    """
    fallback_names = [
        "application-x-executable",
        "utilities-terminal",
        "applications-other",
        "text-x-generic",
    ]

    return load_theme_icon(icon_name, size, fallback_names)
