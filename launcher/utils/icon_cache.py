import threading
from typing import Any, Optional

from gi.repository import GdkPixbuf


class IconCache:
    """
    Thread-safe cache for icons to reduce file system access and memory usage.
    """

    def __init__(self, maxsize: int = 128):
        self._cache = {}
        self._lock = threading.Lock()
        self.maxsize = maxsize

    def get(self, icon_spec: Any, size: int) -> Optional[GdkPixbuf.Pixbuf]:
        """
        Get an icon from the cache.

        Args:
            icon_spec: The icon specification (could be a path, name, etc.)
            size: The size of the icon

        Returns:
            The cached icon or None if not found
        """
        with self._lock:
            key = (str(icon_spec), size)
            return self._cache.get(key)

    def set(self, icon_spec: Any, size: int, pixbuf: GdkPixbuf.Pixbuf) -> None:
        """
        Set an icon in the cache.

        Args:
            icon_spec: The icon specification (could be a path, name, etc.)
            size: The size of the icon
            pixbuf: The pixbuf to cache
        """
        with self._lock:
            key = (str(icon_spec), size)
            # If cache is full, remove oldest entry (this is simplified)
            # In a real implementation, we might want to use an ordered dict
            # to properly implement LRU, but for this implementation we'll just
            # remove a random key if needed
            if len(self._cache) >= self.maxsize:
                # Remove the first key in the cache (not true LRU but sufficient for now)
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            self._cache[key] = pixbuf

    def clear(self) -> None:
        """Clear the cache."""
        with self._lock:
            self._cache.clear()


# Global instance of the icon cache
ICON_CACHE = IconCache()
