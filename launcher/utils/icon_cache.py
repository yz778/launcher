import threading
from collections import OrderedDict
from typing import Any, Optional

from gi.repository import GdkPixbuf


class IconCache:
    """
    Thread-safe cache for icons to reduce file system access and memory usage.
    """

    def __init__(self, maxsize: int = 128):
        self._cache = OrderedDict()
        self._lock = threading.Lock()
        self.maxsize = maxsize

    def get(self, icon_spec: Any, size: int) -> Optional[GdkPixbuf.Pixbuf]:
        """
        Get an icon from the cache and mark it as recently used.

        Args:
            icon_spec: The icon specification (could be a path, name, etc.)
            size: The size of the icon

        Returns:
            The cached icon or None if not found
        """
        with self._lock:
            key = (str(icon_spec), size)
            if key in self._cache:
                # Move the key to the end to mark it as recently used
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def set(self, icon_spec: Any, size: int, pixbuf: GdkPixbuf.Pixbuf) -> None:
        """
        Set an icon in the cache, evicting the least recently used item if necessary.

        Args:
            icon_spec: The icon specification (could be a path, name, etc.)
            size: The size of the icon
            pixbuf: The pixbuf to cache
        """
        with self._lock:
            key = (str(icon_spec), size)
            if key in self._cache:
                # If key already exists, update it and move to end
                self._cache.move_to_end(key)
            elif len(self._cache) >= self.maxsize:
                # Remove the least recently used item (first item in OrderedDict)
                self._cache.popitem(last=False)
            self._cache[key] = pixbuf

    def clear(self) -> None:
        """Clear the cache."""
        with self._lock:
            self._cache.clear()


# Global instance of the icon cache
ICON_CACHE = IconCache()
