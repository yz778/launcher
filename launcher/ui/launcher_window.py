#!/usr/bin/env python3

import logging
from typing import Dict, Any

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
    ):
        super().__init__(title="Launcher")

        # Apply default styling immediately
        CssManager._load_css_from_string(CssManager.DEFAULT_CSS)

        self.plugin_manager = plugin_manager
        self.history_manager = history_manager
        self.config = config
        self.icon_size = config.get("general", {}).get("icon_size")

        # Get window size configuration
        general_config = config.get("general", {})
        self.window_width = general_config.get("window_width")
        self.window_height = general_config.get("window_height")
        self.window_height_results = general_config.get("window_height_results")

        # Set up window properties
        self.set_decorated(False)

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
        self.connect("destroy", Gtk.main_quit)
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

        # Only connect signals if plugin_manager and history_manager are available
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
        self.current_results = []

        # Track if user is navigating with keys
        self.user_navigating = False

        # Make sure the scrolled window is hidden initially
        self.scrolled.hide()

        self.entry.grab_focus()

    def update_results(self, query: str) -> None:
        """Update the results list with matches for the query"""
        for child in self.list_box.get_children():
            self.list_box.remove(child)

        if not query:
            self.scrolled.hide()
            self.result_count_label.set_text("")
            self.result_count_label.hide()
            self.resize(self.window_width, self.window_height)
            return

        # Search for matches using the plugin manager
        results = self.plugin_manager.search(query)

        # Adjust scores based on history
        for result in results:
            count = self.history_manager.get_count(result.plugin_id, result.item_id)
            result.score = self.history_manager.adjust_score(
                result.plugin_id, result.item_id, result.score
            )
            # Store the count in the result for sorting
            result.metadata["history_count"] = count

        # Sort by history first (items with history > 0 come first), then by score
        self.current_results = sorted(
            results,
            key=lambda r: (
                r.metadata.get("history_count", 0) > 0,
                r.score,
            ),
            reverse=True,
        )

        if not self.current_results:
            self.scrolled.hide()
            self.result_count_label.set_text("")
            self.result_count_label.hide()
            self.resize(self.window_width, self.window_height)
            return

        count = len(self.current_results)
        self.result_count_label.set_text(f"{count} result{'s' if count != 1 else ''}")
        self.result_count_label.show()

        for result in self.current_results:
            count = self.history_manager.get_count(result.plugin_id, result.item_id)
            icon_size = (
                self.icon_size
                if self.icon_size is not None
                else self.general_config.get("icon_size")
            )
            list_item = AppListItem(result, icon_size=icon_size, launch_count=count)
            self.list_box.add(list_item)

        self.list_box.show_all()

        self.scrolled.show()

        if len(self.current_results) > 5:  # Show scrollbar only if more than 5 items
            # Force scrollbar to be visible
            self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.ALWAYS)
            # Ensure overlay scrolling is disabled
            self.scrolled.set_overlay_scrolling(False)
        else:
            # Hide scrollbar for 5 or fewer items
            self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)

        # Resize the window to show results at full height
        window_height = self.window_height_results
        self.resize(self.window_width, window_height)

        self.scrolled.queue_resize()

        if len(self.current_results) > 1:
            # Show scrollbar immediately
            adjustment = self.scrolled.get_vadjustment()
            if adjustment:
                # Set values to force scrollbar to appear
                adjustment.set_upper(adjustment.get_upper() + 1)

        # Don't auto-select unless user is navigating
        if not self.user_navigating:
            self.list_box.unselect_all()

    def on_entry_changed(self, widget) -> None:
        """Handle text changes in the entry field"""
        # Reset navigation state when user types
        self.user_navigating = False
        query = self.entry.get_text().strip()
        self.update_results(query)

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
                    self.update_results(self.entry.get_text().strip())
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

    def on_key_press(self, widget, event) -> bool:
        """Handle global key presses"""
        if event.keyval == Gdk.KEY_Escape:
            self.close_window()
            return True

        return False

    def on_focus_out(self, widget, event) -> bool:
        """Close the launcher when it loses focus"""
        self.close_window()
        return False

    def close_window(self):
        Gtk.main_quit()
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
