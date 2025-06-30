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

        hbox.set_property("height-request", 60)  # Increased height to show description

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

        # Add description
        desc_label = Gtk.Label(label=result.description or "")
        desc_label.set_halign(Gtk.Align.START)
        desc_label.set_name("app-description")
        desc_label.get_style_context().add_class("dim-label")
        desc_label.set_ellipsize(Pango.EllipsizeMode.END)
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
        self.list_box.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        self.list_box.connect("row-activated", self.on_row_activated)
        self.list_box.connect(
            "selected-rows-changed", self.on_list_box_selection_changed
        )  # Connect selection changed signal
        self.list_box.set_name("results-list")
        self.scrolled.add(self.list_box)

        # Current search results
        self.current_results: List[SearchResult] = []
        self.active_search_id: int = 0

        # History-related state
        self.showing_history = False
        self.autocomplete_matches: List[str] = []
        self.autocomplete_index = -1

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
        self.showing_history = False

    def _show_recent_history(self):
        """Show the most recent 5 history items when launcher opens with empty input."""
        if not self.history_manager:
            return

        recent_items = self.history_manager.get_recent_history(5)
        if not recent_items:
            return

        # Clear previous items
        for child in self.list_box.get_children():
            child.destroy()

        # Create history result items
        for i, history_entry in enumerate(recent_items):
            user_input = history_entry.get("user_input", "")
            plugin_id = history_entry.get("plugin_id", "")
            item_id = history_entry.get("item_id", "")
            description = history_entry.get("description", user_input)

            if not user_input:
                continue

            # Try to get the actual result from plugins to get the current icon
            # Pass the history_entry so we can check for stored icons
            actual_result = self._get_result_for_history_entry(
                plugin_id, item_id, history_entry
            )

            # Determine the icon to use
            display_icon = None
            if actual_result and actual_result.icon:
                display_icon = actual_result.icon
            else:
                # Fallback to clock icon
                try:
                    icon_theme = Gtk.IconTheme.get_default()
                    display_icon = icon_theme.load_icon(
                        "accessories-history", self.icon_size or 48, 0
                    )
                except Exception as e:
                    logger.warning(f"Could not load history icon: {e}")
                    # Fallback to a generic icon if history icon fails
                    try:
                        display_icon = icon_theme.load_icon(
                            "document-open-recent", self.icon_size or 48, 0
                        )
                    except Exception as e:
                        logger.warning(f"Could not load generic recent icon: {e}")
                        # If all else fails, display no icon (AppListItem will handle it)
                        display_icon = None

            # Determine the icon to use
            display_icon = None
            if actual_result and actual_result.icon:
                display_icon = actual_result.icon
            else:
                # Fallback to clock icon
                try:
                    icon_theme = Gtk.IconTheme.get_default()
                    display_icon = icon_theme.load_icon(
                        "accessories-history", self.icon_size or 48, 0
                    )
                except Exception as e:
                    logger.warning(f"Could not load history icon: {e}")
                    # Fallback to a generic icon if history icon fails
                    try:
                        display_icon = icon_theme.load_icon(
                            "document-open-recent", self.icon_size or 48, 0
                        )
                    except Exception as e:
                        logger.warning(f"Could not load generic recent icon: {e}")
                        # If all else fails, display no icon (AppListItem will handle it)
                        display_icon = None

            # Create history result items
            history_count = history_entry.get("usage_count", 0)
            list_item = AppListItem(
                SearchResult(
                    plugin_id=plugin_id,
                    item_id=item_id,
                    name=user_input,
                    description=description,
                    icon=display_icon,
                    score=0,
                ),
                icon_size=self.icon_size or 48,
                launch_count=history_count,
            )
            list_item.set_name("history-item")
            list_item.user_input = user_input  # Store the input for selection
            list_item.history_entry = history_entry  # Store full history entry
            self.list_box.add(list_item)

        self.list_box.show_all()
        self.scrolled.show()
        self.showing_history = True

        # Resize window for history display
        row_height = 60 + 16  # height + padding
        num_items = len(recent_items)
        min_height = row_height * max(num_items, 1)
        self.resize(self.window_width, self.window_height + min_height)
        self.scrolled.set_size_request(-1, min_height)

    def _get_result_for_history_entry(
        self, plugin_id: str, item_id: str, history_entry: Dict[str, Any] = None
    ):
        """Try to get the actual result object for a history entry to access current icon."""
        if not self.plugin_manager:
            return None

        # First, check if we have stored icon data in history (for executable plugin)
        if history_entry and plugin_id == "executable":
            stored_icon = self.history_manager.get_stored_icon(
                history_entry, self.icon_size or 48
            )
            if stored_icon:
                # Create a result-like object with the stored icon
                class MockResult:
                    def __init__(self, icon, name, plugin_id, item_id):
                        self.icon = icon
                        self.name = name
                        self.plugin_id = plugin_id
                        self.item_id = item_id

                return MockResult(
                    stored_icon,
                    history_entry.get("user_input", ""),
                    plugin_id,
                    item_id,
                )

        plugin = self.plugin_manager.plugins.get(plugin_id)
        if not plugin:
            return None

        try:
            # Handle different plugin types based on their structure
            if plugin_id == "desktop_file" and hasattr(plugin, "desktop_files"):
                # For desktop files, search through the desktop_files dict
                for desktop_file in plugin.desktop_files.values():
                    if desktop_file.path == item_id:
                        # Create a SearchResult-like object with the icon
                        class MockResult:
                            def __init__(self, desktop_file, icon_size):
                                self.icon = desktop_file.get_icon_pixbuf(icon_size)
                                self.name = desktop_file.name
                                self.plugin_id = plugin_id
                                self.item_id = item_id

                        return MockResult(desktop_file, self.icon_size or 48)

            elif plugin_id == "executable" and hasattr(plugin, "executables"):
                # For executables, search through the executables dict
                executable = plugin.executables.get(item_id)
                if executable:
                    # Try to get custom icon first, then fallback to default
                    icon = None
                    if executable.custom_icon:
                        icon = plugin._load_custom_icon(executable.custom_icon)
                    if not icon:
                        icon = plugin.default_icon

                    # Create a SearchResult-like object
                    class MockResult:
                        def __init__(self, icon, name):
                            self.icon = icon
                            self.name = name
                            self.plugin_id = plugin_id
                            self.item_id = item_id

                    return MockResult(icon, executable.name)

            elif plugin_id == "qalculate" or plugin_id == "calculator":
                # For calculator plugins, use a default icon
                try:
                    icon_theme = Gtk.IconTheme.get_default()
                    icon = icon_theme.load_icon(
                        "accessories-calculator", self.icon_size or 48, 0
                    )

                    class MockResult:
                        def __init__(self, icon):
                            self.icon = icon
                            self.name = "Calculator"
                            self.plugin_id = plugin_id
                            self.item_id = item_id

                    return MockResult(icon)
                except:
                    pass

            elif plugin_id == "terminal":
                # For terminal plugin, use a terminal icon
                try:
                    icon_theme = Gtk.IconTheme.get_default()
                    icon = icon_theme.load_icon(
                        "utilities-terminal", self.icon_size or 48, 0
                    )

                    class MockResult:
                        def __init__(self, icon):
                            self.icon = icon
                            self.name = "Terminal"
                            self.plugin_id = plugin_id
                            self.item_id = item_id

                    return MockResult(icon)
                except:
                    pass

        except Exception as e:
            logger.debug(f"Could not get item {item_id} from plugin {plugin_id}: {e}")

        return None

    def _execute_history_item(self, history_entry: Dict[str, Any]) -> None:
        """
        Execute an item from history by doing a targeted search and executing the first exact match.

        Args:
            history_entry: History entry containing plugin_id, item_id, user_input, etc.
        """
        plugin_id = history_entry.get("plugin_id")
        item_id = history_entry.get("item_id")
        user_input = history_entry.get("user_input", "")

        if not plugin_id or not item_id or not self.plugin_manager:
            # Fallback to regular search if missing data
            self.entry.set_text(user_input)
            self.on_entry_changed(self.entry)
            return

        # Get the specific plugin and search for the exact item
        plugin = self.plugin_manager.plugins.get(plugin_id)
        if not plugin:
            # Plugin not available, fallback to search
            self.entry.set_text(user_input)
            self.on_entry_changed(self.entry)
            return

        try:
            # Use the plugin's search method to find the item
            results = plugin.search(user_input)

            # Find the exact result by item_id
            target_result = None
            for result in results:
                if result.item_id == item_id:
                    target_result = result
                    break

            if target_result:
                # Found the exact item, execute it directly
                self.execute_result(target_result, None)
            else:
                # Item not found, fallback to regular search
                self.entry.set_text(user_input)
                self.on_entry_changed(self.entry)

        except Exception as e:
            logger.debug(f"Error executing history item: {e}")
            # Fallback to regular search
            self.entry.set_text(user_input)
            self.on_entry_changed(self.entry)

    def _populate_list_box(self, results_to_display: List[SearchResult]):
        """Populates the list box with the given results and updates UI elements."""
        # Clear previous items from list_box with proper cleanup
        for child in self.list_box.get_children():
            child.destroy()  # Properly destroy widgets

        self.showing_history = False  # We're showing search results now

        # Always show dropdown if user has typed something
        self.scrolled.show()
        self.result_count_label.hide()

        # Add new items
        for result in results_to_display:
            history_count = self.history_manager.get_usage_count(
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
        row_height = 60 + 16  # AppListItem height-request + hbox border
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
                count = self.history_manager.get_usage_count(
                    result.plugin_id, result.item_id
                )
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
        self.autocomplete_matches.clear()
        self.autocomplete_index = -1

        if not query:
            self._clear_list_box_and_hide()
            # Show recent history when empty
            self._show_recent_history()
            return False  # Remove from timeout

        # Check for autocomplete matches
        if self.history_manager:
            self.autocomplete_matches = self.history_manager.get_matching_history(
                query, 5
            )

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

        # Handle Tab for autocomplete
        if keyval == Gdk.KEY_Tab and self.autocomplete_matches:
            self.autocomplete_index = (self.autocomplete_index + 1) % len(
                self.autocomplete_matches
            )
            autocomplete_text = self.autocomplete_matches[self.autocomplete_index]
            self.entry.set_text(autocomplete_text)
            self.entry.set_position(-1)
            return True

        # Handle Enter to execute
        if keyval == Gdk.KEY_Return:
            if self.showing_history:
                # Handle history item selection - execute directly from history
                selected_row = self.list_box.get_selected_row()
                if selected_row and hasattr(selected_row, "history_entry"):
                    self._execute_history_item(selected_row.history_entry)
                    return True
                elif self.list_box.get_children():
                    # No selection but have history items, use first one
                    first_row = self.list_box.get_row_at_index(0)
                    if first_row and hasattr(first_row, "history_entry"):
                        self._execute_history_item(first_row.history_entry)
                        return True
            elif self.scrolled.get_visible() and self.plugin_manager is not None:
                selected_row = self.list_box.get_selected_row()
                if selected_row:
                    self.execute_result(selected_row.result, event)
                    return True
                elif self.current_results:
                    # No selection but have results, execute first result
                    self.execute_result(self.current_results[0], event)
                    return True

            return True

        if self.scrolled.get_visible():
            # Handle Down arrow
            if keyval == Gdk.KEY_Down:
                self.user_navigating = True
                selected_row = (
                    self.list_box.get_selected_row()
                )  # Get the currently focused row
                target_row = None

                if selected_row:
                    index = selected_row.get_index()
                    children = self.list_box.get_children()
                    if index < len(children) - 1:
                        target_row = self.list_box.get_row_at_index(index + 1)
                else:
                    # No current selection, select the first item
                    children = self.list_box.get_children()
                    if children:
                        target_row = self.list_box.get_row_at_index(0)

                if target_row:
                    if not (state & Gdk.ModifierType.SHIFT_MASK):
                        # If Shift is NOT pressed, ensure only the target_row is selected
                        for row in self.list_box.get_selected_rows():
                            if row != target_row:
                                self.list_box.unselect_row(row)
                    self.list_box.select_row(target_row)  # Select the target row

                    adjustment = self.scrolled.get_vadjustment()
                    if adjustment:
                        row_alloc = target_row.get_allocation()
                        adjustment.clamp_page(
                            row_alloc.y, row_alloc.y + row_alloc.height
                        )

                    if self.showing_history and hasattr(target_row, "user_input"):
                        # Temporarily block the "changed" signal
                        if self.entry_changed_handler_id is not None:
                            self.entry.handler_block(self.entry_changed_handler_id)
                        self.entry.set_text(target_row.user_input)
                        self.entry.set_position(-1)
                        # Unblock the "changed" signal
                        if self.entry_changed_handler_id is not None:
                            self.entry.handler_unblock(self.entry_changed_handler_id)
                return True

            # Handle Up arrow
            elif keyval == Gdk.KEY_Up:
                self.user_navigating = True
                selected_row = (
                    self.list_box.get_selected_row()
                )  # Get the currently focused row
                target_row = None

                if selected_row:
                    index = selected_row.get_index()
                    if index > 0:
                        target_row = self.list_box.get_row_at_index(index - 1)
                else:
                    # No current selection, select the last item
                    children = self.list_box.get_children()
                    if children:
                        target_row = self.list_box.get_row_at_index(
                            len(children) - 1
                        )  # Select the last item if no selection

                if target_row:
                    if not (state & Gdk.ModifierType.SHIFT_MASK):
                        # If Shift is NOT pressed, ensure only the target_row is selected
                        for row in self.list_box.get_selected_rows():
                            if row != target_row:
                                self.list_box.unselect_row(row)
                    self.list_box.select_row(target_row)  # Select the target row

                    adjustment = self.scrolled.get_vadjustment()
                    if adjustment:
                        row_alloc = target_row.get_allocation()
                        adjustment.clamp_page(
                            row_alloc.y, row_alloc.y + row_alloc.height
                        )

                    if self.showing_history and hasattr(target_row, "user_input"):
                        # Temporarily block the "changed" signal
                        if self.entry_changed_handler_id is not None:
                            self.entry.handler_block(self.entry_changed_handler_id)
                        self.entry.set_text(target_row.user_input)
                        self.entry.set_position(-1)
                        # Unblock the "changed" signal
                        if self.entry_changed_handler_id is not None:
                            self.entry.handler_unblock(self.entry_changed_handler_id)
                return True

            # Handle Tab for non-autocomplete (select item name)
            elif keyval == Gdk.KEY_Tab and not self.showing_history:
                selected_row = self.list_box.get_selected_row()
                if not selected_row and self.current_results:
                    # No selection, select first item
                    first_row = self.list_box.get_row_at_index(0)
                    self.list_box.select_row(first_row)
                    selected_row = first_row

                if selected_row and hasattr(selected_row, "result"):
                    self.entry.set_text(selected_row.result.name)
                    self.entry.set_position(-1)
                return True

            # Handle Shift+Delete to remove a single history entry
            elif keyval == Gdk.KEY_Delete and state & Gdk.ModifierType.SHIFT_MASK:
                if self.showing_history:
                    selected_row = self.list_box.get_selected_row()
                    if selected_row and hasattr(selected_row, "history_entry"):
                        entries_to_remove = [selected_row.history_entry]
                        removed_count = (
                            self.history_manager.remove_history_entries_by_ids(
                                entries_to_remove
                            )
                        )
                        if removed_count > 0:
                            logger.info(
                                f"Removed 1 history entry with Shift+Delete: {selected_row.history_entry.get('user_input', '')}"
                            )
                            self._refresh_history_view_after_delete()
                        return True
                return (
                    False  # Allow other handlers if not showing history or no selection
                )

            # Handle Ctrl+Delete to remove multiple selected history entries
            elif keyval == Gdk.KEY_Delete and state & Gdk.ModifierType.CONTROL_MASK:
                if self.showing_history:
                    selected_rows = self.list_box.get_selected_rows()
                    if selected_rows:
                        entries_to_remove = [
                            row.history_entry
                            for row in selected_rows
                            if hasattr(row, "history_entry")
                        ]
                        if entries_to_remove:
                            removed_count = (
                                self.history_manager.remove_history_entries_by_ids(
                                    entries_to_remove
                                )
                            )
                            if removed_count > 0:
                                logger.info(
                                    f"Removed {removed_count} history entries with Ctrl+Delete."
                                )
                                self._refresh_history_view_after_delete()
                            return True
                return (
                    False  # Allow other handlers if not showing history or no selection
                )

        # Global hotkeys (work anywhere in the window)
        # Handle Ctrl+Q to quit (hide first for snappy response)
        if keyval == Gdk.KEY_q and state & Gdk.ModifierType.CONTROL_MASK:
            logger.info("Ctrl+Q pressed, hiding window and quitting application")
            self.hide()  # Hide immediately for snappy response
            from gi.repository import GLib

            GLib.timeout_add(50, lambda: Gtk.main_quit())  # Delayed clean shutdown
            return True

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
            if self.showing_history and hasattr(row, "user_input"):
                # History item activated - populate entry and search
                self.entry.set_text(row.user_input)
                self.on_entry_changed(self.entry)
            elif hasattr(row, "result"):
                # Regular search result activated
                self.execute_result(row.result, None)

    def on_list_box_selection_changed(self, list_box) -> None:
        """Handle selection changes in the list box."""
        if self.showing_history:
            selected_rows = list_box.get_selected_rows()
            count = len(selected_rows)
            if count > 0:
                self.result_count_label.set_text(
                    f"{count} selected item{'s' if count != 1 else ''}"
                )
                self.result_count_label.show()
            else:
                self.result_count_label.hide()

    def _build_executed_command(self, result: SearchResult) -> str:
        """
        Build the complete command that represents what was actually executed.
        This ensures history shows the matched command name, not the partial user input.

        Args:
            result: The SearchResult that was executed

        Returns:
            Complete command string for history storage
        """
        # Use the result name (matched command) as the base
        base_command = result.name

        # Add any arguments if present in metadata
        args = result.metadata.get("args", [])
        if args:
            base_command = base_command + " " + " ".join(args)

        return base_command

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
            # Check if this result should be tracked in history
            should_track = result.metadata.get("track_history", True)

            if should_track:
                # Build the complete command that represents what was actually executed
                # This should be the full application name/command, not the partial user input
                executed_command = self._build_executed_command(result)

                # Pass the icon pixbuf to history for storage (especially for executable plugin)
                icon_pixbuf = result.icon if result.plugin_id == "executable" else None
                user_input_for_history = self.entry.get_text().strip()
                self.history_manager.add_execution(
                    result.plugin_id,
                    result.item_id,
                    executed_command,
                    user_input_for_history,
                    result.description,
                    icon_pixbuf,
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

        # Clear entry and reset state
        self.entry.set_text("")
        self._clear_list_box_and_hide()

        # Show recent history if available
        self._show_recent_history()

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
        state = event.state
        nav_keys = [
            Gdk.KEY_Up,
            Gdk.KEY_Down,
            Gdk.KEY_Tab,
            Gdk.KEY_Page_Up,
            Gdk.KEY_Page_Down,
        ]

        # Handle Ctrl+Q to quit (global hotkey)
        if keyval == Gdk.KEY_q and state & Gdk.ModifierType.CONTROL_MASK:
            logger.info("Ctrl+Q pressed, hiding window and quitting application")
            self.hide()  # Hide immediately for snappy response
            from gi.repository import GLib

            GLib.timeout_add(50, lambda: Gtk.main_quit())  # Delayed clean shutdown
            return True

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

    def _refresh_history_view_after_delete(self):
        """
        Refreshes the history view after items have been deleted.
        This clears the current view and re-shows the updated recent history.
        """
        self.entry.set_text("")
        self._clear_list_box_and_hide()
        self._show_recent_history()
        self.entry.grab_focus()
