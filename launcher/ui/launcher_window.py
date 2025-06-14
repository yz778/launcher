#!/usr/bin/env python3

import logging
from typing import Dict, Any, List

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango

from plugins.base import SearchResult
from core.plugin_manager import PluginManager
from core.history_manager import HistoryManager
from ui.css_manager import CssManager

logger = logging.getLogger(__name__)


class AppListItem(Gtk.ListBoxRow):
    """Custom list box row for displaying a search result"""

    def __init__(self, result: SearchResult, icon_size: int, launch_count: int = 0):
        super().__init__()
        self.set_name("app-list-item")
        self.result = result

        # Add plugin-specific CSS class
        style_context = self.get_style_context()
        plugin_class = f"{result.plugin_id}-result"
        style_context.add_class(plugin_class)

        # Create a horizontal box to hold the icon and text
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox.set_border_width(8)

        hbox.set_property("height-request", 40)

        if result.icon:
            # Create a fixed size container for the icon
            icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            icon_box.set_size_request(icon_size, icon_size)

            # Use the icon
            icon = Gtk.Image.new_from_pixbuf(result.icon)

            # Center the icon in the fixed size box
            icon_box.pack_start(icon, True, False, 0)
            hbox.pack_start(icon_box, False, False, 0)
        else:
            # Add an empty box to maintain spacing
            spacer = Gtk.Box()
            spacer.set_size_request(icon_size, icon_size)
            hbox.pack_start(spacer, False, False, 0)

        # Create a vertical box for name and description
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        # Create a horizontal box for name and count
        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

        # Add the name
        name_label = Gtk.Label(label=result.name)
        name_label.set_halign(Gtk.Align.START)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        name_label.set_name("app-name")
        name_box.pack_start(name_label, True, True, 0)

        # Add launch count if greater than 0
        if launch_count > 0:
            count_label = Gtk.Label(
                label=f"Used {launch_count} time{'s' if launch_count != 1 else ''}"
            )
            count_label.set_halign(Gtk.Align.END)
            count_label.get_style_context().add_class("dim-label")
            count_label.set_name("app-count")
            name_box.pack_end(count_label, False, False, 5)

        vbox.pack_start(name_box, True, True, 0)

        if result.description:
            desc_label = Gtk.Label(label=result.description)
            desc_label.set_halign(Gtk.Align.START)
            desc_label.set_ellipsize(Pango.EllipsizeMode.END)
            desc_label.set_name("app-description")
            desc_label.get_style_context().add_class("dim-label")
            vbox.pack_start(desc_label, True, True, 0)

        hbox.pack_start(vbox, True, True, 0)
        self.add(hbox)

        if result.description:
            self.set_tooltip_text(result.description)


