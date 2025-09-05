#!/usr/bin/env python3

from gi.repository import Gtk, GdkPixbuf
from typing import Optional, List, Dict
from xdg_base_dirs import xdg_cache_home
from xdg.IconTheme import getIconPath
import hashlib
import logging
import os
import urllib.parse
import urllib.request


logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_EXTENSIONS = (
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
        except Exception:
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
    Load custom icon with URI scheme support and caching

    Args:
        icon_spec: Icon specification with URI scheme support:
                  - desktop://icon_name for desktop file icons
                  - theme://icon_name for theme icons
                  - file:///path/to/icon for file paths
                  - http://example.com/icon.png for URLs
                  - Plain strings are treated as theme icons for backward compatibility
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
        # Handle URI schemes
        if icon_spec.startswith("desktop://"):
            icon_name = icon_spec[10:]
            loaded_icon = load_desktop_file_icon(icon_name, size)
        elif icon_spec.startswith("theme://"):
            icon_name = icon_spec[8:]
            loaded_icon = _load_icon_from_theme(icon_name, size)
        elif icon_spec.startswith(("http://", "https://")):
            loaded_icon = _load_icon_from_url(icon_spec, size, cache_dir)
        elif icon_spec.startswith("file://"):
            file_path = icon_spec[7:]
            loaded_icon = _load_icon_from_file(file_path, size)
        elif "/" in icon_spec or icon_spec.endswith(SUPPORTED_IMAGE_EXTENSIONS):
            loaded_icon = _load_icon_from_file(icon_spec, size)
        else:
            loaded_icon = _load_icon_from_theme(icon_spec, size)

        if cache is not None and loaded_icon is not None:
            cache[icon_spec] = loaded_icon

    except Exception as e:
        logger.error(f"Error loading custom icon '{icon_spec}': {e}")

    return loaded_icon


def _load_icon_from_file(icon_path: str, size: int) -> Optional[GdkPixbuf.Pixbuf]:
    """Load icon from file path with search in common directories"""
    expanded_path = os.path.expanduser(icon_path)

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
        cache_dir = os.path.join(xdg_cache_home(), "launcher", "url_icons")

    os.makedirs(cache_dir, exist_ok=True)

    url_hash = hashlib.sha256(icon_url.encode()).hexdigest()[:16]
    parsed_url = urllib.parse.urlparse(icon_url)
    file_ext = os.path.splitext(parsed_url.path)[1].lower()

    if file_ext not in SUPPORTED_IMAGE_EXTENSIONS:
        file_ext = ".png"

    cache_filename = f"{url_hash}{file_ext}"
    cache_path = os.path.join(cache_dir, cache_filename)

    # Check if icon is already cached
    if os.path.isfile(cache_path):
        try:
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(cache_path, size, size, True)
        except Exception as e:
            logger.warning(f"Failed to load cached icon {cache_path}: {e}")
            try:
                os.remove(cache_path)
            except Exception:
                pass

    # Download icon from URL
    try:
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

                content = response.read(5 * 1024 * 1024)  # 5MB limit

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

                if content_type in content_type_to_ext:
                    correct_ext = content_type_to_ext[content_type]
                    if not cache_path.endswith(correct_ext):
                        cache_filename = f"{url_hash}{correct_ext}"
                        cache_path = os.path.join(cache_dir, cache_filename)

                with open(cache_path, "wb") as f:
                    f.write(content)

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
        try:
            if os.path.exists(cache_path):
                os.remove(cache_path)
        except Exception:
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


def normalize_icon_spec(icon_spec: str) -> str:
    """
    Normalize an icon specification to use proper URI schemes.

    Args:
        icon_spec: Raw icon specification (may or may not have URI scheme)

    Returns:
        Normalized icon specification with appropriate URI scheme
    """

    if not icon_spec:
        return "theme://application-x-executable"
    elif icon_spec.startswith(
        ("desktop://", "theme://", "file://", "http://", "https://")
    ):
        return icon_spec
    elif "/" in icon_spec or icon_spec.endswith(SUPPORTED_IMAGE_EXTENSIONS):
        return f"file://{icon_spec}"
    else:
        return f"theme://{icon_spec}"


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


def load_desktop_file_icon(icon_spec: str, size: int) -> Optional[GdkPixbuf.Pixbuf]:
    """
    Load icon for a desktop file with desktop-specific fallback logic

    Args:
        icon_spec: Icon specification from desktop file (path, theme name, etc.)
        size: Icon size in pixels

    Returns:
        Loaded icon pixbuf or fallback icon
    """
    if not icon_spec:
        return _get_desktop_fallback_icon(size)

    try:
        if os.path.isfile(icon_spec):
            return GdkPixbuf.Pixbuf.new_from_file_at_size(icon_spec, size, size)

        pixbuf = _load_desktop_icon_from_xdg_theme(icon_spec, size)
        if pixbuf:
            return pixbuf

        pixbuf = _load_desktop_icon_from_gtk_theme(icon_spec, size)
        if pixbuf:
            return pixbuf

        return _get_desktop_fallback_icon(size)

    except Exception as e:
        logger.error(f"Error loading desktop file icon {icon_spec}: {e}")
        return _get_desktop_fallback_icon(size)


def _load_desktop_icon_from_xdg_theme(
    icon_name: str, size: int
) -> Optional[GdkPixbuf.Pixbuf]:
    """Load desktop icon from XDG icon theme"""
    try:
        icon_path = getIconPath(icon_name, size)

        if not icon_path and "." in icon_name:
            icon_name_no_ext = os.path.splitext(icon_name)[0]
            icon_path = getIconPath(icon_name_no_ext, size)

        if icon_path:
            try:
                return GdkPixbuf.Pixbuf.new_from_file_at_size(icon_path, size, size)
            except Exception:
                pass

    except ImportError:
        pass
    except Exception:
        pass

    return None


def _load_desktop_icon_from_gtk_theme(
    icon_name: str, size: int
) -> Optional[GdkPixbuf.Pixbuf]:
    """Load desktop icon from GTK icon theme"""
    try:
        icon_theme = Gtk.IconTheme.get_default()

        if icon_theme.has_icon(icon_name):
            try:
                return icon_theme.load_icon(icon_name, size, 0)
            except Exception:
                pass

        if "." in icon_name:
            icon_name_no_ext = os.path.splitext(icon_name)[0]
            if icon_theme.has_icon(icon_name_no_ext):
                try:
                    return icon_theme.load_icon(icon_name_no_ext, size, 0)
                except Exception:
                    pass

    except Exception:
        pass

    return None


def _get_desktop_fallback_icon(size: int) -> Optional[GdkPixbuf.Pixbuf]:
    """Get fallback icon for desktop files"""
    try:
        icon_theme = Gtk.IconTheme.get_default()
        return icon_theme.load_icon("application-x-executable", size, 0)
    except Exception:
        return None


def ensure_correct_icon_size(
    pixbuf: Optional[GdkPixbuf.Pixbuf], size: int
) -> Optional[GdkPixbuf.Pixbuf]:
    """Ensure pixbuf is the correct size"""
    if not pixbuf:
        return pixbuf

    if pixbuf.get_width() != size or pixbuf.get_height() != size:
        return pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)

    return pixbuf
