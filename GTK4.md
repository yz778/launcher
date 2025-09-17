# GTK4 Migration Plan

This document outlines the steps to migrate the launcher application from GTK3 to GTK4. Since no backward compatibility is required, this plan focuses on a direct, clean migration.

## Phase 1: Project Setup & Dependencies

1.  **Create a New Git Branch:**
    It is crucial to perform the migration in a dedicated branch.
    ```bash
    git checkout -b feature/gtk4-migration
    ```

2.  **Update Dependencies:**
    Modify `requirements.txt` to specify the PyGObject version that supports GTK4. You will also need to ensure the correct GTK4 libraries are installed on your system (`gtk4` package).

    *   **Action:** Update `requirements.txt` to use a modern version of PyGObject. It's recommended to check the PyGObject documentation for the latest stable version.
    *   **Action:** Create a new, clean virtual environment and install the updated dependencies.

3.  **Initial Code Check:**
    After updating dependencies, running the application will fail. The goal of the next phases is to fix these failures. The fundamental change is that `from gi.repository import Gtk` will now import version 4.0 of the library.

## Phase 2: Application Lifecycle (Gtk.Application)

The current application uses a `Gtk.main()` loop. The standard GTK4 approach is to use `Gtk.Application` for better lifecycle management.

1.  **Refactor `launcher.py`:**
    Modify the main `main()` function in `launcher/launcher.py` to use `Gtk.Application`.

    ```python
    # launcher/launcher.py (Example)
    import sys
    from gi.repository import Gtk
    from .ui.launcher_window import LauncherWindow

    class App(Gtk.Application):
        def __init__(self, foreground_mode, **kwargs):
            super().__init__(**kwargs)
            self.foreground_mode = foreground_mode
            self.window = None

        def do_activate(self):
            if not self.window:
                self.window = LauncherWindow(application=self, foreground_mode=self.foreground_mode)
            self.window.show_and_focus()

    def main():
        # ... (config loading etc.)
        app = App(foreground_mode=args.foreground)
        sys.exit(app.run(sys.argv))
    ```

2.  **Update `LauncherWindow`:**
    *   Change `LauncherWindow` to inherit from `Gtk.ApplicationWindow`.
    *   Update its `__init__` method to accept the `application` instance.

    ```python
    # launcher/ui/launcher_window.py
    class LauncherWindow(Gtk.ApplicationWindow):
        def __init__(self, application, foreground_mode: bool = False):
            super().__init__(application=application, title="Launcher")
            # ... rest of the init
    ```

3.  **Replace `Gtk.main_quit()`:**
    The `_schedule_quit` lambda function currently calls `Gtk.main_quit`. This should be changed to call the application's `quit()` method.

    *   **From:** `self._schedule_quit = lambda reason=None: GLib.idle_add(Gtk.main_quit)`
    *   **To:** `self._schedule_quit = lambda reason=None: GLib.idle_add(self.get_application().quit)`

## Phase 3: CSS & Style Management (`css_manager.py`)

The CSS loading mechanism relies on APIs that have changed in GTK4.

1.  **Use `Gdk.Display` instead of `Gdk.Screen`:**
    `Gdk.Screen` is removed in GTK4. You must use `Gdk.Display`.

    *   **Action:** In `_clear_providers`, `_apply_transition_styles`, `_load_base_styles`, etc., replace `Gdk.Screen.get_default()` with `Gdk.Display.get_default()`.

2.  **Update CSS Provider Functions:**
    The screen-based functions are deprecated.

    *   **Action:** Replace `Gtk.StyleContext.add_provider_for_screen(...)` with `Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), ...)`
    *   **Action:** Replace `Gtk.StyleContext.remove_provider_for_screen(...)` with `Gtk.StyleContext.remove_provider_for_display(Gdk.Display.get_default(), ...)`

3.  **Audit and Update All CSS Files:**
    GTK4's CSS engine is stricter, and node/property names have changed. This will be the most time-consuming part.
    *   **Widget Names:** CSS nodes are now lowercase (e.g., `window` instead of `GtkWindow`, `listboxrow` instead of `GtkListBoxRow`).
    *   **Properties:** Some properties like `font` have been replaced by `font-family`, `font-size`, etc.
    *   **Tooling:** Use the GTK Inspector heavily. Run the app with `GTK_DEBUG=interactive` to inspect widgets, see their CSS nodes, and test CSS changes live.
    *   **Files to Check:**
        *   All files in `launcher/themes/`
        *   All `default.css` files within each plugin directory (e.g., `launcher/plugins/commands/default.css`).

## Phase 4: Widget & Windowing API Migration (`launcher_window.py`)

Many widget methods have been replaced with properties or have new names.

1.  **Container `add()`/`remove()`:**
    *   `Gtk.Window.add()` is replaced by `set_child()`.
        *   **From:** `self.add(self.vbox)`
        *   **To:** `self.set_child(self.vbox)`
    *   `Gtk.ScrolledWindow.add()` is replaced by `set_child()`.
        *   **From:** `self.scrolled.add(self.list_box)`
        *   **To:** `self.scrolled.set_child(self.list_box)`
    *   `Gtk.ListBoxRow.add()` is replaced by `set_child()`.
        *   **From:** `self.add(hbox)` in `AppListItem`
        *   **To:** `self.set_child(hbox)`
    *   `Gtk.Box.pack_start()` and `pack_end()` are still valid, but are replaced by `append()` and `prepend()`.

2.  **Child Iteration:**
    `get_children()` is deprecated. Use `get_first_child()` and `get_next_sibling()` in a loop.
    *   **Action:** Refactor `_clear_list_box_and_hide` and `_clear_list_box`.

    ```python
    # Example for _clear_list_box
    child = self.list_box.get_first_child()
    while child:
        next_child = child.get_next_sibling()
        self.list_box.remove(child)
        child = next_child
    ```

3.  **Widget Visibility:**
    `show_all()` is deprecated. Widgets are visible by default. Use `set_visible(True/False)`.
    *   **Action:** Remove all calls to `.show_all()`.
    *   **Action:** Replace `.show()` with `.set_visible(True)` and `.hide()` with `.set_visible(False)`. The logic in `_clear_list_box_and_hide` and `_populate_list_box` will need to be adjusted.

4.  **Scrolled Window Properties:**
    *   `set_policy()` is replaced by properties.
        *   **From:** `self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)`
        *   **To:** `self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)` (This is one of the few that remains the same).
    *   `set_shadow_type()` is deprecated. This is now controlled by CSS (`-gtk-scroll-shadow-type`).
    *   `set_overlay_scrolling()` is deprecated. Control with the `overlay-scrolling` property.
        *   **From:** `self.scrolled.set_overlay_scrolling(False)`
        *   **To:** `self.scrolled.set_property("overlay-scrolling", False)`

5.  **Key/Modifier State:**
    The method for getting modifier state has changed.
    *   **From:** `keymap = Gdk.Keymap.get_default(); state = keymap.get_modifier_state()`
    *   **To:** `display = Gdk.Display.get_default(); state = display.get_keyboard().get_modifier()`
    *   **Action:** Update this in `on_row_selected` and `_capture_modifier_state`.

## Phase 5: Verification & Cleanup

1.  **Run and Test:**
    Continuously run the application after each major change to catch regressions early.

2.  **Use GTK Inspector:**
    Launch the app with `GTK_DEBUG=interactive` to debug UI and CSS issues. This is the most critical tool for the migration.

3.  **Remove Obsolete Code:**
    Once the application is stable, search for and remove any remaining GTK3-specific code, such as calls to deprecated methods that might still work but log warnings.
