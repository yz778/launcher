# UI loop abstractions to keep __main__ free of Gtk imports
try:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib
except Exception:  # pragma: no cover - only during non-GUI ops
    Gtk = None
    GLib = None


def run_main_loop():
    """Run the UI main loop if available."""
    if Gtk is None:
        return
    Gtk.main()


def process_pending_events():
    """Process pending UI events once (used during startup)."""
    if Gtk is None:
        return
    while Gtk.events_pending():
        Gtk.main_iteration()


def idle_add(func):
    """Schedule a function to run when idle in the UI main loop."""
    if GLib is None:
        return None
    return GLib.idle_add(func)