class LauncherWindow(Gtk.Window):
    """Main launcher window"""

    def __init__(
        self,
        plugin_manager: PluginManager,
        history_manager: HistoryManager,
        config: Dict[str, Any],
        foreground_mode: bool = False,
    ):
        super().__init__(title="Launcher")

        # Apply default styling immediately
        CssManager._load_css_from_string(CssManager.DEFAULT_CSS)

        self.plugin_manager = plugin_manager
        self.history_manager = history_manager
        self.config = config
        self.foreground_mode = foreground_mode
        self.icon_size = config.get("general", {}).get("icon_size")

        # Get window size configuration
        general_config = config.get("general", {})
        self.window_width = general_config.get("window_width")
        self.window_height = general_config.get("window_height")
        self.window_height_results = general_config.get("window_height_results")

        # Position tracking variables
        self.saved_x = None
        self.saved_y = None

        # Set up window properties
        self.set_decorated(False)

        # Connect position tracking before setting initial position
        self.connect("configure-event", self.on_configure_event)

        try:
            display = Gdk.Display.get_default()
            monitor = display.get_primary_monitor()
            geometry = monitor.get_geometry()
            scale_factor = monitor.get_scale_factor()
            monitor_width = geometry.width // scale_factor
            monitor_height = geometry.height // scale_factor
            x = geometry.x + (monitor_width - self.window_width) // 2
            y = geometry.y + (monitor_height - self.window_height) // 4
            self.move(x, y)
            # Store initial position
            self.saved_x = x
            self.saved_y = y

        except Exception as e:
            logger.error(f"Unable to set window position: {e}")
            self.set_position(Gtk.WindowPosition.CENTER)

        self.set_default_size(self.window_width, self.window_height)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_name("launcher-window")

        # Connect signals
        self.connect("delete-event", self.on_delete_event)
        self.connect("key-press-event", self.on_key_press)
        self.connect("focus-out-event", self.on_focus_out)

        # Create a vertical box for the layout
        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.vbox.set_border_width(general_config.get("border_width"))
        self.add(self.vbox)

        # Create a box for the entry field and result count
        entry_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        entry_box.set_name("launcher-entry-container")

        # Initialize the entry field
        self.entry = Gtk.Entry()
        self.entry.set_activates_default(True)
        self.entry.set_name("launcher-entry")

        # Only connect signals if plugin_manager is not None and history_manager is not None
        if plugin_manager is not None and history_manager is not None:
            self.entry.connect("changed", self.on_entry_changed)
        self.entry.connect("key-press-event", self.on_entry_key_press)

        # Store the signal handler ID for later connection/disconnection
        self.entry_changed_handler_id = None

        entry_box.pack_start(self.entry, True, True, 0)

        # Initialize the result count label
        self.result_count_label = Gtk.Label()
        self.result_count_label.set_halign(Gtk.Align.END)
        self.result_count_label.get_style_context().add_class("dim-label")
        self.result_count_label.set_name("result-count-label")
        entry_box.pack_end(self.result_count_label, False, False, 5)
        self.result_count_label.hide()

        self.vbox.pack_start(entry_box, False, False, 0)

        # Create a scrolled window for the results
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.ALWAYS)
        self.scrolled.set_shadow_type(Gtk.ShadowType.NONE)
        self.scrolled.set_name("results-scrolled")

        # Set overlay scrolling to False to ensure scrollbar is always visible
        self.scrolled.set_overlay_scrolling(False)

        self.scrolled.set_max_content_height(
            self.window_height_results - self.window_height
        )

        self.scrolled.set_propagate_natural_height(True)

        self.vbox.pack_start(self.scrolled, True, True, 5)

        # Create the list box for results
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.connect("row-activated", self.on_row_activated)
        self.list_box.set_name("results-list")
        self.scrolled.add(self.list_box)

        # Current search results
        self.current_results: List[SearchResult] = []
        self.active_search_id: int = 0

        # Search debouncing
        self._search_timeout_id = None
        self._search_delay_ms = 50  # 100ms delay to reduce search frequency

        # Track if user is navigating with keys
        self.user_navigating = False

        # Make sure the scrolled window is hidden initially
        self.scrolled.hide()

        self.entry.grab_focus()

    def _clear_list_box_and_hide(self):
        """Clears all items from the list box and hides the results area."""
        # Properly destroy child widgets to prevent memory leaks
        for child in self.list_box.get_children():
            child.destroy()  # Explicitly destroy rather than just remove
        self.scrolled.hide()
        self.result_count_label.set_text("")
        self.result_count_label.hide()
        self.resize(self.window_width, self.window_height)

    def _populate_list_box(self, results_to_display: List[SearchResult]):
        """Populates the list box with the given results and updates UI elements."""
        # Clear previous items from list_box with proper cleanup
        for child in self.list_box.get_children():
            child.destroy()  # Properly destroy widgets

        # Always show dropdown if user has typed something
        self.scrolled.show()
        self.result_count_label.hide()

        # Add new items
        for result in results_to_display:
            history_count = self.history_manager.get_count(
                result.plugin_id, result.item_id
            )
            icon_size = (
                self.icon_size
                if self.icon_size is not None
                else self.config.get("general", {}).get("icon_size", 48)
            )
            list_item = AppListItem(
                result, icon_size=icon_size, launch_count=history_count
            )
            self.list_box.add(list_item)

        self.list_box.show_all()
        self.scrolled.show()
        # Scroll to top when results change
        vadj = self.scrolled.get_vadjustment()
        if vadj:
            vadj.set_value(vadj.get_lower())

        # Show result count if there are results
        if results_to_display:
            count = len(results_to_display)
            self.result_count_label.set_text(
                f"{count} result{'s' if count != 1 else ''}"
            )
            self.result_count_label.show()
        else:
            self.result_count_label.set_text("")
            self.result_count_label.hide()

        # Always reserve space for 5 results
        row_height = 40 + 16  # AppListItem height-request + hbox border
        min_height = row_height * 5
        self.resize(self.window_width, max(self.window_height_results, min_height))
        self.scrolled.set_size_request(-1, min_height)
        self.scrolled.queue_resize()

        # Scrollbar visibility logic
        if len(results_to_display) > 5:
            self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.ALWAYS)
            self.scrolled.set_overlay_scrolling(False)
        else:
            self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)

        # Resize window
        self.resize(self.window_width, self.window_height_results)
        self.scrolled.queue_resize()

        if len(results_to_display) > 1:
            adjustment = self.scrolled.get_vadjustment()
            if adjustment:
                adjustment.set_upper(adjustment.get_upper() + 1)

        if not self.user_navigating:
            self.list_box.unselect_all()

    def handle_plugin_results(
        self, search_id: int, plugin_id: str, plugin_results: List[SearchResult]
    ):
        """Callback for when a plugin returns results."""
        if search_id != self.active_search_id:
            logger.debug(
                f"Ignoring stale results from plugin {plugin_id} for search_id {search_id} (current is {self.active_search_id})"
            )
            return

        logger.debug(
            f"Received {len(plugin_results)} results from plugin {plugin_id} for search_id {search_id}"
        )
        self.current_results.extend(plugin_results)

        # Adjust scores based on history for all current results
        for result in self.current_results:
            if (
                "history_count" not in result.metadata
            ):  # Avoid re-processing if called multiple times
                count = self.history_manager.get_count(result.plugin_id, result.item_id)
                result.score = self.history_manager.adjust_score(
                    result.plugin_id, result.item_id, result.score
                )
                result.metadata["history_count"] = count

        # Sort by history (items with history > 0 come first), then by score
        self.current_results.sort(
            key=lambda r: (
                r.metadata.get("history_count", 0)
                > 0,  # True (1) for items with history
                r.score,
            ),
            reverse=True,
        )

        # Truncate results
        max_results = self.config.get("general", {}).get("max_results", 15)
        self.current_results = self.current_results[:max_results]

        self._populate_list_box(self.current_results)

    def handle_search_finished(self, search_id: int):
        """Callback for when all plugins have finished searching."""
        if search_id != self.active_search_id:
            logger.debug(
                f"Ignoring stale search_finished signal for search_id {search_id} (current is {self.active_search_id})"
            )
            return

        logger.debug(f"All plugins have finished searching for search_id {search_id}.")
        # Always show dropdown if user has typed something, even if no results
        if self.entry.get_text().strip() and not self.current_results:
            self._populate_list_box([])
        elif not self.current_results:
            self._clear_list_box_and_hide()

    def on_entry_changed(self, widget) -> None:
        """Handle text changes in the entry field with debouncing."""
        # Cancel any pending search
        if self._search_timeout_id:
            from gi.repository import GLib

            GLib.source_remove(self._search_timeout_id)

        # Schedule new search with debouncing
        from gi.repository import GLib

        self._search_timeout_id = GLib.timeout_add(
            self._search_delay_ms, self._perform_search
        )

    def _perform_search(self) -> bool:
        """Actually perform the search (called after debounce delay)"""
        self._search_timeout_id = None  # Clear timeout ID

        self.user_navigating = False  # Reset navigation state
        query = self.entry.get_text().strip()

        self.current_results.clear()
        if not query:
            self._clear_list_box_and_hide()
            return False  # Remove from timeout

        self.active_search_id += 1
        logger.debug(
            f"Initiating new search with search_id: {self.active_search_id} for query: '{query}'"
        )

        self.plugin_manager.search(
            query,
            self.active_search_id,
            self.handle_plugin_results,
            self.handle_search_finished,
        )
        return False  # Remove from timeout

    def on_entry_key_press(self, widget, event) -> bool:
        """Handle key presses in the entry field"""
        keyval = event.keyval
        state = event.state

        # Handle Enter to execute
        if keyval == Gdk.KEY_Return:
            if self.scrolled.get_visible() and self.plugin_manager is not None:
                selected_row = self.list_box.get_selected_row()
                if selected_row:
                    self.execute_result(selected_row.result, event)
                    return True
                elif self.current_results:
                    # No selection but have results, execute first result
                    self.execute_result(self.current_results[0], event)
                    return True

                Gtk.main_quit()

            return True

        if self.scrolled.get_visible():
            # Handle Down arrow
            if keyval == Gdk.KEY_Down:
                self.user_navigating = True
                selected_row = self.list_box.get_selected_row()
                if selected_row:
                    index = selected_row.get_index()
                    if index < len(self.current_results) - 1:
                        next_row = self.list_box.get_row_at_index(index + 1)
                        self.list_box.select_row(next_row)
                        adjustment = self.scrolled.get_vadjustment()
                        if adjustment:
                            row_alloc = next_row.get_allocation()
                            adjustment.clamp_page(
                                row_alloc.y, row_alloc.y + row_alloc.height
                            )
                else:
                    # No selection, select first item
                    if self.current_results:
                        first_row = self.list_box.get_row_at_index(0)
                        self.list_box.select_row(first_row)
                return True

            # Handle Up arrow
            elif keyval == Gdk.KEY_Up:
                self.user_navigating = True
                selected_row = self.list_box.get_selected_row()
                if selected_row:
                    index = selected_row.get_index()
                    if index > 0:
                        prev_row = self.list_box.get_row_at_index(index - 1)
                        self.list_box.select_row(prev_row)
                        adjustment = self.scrolled.get_vadjustment()
                        if adjustment:
                            row_alloc = prev_row.get_allocation()
                            adjustment.clamp_page(
                                row_alloc.y, row_alloc.y + row_alloc.height
                            )
                else:
                    # No selection, select first item
                    if self.current_results:
                        first_row = self.list_box.get_row_at_index(0)
                        self.list_box.select_row(first_row)
                return True

            # Handle Tab
            elif keyval == Gdk.KEY_Tab:
                selected_row = self.list_box.get_selected_row()
                if not selected_row and self.current_results:
                    # No selection, select first item
                    first_row = self.list_box.get_row_at_index(0)
                    self.list_box.select_row(first_row)
                    selected_row = first_row

                if selected_row:
                    self.entry.set_text(selected_row.result.name)
                    self.entry.set_position(-1)
                return True

            # Handle Shift+Delete to remove history entry
            elif keyval == Gdk.KEY_Delete and state & Gdk.ModifierType.SHIFT_MASK:
                selected_row = self.list_box.get_selected_row()
                if selected_row:
                    result = selected_row.result
                    self.history_manager.remove_entry(result.plugin_id, result.item_id)
                    self.on_entry_changed(self.entry)
                return True

        # Global hotkeys (work anywhere in the window)
        # Handle F5 or Ctrl+R to rescan all plugins
        if keyval == Gdk.KEY_F5 or (
            keyval == Gdk.KEY_r and state & Gdk.ModifierType.CONTROL_MASK
        ):
            self._trigger_rescan()
            return True

        return False

    def on_row_activated(self, list_box, row) -> None:
        """Handle activation of a row in the results list"""
        if row:
            self.execute_result(row.result, None)

    def execute_result(self, result: SearchResult, event=None) -> None:
        """Execute the given search result"""

        # Check if history_manager and plugin_manager are available
        if self.history_manager is None or self.plugin_manager is None:
            logger.warning("Cannot execute result: managers not initialized yet")
            self.close_window()
            return

        if event:
            state = event.state

        else:
            keymap = Gdk.Keymap.get_default()
            state = keymap.get_modifier_state()

        # Store modifier state in the result metadata
        result.metadata["shift_pressed"] = bool(state & Gdk.ModifierType.SHIFT_MASK)
        result.metadata["ctrl_pressed"] = bool(state & Gdk.ModifierType.CONTROL_MASK)
        result.metadata["alt_pressed"] = bool(state & Gdk.ModifierType.MOD1_MASK)
        result.metadata["cmd_pressed"] = bool(state & Gdk.ModifierType.META_MASK)

        # Use plugin manager to execute result, if successful save to history and quit
        if self.plugin_manager.execute(result):
            command_string = self.entry.get_text().strip()
            self.history_manager.increment_count(
                result.plugin_id, result.item_id, command_string
            )
            self.history_manager.save_history()
            result.metadata["history_manager"] = self.history_manager
            self.close_window()

    def on_configure_event(self, widget, event):
        """Track window position changes"""
        # Only track position if window is visible and we're not in the middle of showing
        if self.get_visible() and self.get_mapped():
            # Add a small delay to avoid tracking intermediate positions during window showing
            from gi.repository import GLib

            GLib.timeout_add(100, self._save_position, event.x, event.y)
        return False

    def _save_position(self, x, y):
        """Save position after a small delay to ensure it's the final position"""
        if self.get_visible():
            self.saved_x = x
            self.saved_y = y
            logger.debug(f"Saved window position: ({x}, {y})")
        return False  # Remove from timeout

    def show_and_focus(self):
        """Show window at saved position and grab focus"""
        # Restore saved position if we have one
        if self.saved_x is not None and self.saved_y is not None:
            self.move(self.saved_x, self.saved_y)

        # Show the window
        self.show_all()

        # Make sure results are hidden initially
        self.scrolled.hide()

        # Clear entry and reset state
        self.entry.set_text("")
        self._clear_list_box_and_hide()

        # Present window and grab focus
        self.present()

        # Use GLib.idle_add to ensure this happens after window is mapped
        from gi.repository import GLib

        GLib.idle_add(self._delayed_focus)

    def _delayed_focus(self):
        """Delayed focus grabbing to ensure window is fully shown"""
        try:
            # Make sure window is visible and mapped
            if not self.get_visible() or not self.get_mapped():
                return False

            # Make sure window is at the front
            if self.get_window():
                self.get_window().raise_()
                self.get_window().focus(0)

            # Grab focus for the entry field
            self.entry.grab_focus()

            # Additional focus enforcement for stubborn window managers
            self.present()

            # Some window managers need an extra nudge
            self.activate_focus()

        except Exception as e:
            logger.debug(f"Error in delayed focus: {e}")

        return False  # Remove from idle queue

    def _trigger_rescan(self):
        """Trigger a rescan of all plugins"""
        if not self.plugin_manager:
            return

        logger.info("Manual rescan triggered")

        # Show a brief notification
        self.entry.set_text("🔄 Rescanning...")
        self.entry.set_editable(False)

        # Schedule the actual rescan and UI reset
        from gi.repository import GLib

        GLib.timeout_add(100, self._do_rescan)

    def _do_rescan(self):
        """Perform the actual rescan"""
        # Trigger rescan for supported plugins
        for plugin_id, plugin in self.plugin_manager.plugins.items():
            if hasattr(plugin, "rescan"):
                logger.info(f"Rescanning {plugin_id} plugin")
                plugin.rescan()

        # Reset UI after a short delay
        from gi.repository import GLib

        GLib.timeout_add(1000, self._reset_after_rescan)
        return False

    def _reset_after_rescan(self):
        """Reset UI after rescan completes"""
        self.entry.set_text("")
        self.entry.set_editable(True)
        self.entry.grab_focus()
        return False

    def on_delete_event(self, widget, event):
        """Handle window delete event - hide or quit based on mode"""
        if self.foreground_mode:
            # In foreground mode, quit the application
            Gtk.main_quit()
        else:
            # In singleton mode, hide the window
            self.hide()
        return True  # Prevent default destroy behavior

    def on_key_press(self, widget, event) -> bool:
        keyval = event.keyval
        nav_keys = [
            Gdk.KEY_Up,
            Gdk.KEY_Down,
            Gdk.KEY_Tab,
            Gdk.KEY_Page_Up,
            Gdk.KEY_Page_Down,
        ]
        if keyval == Gdk.KEY_Escape:
            self.close_window()
            return True
        if keyval not in nav_keys and not self.is_active():
            self.present()
            self.entry.grab_focus()
        return False

    def on_focus_out(self, widget, event) -> bool:
        """Close the launcher when it loses focus (only in singleton mode)"""
        if not self.foreground_mode:
            # Only auto-hide in singleton mode
            self.close_window()
        return False

    def close_window(self):
        """Hide the window or quit based on mode"""
        if self.foreground_mode:
            # In foreground mode, quit the application
            Gtk.main_quit()
        else:
            # In singleton mode, hide the window
            self.hide()
        return True

    def update_with_full_config(self, plugin_manager, history_manager, config):
        """Update the window with the full configuration after initialization"""
        self.plugin_manager = plugin_manager
        self.history_manager = history_manager
        self.config = config

        # Update window size if needed
        general_config = config.get("general", {})
        self.window_width = general_config.get("window_width", self.window_width)
        self.window_height = general_config.get("window_height", self.window_height)
        self.window_height_results = general_config.get("window_height_results")

        # Update icon size
        self.icon_size = general_config.get("icon_size", self.icon_size)

        # Resize the window to match the full config
        self.resize(self.window_width, self.window_height)

        # Connect the entry's "changed" signal now that we have plugin_manager and history_manager
        if self.entry_changed_handler_id is None:
            self.entry_changed_handler_id = self.entry.connect(
                "changed", self.on_entry_changed
            )
            logger.info("Connected entry changed signal after full initialization")
