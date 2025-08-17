#!/usr/bin/env python3


from gi.repository import Gtk, GdkPixbuf
from typing import Optional, List, Dict
import hashlib
import logging
import os
import urllib.parse
import urllib.request

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
    icon_spec: str,
    size: int,
    cache: Dict[str, GdkPixbuf.Pixbuf] = None,
    cache_dir: str = None,
) -> Optional[GdkPixbuf.Pixbuf]:
    """
    Load custom icon from file path, URL, or theme name with caching

    Args:
        icon_spec: Icon specification (file path, URL, or theme name)
        size: Icon size in pixels
        cache: Optional cache dictionary to store loaded icons
        cache_dir: Directory for storing downloaded URL icons

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
        # Check if it's a URL
        if icon_spec.startswith(("http://", "https://")):
            loaded_icon = _load_icon_from_url(icon_spec, size, cache_dir)
        # Check if it's a file path (contains / or common image extensions)
        elif "/" in icon_spec or icon_spec.endswith(
            (
                ".png",
                ".svg",
                ".jpg",
                ".jpeg",
                ".ico",
                ".gif",
                ".bmp",
                ".tiff",
                ".tif",
                ".webp",
            )
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


def _load_icon_from_url(
    icon_url: str, size: int, cache_dir: str = None
) -> Optional[GdkPixbuf.Pixbuf]:
    """
    Load icon from URL with local caching

    Args:
        icon_url: URL of the icon to download
        size: Icon size in pixels
        cache_dir: Directory to store cached icons

    Returns:
        Loaded icon pixbuf or None if loading fails
    """
    if not cache_dir:
        # Use default cache directory if not provided
        from xdg_base_dirs import xdg_cache_home

        cache_dir = os.path.join(xdg_cache_home(), "launcher", "url_icons")

    # Create cache directory if it doesn't exist
    os.makedirs(cache_dir, exist_ok=True)

    # Generate cache filename based on URL hash
    url_hash = hashlib.sha256(icon_url.encode()).hexdigest()[:16]
    parsed_url = urllib.parse.urlparse(icon_url)
    file_ext = os.path.splitext(parsed_url.path)[1].lower()

    # Validate and normalize file extension
    supported_extensions = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".ico",
        ".bmp",
        ".tiff",
        ".tif",
        ".webp",
    }
    if file_ext not in supported_extensions:
        file_ext = ".png"  # Default to PNG if extension is unknown or unsupported

    cache_filename = f"{url_hash}{file_ext}"
    cache_path = os.path.join(cache_dir, cache_filename)

    # Check if icon is already cached
    if os.path.isfile(cache_path):
        logger.debug(f"Loading cached URL icon: {cache_path}")
        try:
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(cache_path, size, size, True)
        except Exception as e:
            logger.warning(f"Failed to load cached icon {cache_path}: {e}")
            # Remove corrupted cache file
            try:
                os.remove(cache_path)
            except:
                pass

    # Download icon from URL
    logger.debug(f"Downloading icon from URL: {icon_url}")
    try:
        # Set a reasonable timeout and user agent
        request = urllib.request.Request(
            icon_url, headers={"User-Agent": "Launcher/1.0"}
        )

        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status == 200:
                content_type = response.headers.get("content-type", "").lower()
                if not content_type.startswith("image/"):
                    logger.warning(
                        f"URL does not return an image (content-type: {content_type}): {icon_url}"
                    )
                    return None

                # Read content with size limit (5MB max)
                content = response.read(5 * 1024 * 1024)  # 5MB limit

                # Determine correct file extension from content-type if possible
                content_type_to_ext = {
                    "image/png": ".png",
                    "image/jpeg": ".jpg",
                    "image/jpg": ".jpg",
                    "image/gif": ".gif",
                    "image/svg+xml": ".svg",
                    "image/x-icon": ".ico",
                    "image/vnd.microsoft.icon": ".ico",
                    "image/bmp": ".bmp",
                    "image/tiff": ".tiff",
                    "image/webp": ".webp",
                }

                # Update cache path if we can determine a better extension from content-type
                if content_type in content_type_to_ext:
                    correct_ext = content_type_to_ext[content_type]
                    if not cache_path.endswith(correct_ext):
                        cache_filename = f"{url_hash}{correct_ext}"
                        cache_path = os.path.join(cache_dir, cache_filename)

                # Save to cache
                with open(cache_path, "wb") as f:
                    f.write(content)

                logger.debug(
                    f"Successfully cached icon from {icon_url} to {cache_path} (content-type: {content_type})"
                )

                # Load and return the icon
                return GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    cache_path, size, size, True
                )
            else:
                logger.warning(
                    f"HTTP {response.status} when downloading icon: {icon_url}"
                )

    except urllib.error.URLError as e:
        logger.error(f"Network error downloading icon from {icon_url}: {e}")
    except Exception as e:
        logger.error(f"Error downloading icon from {icon_url}: {e}")
        # Clean up partial download
        try:
            if os.path.exists(cache_path):
                os.remove(cache_path)
        except:
            pass

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
