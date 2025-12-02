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


# Global instance for backward compatibility and easy access
# Usage: from launcher import services; services.config = ...
# This allows existing code like `services.config` to work if we replace the module lookup
# BUT, `services.config` in the old code referred to the module-level variable `config`.
# To maintain compatibility without changing every import site immediately, we can keep the module-level variables
# OR we can rely on the fact that `import launcher.services as services` results in `services` being the module.
# If we want `services.config` to work, we need `config` to be a variable in this module.
# However, the goal is to use the class.
# Let's try to make it a hybrid or just switch to the class instance.
# Since I am updating the codebase, I should update the usages too.
# But to be safe and "modernize", I will make `services` module expose the instance members if possible,
# or just expect the code to use the instance.
# Actually, the plan said "Replace the module-level global variables with a Services singleton class."
# So I will create the class and an instance of it.

sys_modules_workaround = True

# To make `from launcher import services` work such that `services.config` accesses the instance attribute,
# we can't easily replace the module object itself in a standard way without hacks.
# However, the existing code does `from launcher import services` and then `services.config`.
# If I keep the module structure but change how it holds data, that's safest.
# But a class is better for typing.
# Let's define the class, and then create a global instance named `_services_instance`.
# And then we can use properties or just require updating the call sites.
# The plan implies updating call sites. "Update initialization logic to use the new Services class."

# Let's stick to the plan: Create the class.
# I will also instantiate it as `instance`.
# And I will try to keep the global variables as proxies or just remove them and update the code.
# Updating the code is cleaner.

instance = Services()
