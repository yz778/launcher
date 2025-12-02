from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from launcher.core.config import AttrDict, ConfigManager
    from launcher.core.history_manager import HistoryManager
    from launcher.core.ipc import IPCManager
    from launcher.core.plugin_manager import PluginManager
    from launcher.ui.css_manager import CssManager
    from launcher.ui.launcher_window import LauncherWindow


class Services:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Services, cls).__new__(cls)
            cls._instance.config: Optional["AttrDict"] = None
            cls._instance.config_manager: Optional["ConfigManager"] = None
            cls._instance.css_manager: Optional["CssManager"] = None
            cls._instance.history_manager: Optional["HistoryManager"] = None
            cls._instance.ipc_manager: Optional["IPCManager"] = None
            cls._instance.launcher_window: Optional["LauncherWindow"] = None
            cls._instance.plugin_manager: Optional["PluginManager"] = None
        return cls._instance


# Global singleton instance
instance = Services()
