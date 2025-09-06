import logging
from typing import List

from gi.repository import Gdk, GLib, Gtk, Pango
from plugins.base import SearchResult
from ui.css_manager import CssManager

from launcher import services
from launcher.utils.icon_utils import get_fallback_icon, load_custom_icon
from launcher.utils.result_deduplicator import ResultDeduplicator
from launcher.utils.text_highlighter import TextHighlighter

logger = logging.getLogger(__name__)


class AppListItem(Gtk.ListBoxRow):
    """Custom list box row for displaying a search result"""

    def __init__(
        self,
        result: SearchResult,
        icon_size: int,
        usage_count: int = 0,
        query: str = "",
    ):
        super().__init__()
        self.set_name("app-list-item")
        self.result = result
        self.query = query

        # Add plugin-specific CSS class
        style_context = self.get_style_context()
        style_context.add_class(f"{result.plugin_id}-result")

        # Create a horizontal box to hold the icon and text
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox.set_border_width(8)
        hbox.set_property("height-request", 60)

        # Load and display icon
        icon_pixbuf = self._load_result_icon(result, icon_size)
        if icon_pixbuf:
            icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            icon_box.set_size_request(icon_size, icon_size)
            icon = Gtk.Image.new_from_pixbuf(icon_pixbuf)
            icon_box.pack_start(icon, True, False, 0)
            hbox.pack_start(icon_box, False, False, 0)
        else:
            spacer = Gtk.Box()
            spacer.set_size_request(icon_size, icon_size)
            hbox.pack_start(spacer, False, False, 0)

        # Create a vertical box for name and description
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        # Create a horizontal box for name and count
        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

        # Add the name
        name_label = Gtk.Label(label=result.name)  # Always set the initial text
        name_label.set_halign(Gtk.Align.START)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        name_label.set_name("app-name")

        # Apply highlighting based on current query (UI handles highlighting logic)
        self._apply_highlighting(name_label, result.name, self.query, "name")
        name_box.pack_start(name_label, True, True, 0)

        if usage_count > 0:
            count_label = Gtk.Label(
                label=f"Used {usage_count} time{'s' if usage_count != 1 else ''}"
            )
            count_label.set_halign(Gtk.Align.END)
            count_label.get_style_context().add_class("dim-label")
            count_label.set_name("app-count")
            name_box.pack_end(count_label, False, False, 5)

        vbox.pack_start(name_box, True, True, 0)

        desc_label = Gtk.Label(label=result.description or "")
        desc_label.set_halign(Gtk.Align.START)
        desc_label.set_name("app-description")
        desc_label.get_style_context().add_class("dim-label")
        desc_label.set_ellipsize(Pango.EllipsizeMode.END)

        # Apply highlighting to description
        if result.description:
            self._apply_highlighting(
                desc_label, result.description, self.query, "description"
            )

        vbox.pack_start(desc_label, True, True, 0)

        hbox.pack_start(vbox, True, True, 0)
        self.add(hbox)

    def _load_result_icon(self, result: SearchResult, size: int):
        """Load icon for a search result using icon_spec"""
        if result.icon_spec:
            return load_custom_icon(result.icon_spec, size)
        else:
            return get_fallback_icon(size)

    def _apply_highlighting(
        self, label: Gtk.Label, text: str, query: str, field_type: str
    ) -> None:
        """Apply highlighting to a label based on the search query using flexible highlighting"""
        if not text or not query:
            label.set_text(text or "")
            return

        query = query.strip()
        if not query:
            label.set_text(text)
            return

        try:
            # Check if we have hilight information from the search result
            hilight = getattr(self.result, "hilight", None)

            # Get indices for the specific field being rendered
            if hilight:
                indices = hilight.get_indices_for_field(field_type)
                if indices:
                    # Use exact indices with config-based styling
                    highlighter = TextHighlighter()
                    markup = highlighter.build_markup_from_indices(text, indices)
                    label.set_markup(markup)
                else:
                    # No highlighting for this field - just set plain text
                    label.set_text(text)
            else:
                # No highlighting - just set plain text
                label.set_text(text)

        except Exception:
            label.set_text(text)


