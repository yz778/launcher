import gi
from gi.repository import Gtk, GLib

gi.require_version("Gtk", "3.0")


def run_main_loop():
    """Run the UI main loop if available."""
    Gtk.main()


def process_pending_events():
    """Process pending UI events once (used during startup)."""
    while Gtk.events_pending():
        Gtk.main_iteration()


def idle_add(func):
    """Schedule a function to run when idle in the UI main loop."""
    return GLib.idle_add(func)