class LauncherWindow(Gtk.Window):
    """Main launcher window"""

    _shutdown_requested = False

    def __init__(
        self,
        foreground_mode: bool = False,
    ):
        super().__init__(title="Launcher")

        CssManager.load_default_css()

        self.foreground_mode = foreground_mode
        self.result_deduplicator = ResultDeduplicator()

        self.icon_size = services.config.system.icon_size
        self.window_width = services.config.system.window_width
        self.window_height = services.config.system.window_height

        self.set_decorated(False)
        self.set_default_size(self.window_width, self.window_height)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_name("launcher-window")

        # Keep a reference to the main loop quit function without leaking Gtk details to main
        self._schedule_quit = lambda reason=None: GLib.idle_add(Gtk.main_quit)

        # Create a vertical box for the layout
        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.vbox.set_border_width(services.config.system.border_width)
        self.add(self.vbox)

        # Create a box for the entry field and result count
        entry_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        entry_box.set_name("launcher-entry-container")

        # Initialize the entry field
        self.entry = Gtk.Entry()
        self.entry.set_activates_default(True)
        self.entry.set_name("launcher-entry")
        self.entry.connect("key-press-event", self.on_entry_key_press)

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
        self.scrolled.set_propagate_natural_height(True)

        self.vbox.pack_start(self.scrolled, True, True, 5)

        # Create the list box for results
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        self.list_box.connect("row-activated", self.on_row_activated)
        self.list_box.set_name("results-list")
        self.scrolled.add(self.list_box)

        # Current search results
        self.current_results: List[SearchResult] = []
        self.active_search_id: int = 0

        # History-related state
        self.autocomplete_matches: List[str] = []
        self.autocomplete_index = -1

        # Search debouncing
        self._search_timeout_id = None
        self._search_delay_ms = 50

        # Result update stabilization
        self._result_update_timeout_id = None
        self._result_update_delay_ms = 100  # Delay to stabilize result updates

        # Make sure the scrolled window is hidden initially
        self.scrolled.hide()

        self.connect("focus-out-event", self.on_focus_out)
        self.connect("key-press-event", self.on_key_press)

    def _clear_list_box_and_hide(self):
        """Clears all items from the list box and hides the results area."""
        for child in self.list_box.get_children():
            child.destroy()
        self.scrolled.hide()
        self.result_count_label.set_text("")
        self.result_count_label.hide()
        self.resize(self.window_width, self.window_height)

    def _clear_list_box(self):
        """Clear all items from the list box"""
        for child in self.list_box.get_children():
            child.destroy()

    def _populate_list_box(self, results: List[SearchResult]):
        """Populates the list box with the given results and updates UI elements."""

        for child in self.list_box.get_children():
            child.destroy()

        for result in results:
            history_count = (
                result.metadata.get("usage_count", 0)
                if result.plugin_id == "history"
                else 0
            )

            list_item = AppListItem(
                result,
                icon_size=self.icon_size or 48,
                usage_count=history_count,
                query=self.entry.get_text().strip(),
            )

            self.list_box.add(list_item)

        self.list_box.show_all()
        self.scrolled.show()
        self._update_results_count(results)

    def _update_results_count(self, results):
        """Unified method to set up the results display area with consistent sizing and scrolling."""

        count = len(results)

        # Show/hide result count
        if count:
            count_text = f"{count} result{'s' if count != 1 else ''}"
            self.result_count_label.set_text(count_text)
            self.result_count_label.show()
        else:
            self.result_count_label.set_text("")
            self.result_count_label.hide()

        # Set scrolling policy based on number of items
        if count > 5:
            self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.ALWAYS)
            self.scrolled.set_overlay_scrolling(False)
        else:
            self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)

    def handle_plugin_results(
        self, search_id: int, plugin_id: str, plugin_results: List[SearchResult]
    ):
        """Callback for when a plugin returns results."""
        if search_id != self.active_search_id:
            return

        # Add results to current collection
        self.current_results.extend(plugin_results)

        # Process and update UI with stabilization delay
        self._schedule_result_update(search_id)

    def _schedule_result_update(self, search_id: int):
        """Schedule a result update with stabilization delay to prevent flickering."""
        # Check if we have any high-priority results that should be shown immediately
        has_high_priority = any(result.score >= 1000 for result in self.current_results)

        if has_high_priority:
            # Show high-priority results immediately (exact matches)
            if self._result_update_timeout_id:
                GLib.source_remove(self._result_update_timeout_id)
                self._result_update_timeout_id = None
            self._perform_result_update(search_id)
        else:
            # Use stabilization delay for lower-priority results
            if self._result_update_timeout_id:
                GLib.source_remove(self._result_update_timeout_id)

            # Schedule new update
            self._result_update_timeout_id = GLib.timeout_add(
                self._result_update_delay_ms,
                lambda: self._perform_result_update(search_id),
            )

    def _perform_result_update(self, search_id: int) -> bool:
        """Actually update the UI with current results (called after stabilization delay)."""
        self._result_update_timeout_id = None  # Clear timeout ID

        if search_id != self.active_search_id:
            return False  # Ignore stale updates

        self.current_results = self.result_deduplicator.deduplicate_results(
            self.current_results
        )

        self.current_results.sort(key=lambda r: r.score, reverse=True)
        self.current_results = self.current_results[
            : services.config.system.max_results
        ]

        self._populate_list_box(self.current_results)

        return False  # Remove from timeout queue

    def handle_search_finished(self, search_id: int):
        """Callback for when all plugins have finished searching."""
        if search_id != self.active_search_id:
            return

        # Cancel any pending result update and perform final update immediately
        if self._result_update_timeout_id:
            GLib.source_remove(self._result_update_timeout_id)
            self._result_update_timeout_id = None

        # Perform final result processing and UI update
        self._perform_result_update(search_id)

        # Always show dropdown if user has typed something, even if no results
        query_text = self.entry.get_text().strip()
        if query_text and not self.current_results:
            self._populate_list_box([])
        elif not self.current_results:
            self._clear_list_box_and_hide()

    def on_entry_changed(self, widget) -> None:
        """Handle text changes in the entry field with debouncing."""
        if self._search_timeout_id:
            GLib.source_remove(self._search_timeout_id)

        self._search_timeout_id = GLib.timeout_add(self._search_delay_ms, self._search)

    def _show_recent_history(self) -> None:
        """Show recent history."""
        self._clear_list_box_and_hide()
        results = services.history_manager.get_history_results()
        if results:
            self._populate_list_box(results)

    def _search(self) -> bool:
        """Actually perform the search (called after debounce delay)"""
        self._search_timeout_id = None  # Clear timeout ID

        # Cancel any pending result updates from previous search
        if self._result_update_timeout_id:
            GLib.source_remove(self._result_update_timeout_id)
            self._result_update_timeout_id = None

        query = self.entry.get_text().strip()

        self.current_results.clear()
        self.autocomplete_matches.clear()
        self.autocomplete_index = -1

        if not query:
            self._show_recent_history()
            return False

        # Check for autocomplete matches - cache history manager check
        self.autocomplete_matches = services.history_manager.get_matching_history(
            query, 5
        )
        self.active_search_id += 1
        services.plugin_manager.search(
            query,
            self.active_search_id,
            self.handle_plugin_results,
            self.handle_search_finished,
        )
        return False

    def _navigate_selection(self, direction: int, state) -> bool:
        """Navigate selection in the results list by direction (+1 down, -1 up), supporting shift+arrow multi-selection like typical listboxes."""
        children = self.list_box.get_children()
        if not children:
            return True

        shift_pressed = bool(state & Gdk.ModifierType.SHIFT_MASK)

        # Track anchor for shift selection
        if not hasattr(self, "_selection_anchor") or not shift_pressed:
            # Set anchor to current selection or to-be-selected row
            selected_row = self.list_box.get_selected_row()
            if selected_row:
                self._selection_anchor = selected_row.get_index()
            else:
                self._selection_anchor = 0 if direction > 0 else len(children) - 1

        selected_row = self.list_box.get_selected_row()
        if selected_row:
            index = selected_row.get_index()
            target_index = index + direction
            if target_index < 0 or target_index >= len(children):
                return True
        else:
            target_index = 0 if direction > 0 else len(children) - 1

        target_row = self.list_box.get_row_at_index(target_index)

        if shift_pressed:
            # Select range from anchor to target_index (inclusive)
            anchor = self._selection_anchor
            start = min(anchor, target_index)
            end = max(anchor, target_index)
            self.list_box.unselect_all()
            for i in range(start, end + 1):
                row = self.list_box.get_row_at_index(i)
                self.list_box.select_row(row)
        else:
            self.list_box.unselect_all()
            self.list_box.select_row(target_row)
            self._selection_anchor = target_index

        # Ensure the selected row is visible
        adjustment = self.scrolled.get_vadjustment()
        if adjustment:
            row_alloc = target_row.get_allocation()
            adjustment.clamp_page(row_alloc.y, row_alloc.y + row_alloc.height)

        # Cancel any pending search while navigating
        if self._search_timeout_id:
            GLib.source_remove(self._search_timeout_id)
            self._search_timeout_id = None

        # Update the entry with the row's user_input without triggering search
        if not shift_pressed:
            if self.entry_changed_handler_id is not None:
                self.entry.handler_block(self.entry_changed_handler_id)
            self.entry.set_text(target_row.result.name)
            self.entry.set_position(-1)
            if self.entry_changed_handler_id is not None:
                self.entry.handler_unblock(self.entry_changed_handler_id)

        return True

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
            if self.scrolled.get_visible() and services.plugin_manager is not None:
                selected_row = self.list_box.get_selected_row()
                row = selected_row
                if not row and self.list_box.get_children():
                    row = self.list_box.get_row_at_index(0)
                if row:
                    self.execute_result(row.result, event)
                    return True
            return True

        if self.scrolled.get_visible():
            # Handle Down arrow
            if keyval == Gdk.KEY_Down:
                return self._navigate_selection(+1, state)

            # Handle Up arrow
            elif keyval == Gdk.KEY_Up:
                return self._navigate_selection(-1, state)

            # Handle Tab for non-autocomplete (select item name)
            elif keyval == Gdk.KEY_Tab:
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

            # Handle Shift+Delete to remove selected history entries (single or multiple)
            elif keyval == Gdk.KEY_Delete and state & Gdk.ModifierType.SHIFT_MASK:
                selected_rows = self.list_box.get_selected_rows()
                if selected_rows:
                    for row in selected_rows:
                        if hasattr(row, "result") and row.result.plugin_id == "history":
                            services.history_manager.remove_history_entry(
                                row.result.item_id
                            )
                            self.list_box.remove(row)
                    return True
                return False

        return False

    def on_row_activated(self, list_box, row) -> None:
        """Handle activation of a row in the results list"""
        if row and hasattr(row, "result"):
            self.execute_result(row.result, None)

    def execute_result(self, result: SearchResult, event=None) -> None:
        """Execute the given search result"""
        if not self._validate_managers():
            return

        self._capture_modifier_state(result, event)

        if services.plugin_manager.execute(result):
            result_to_track = result
            if result.plugin_id == "history":
                original_result_dict = result.metadata.get("original_result")
                if original_result_dict:
                    result_to_track = SearchResult.from_dict(original_result_dict)

            self._handle_history_tracking(result_to_track)
            self.close_window()

    def _validate_managers(self) -> bool:
        """Validate that required managers are initialized"""
        if services.history_manager is None or services.plugin_manager is None:
            logger.warning("Cannot execute result: managers not initialized yet")
            self.close_window()
            return False
        return True

    def _capture_modifier_state(self, result: SearchResult, event=None) -> None:
        """Capture and store modifier key states in result metadata"""
        if event:
            state = event.state
        else:
            keymap = Gdk.Keymap.get_default()
            state = keymap.get_modifier_state()

        result.metadata["shift_pressed"] = bool(state & Gdk.ModifierType.SHIFT_MASK)
        result.metadata["ctrl_pressed"] = bool(state & Gdk.ModifierType.CONTROL_MASK)
        result.metadata["alt_pressed"] = bool(state & Gdk.ModifierType.MOD1_MASK)
        result.metadata["cmd_pressed"] = bool(state & Gdk.ModifierType.META_MASK)

    def _handle_history_tracking(self, result: SearchResult) -> None:
        """Handle history tracking logic for executed results"""
        should_track = result.metadata.get("track_history", True)
        if not should_track:
            return

        services.history_manager.add_history(result)

    def show_and_focus(self):
        """Show window and grab focus"""
        self.show_all()
        self.present()
        self.entry.select_region(0, -1)
        self.entry.grab_focus()

    def on_delete_event(self, widget, event):
        """Handle window delete event - hide or quit in foreground mode"""
        if self.foreground_mode:
            self.shutdown("window delete")
        else:
            self.hide()
        return True

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

        if keyval == Gdk.KEY_q and state & Gdk.ModifierType.CONTROL_MASK:
            logger.info("Ctrl+Q pressed, quitting via launcher window")
            self.shutdown("Ctrl+Q")
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
            self.close_window()
        return False

    def close_window(self):
        """Hide the window or quit based on mode"""
        if self.foreground_mode:
            # Quit GTK loop through launcher's own method
            self.shutdown("close_window")
        else:
            self.hide()
        return True

    def shutdown(self, reason: str = ""):
        """Schedule quitting the main loop once, allowing cleanup in finally blocks.

        This keeps GTK knowledge within the launcher window and avoids main importing Gtk.
        """
        if LauncherWindow._shutdown_requested:
            return
        LauncherWindow._shutdown_requested = True

        self._schedule_quit(reason)

    def start(self):
        """Update the window with the full configuration after initialization"""

        # Store the signal handler ID for later connection/disconnection
        self.connect("delete-event", self.on_delete_event)
        self.entry_changed_handler_id = self.entry.connect(
            "changed", self.on_entry_changed
        )

        self._show_recent_history()
        self.entry.grab_focus()
