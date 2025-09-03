#!/usr/bin/env python3

from core.history_manager import HistoryManager
from core.plugin_manager import PluginManager
from gi.repository import Gtk, Gdk, Pango, GLib
from launcher.utils.icon_utils import load_custom_icon, get_fallback_icon
from launcher.utils.result_deduplicator import ResultDeduplicator
from launcher.utils.text_highlighter import TextHighlighter
from plugins.base import SearchResult
from typing import Dict, Any, List
from ui.css_manager import CssManager
import gi
import logging

gi.require_version("Gtk", "3.0")
logger = logging.getLogger(__name__)


class AppListItem(Gtk.ListBoxRow):
    """Custom list box row for displaying a search result"""

    def __init__(
        self,
        result: SearchResult,
        icon_size: int,
        launch_count: int = 0,
        query: str = "",
    ):
        super().__init__()
        self.set_name("app-list-item")
        self.result = result
        self.query = query

        # Add plugin-specific CSS class
        style_context = self.get_style_context()
        plugin_class = f"{result.plugin_id}-result"
        style_context.add_class(plugin_class)

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
        self._apply_highlighting(name_label, result.name, self.query)
        name_box.pack_start(name_label, True, True, 0)

        if launch_count > 0:
            count_label = Gtk.Label(
                label=f"Used {launch_count} time{'s' if launch_count != 1 else ''}"
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
            self._apply_highlighting(desc_label, result.description, self.query)

        vbox.pack_start(desc_label, True, True, 0)

        hbox.pack_start(vbox, True, True, 0)
        self.add(hbox)

    def _load_result_icon(self, result: SearchResult, size: int):
        """Load icon for a search result using icon_spec"""
        if result.icon_spec:
            return load_custom_icon(result.icon_spec, size)
        else:
            return get_fallback_icon(size)

    def _apply_highlighting(self, label: Gtk.Label, text: str, query: str) -> None:
        """Apply highlighting to a label based on the search query using flexible highlighting"""
        if not text or not query:
            label.set_text(text or "")
            return

        query = query.strip()
        if not query:
            label.set_text(text)
            return

        try:
            highlighter = TextHighlighter()
            segments = highlighter.get_highlight_segments(text, query)

            if not segments:
                label.set_text(text)
                return

            markup = highlighter.build_markup(text, segments, label)
            label.set_markup(markup)

        except Exception:
            label.set_text(text)


class LauncherWindow(Gtk.Window):
    """Main launcher window"""

    _quit_scheduled = False

    def __init__(
        self,
        plugin_manager: PluginManager,
        history_manager: HistoryManager,
        config: Dict[str, Any],
        foreground_mode: bool = False,
    ):
        super().__init__(title="Launcher")

        CssManager.load_default_css()

        self.plugin_manager = plugin_manager
        self.history_manager = history_manager
        self.result_deduplicator = ResultDeduplicator()
        self.config = config
        self.foreground_mode = foreground_mode

        general_config = config.get("general", {})
        self.icon_size = general_config.get("icon_size")
        self.window_width = general_config.get("window_width")
        self.window_height = general_config.get("window_height")
        self.window_height_results = general_config.get("window_height_results")

        self.set_decorated(False)
        self.set_default_size(self.window_width, self.window_height)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_name("launcher-window")

        # Connect signals
        self.connect("delete-event", self.on_delete_event)
        self.connect("key-press-event", self.on_key_press)
        self.connect("focus-out-event", self.on_focus_out)

        # Keep a reference to the main loop quit function without leaking Gtk details to main
        self._schedule_quit = lambda reason=None: GLib.idle_add(Gtk.main_quit)

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

        # Track if user is navigating with keys
        self.user_navigating = False

        # Make sure the scrolled window is hidden initially
        self.scrolled.hide()

        self.entry.grab_focus()

    def _clear_list_box_and_hide(self):
        """Clears all items from the list box and hides the results area."""
        for child in self.list_box.get_children():
            child.destroy()
        self.scrolled.hide()
        self.result_count_label.set_text("")
        self.result_count_label.hide()
        self.resize(self.window_width, self.window_height)

    def _show_recent_history(self):
        """Show all history items when launcher opens with empty input, with scrolling support."""
        if not self.history_manager:
            return

        all_history = self.history_manager.get_recent_history(100)
        history_results = self._convert_history_entries_to_results(all_history)

        if not history_results:
            return

        self._populate_list_box_with_results(history_results)
        self._finalize_history_display(history_results)

    def _convert_history_entries_to_results(
        self, all_history: List[Dict[str, Any]]
    ) -> List[SearchResult]:
        """Convert history entries to SearchResults (simple mapping, use info directly)"""
        results = []
        for history_entry in all_history:
            if not history_entry.get("user_input"):
                continue

            plugin_id = history_entry.get("plugin_id", "")
            item_id = history_entry.get("item_id", "")
            user_input = history_entry.get("user_input", "")
            result_name = history_entry.get("result_name")
            name = self._build_hybrid_display_name(user_input, result_name)
            description = history_entry.get("description", "")
            icon_spec = history_entry.get("icon_spec") or ""

            result = SearchResult(
                plugin_id="history",
                item_id=f"history_{plugin_id}_{item_id}",
                name=name,
                description=description,
                icon_spec=icon_spec,
                score=0,
            )
            result.metadata = {
                "original_plugin_id": plugin_id,
                "original_item_id": item_id,
                "user_input": history_entry.get("user_input", ""),
                "usage_count": history_entry.get("usage_count", 0),
                "history_entry": history_entry,
            }
            results.append(result)
        return results

    def _build_hybrid_display_name(self, user_input: str, result_name: str) -> str:
        """
        Build hybrid display name:
        - If result_name available: use canonical name + any args (e.g., "Firefox" or "Firefox --new-window")
        - If no result_name: use original input (e.g., "fire")
        """
        try:
            if not user_input:
                return "Unknown Command"

            # If we have a canonical result name, use it
            if result_name and result_name != user_input:
                # Check if user input has arguments (contains spaces)
                user_parts = user_input.split()
                if len(user_parts) > 1:
                    # User input has arguments, use canonical name + args
                    args = " ".join(user_parts[1:])
                    return f"{result_name} {args}"
                else:
                    # No arguments, just use canonical name
                    return result_name
            else:
                # No result_name available, use original input
                return user_input

        except Exception as e:
            logger.warning(
                f"Error building hybrid display name: {e} - using user_input"
            )
            return user_input if user_input else "Unknown Command"

    def _clear_list_box(self):
        """Clear all items from the list box"""
        for child in self.list_box.get_children():
            child.destroy()

    def _populate_list_box_with_results(self, results: List[SearchResult]):
        """Populate the list box with SearchResults"""
        self._clear_list_box()
        for result in results:
            history_count = result.metadata.get("usage_count", 0)
            list_item = AppListItem(
                result,
                icon_size=self.icon_size or 48,
                launch_count=history_count,
                query="",
            )
            list_item.set_name("history-item")
            list_item.history_entry = result.metadata.get("history_entry", {})
            self.list_box.add(list_item)

    def _finalize_history_display(self, history_results: List[SearchResult]):
        """Finalize the history display setup"""
        self.list_box.show_all()
        self.scrolled.show()
        count_text = f"{len(history_results)} history item{'s' if len(history_results) != 1 else ''}"
        self._setup_results_display(history_results, count_text)

    def _execute_history_item(self, history_entry: Dict[str, Any]) -> None:
        """
        Execute an item from history using the history plugin.
        Falls back to regular search if execution fails.
        """
        if not self.history_plugin or not self.plugin_manager:
            logger.error("History plugin or plugin manager not available.")
            # Fallback to regular search
            user_input = history_entry.get("user_input", "")
            self.entry.set_text(user_input)
            self.on_entry_changed(self.entry)
            return

        # Convert history_entry to SearchResult for execution by the history plugin
        # The history plugin's execute method expects a SearchResult
        history_search_result = self.history_plugin._create_history_search_result(
            history_entry
        )

        if history_search_result:
            success = self.history_plugin.execute(history_search_result)
        else:
            success = False
            logger.error(
                f"Failed to create SearchResult from history entry: {history_entry.get('user_input', 'N/A')}"
            )

        if not success:
            # Fallback to regular search
            user_input = history_entry.get("user_input", "")
            self.entry.set_text(user_input)
            self.on_entry_changed(self.entry)

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
            # For history plugin results, use the stored usage count, otherwise look it up
            if result.plugin_id == "history":
                history_count = result.metadata.get("usage_count", 0)
            else:
                history_count = self.history_manager.get_usage_count(
                    result.plugin_id, result.item_id
                )

            list_item = AppListItem(
                result,
                icon_size=self.icon_size or 48,
                launch_count=history_count,
                query=self.entry.get_text().strip(),
            )

            if result.plugin_id == "history":
                list_item.set_name("history-search-result")
                list_item.get_style_context().add_class("history-result")

            self.list_box.add(list_item)

        self.list_box.show_all()
        self.scrolled.show()
        # Scroll to top when results change
        vadj = self.scrolled.get_vadjustment()
        if vadj:
            vadj.set_value(vadj.get_lower())

        # Use unified display setup
        count_text = (
            f"{len(results_to_display)} result{'s' if len(results_to_display) != 1 else ''}"
            if results_to_display
            else ""
        )
        self._setup_results_display(results_to_display, count_text)

        if not self.user_navigating:
            self.list_box.unselect_all()

    def _setup_results_display(self, items, count_text=""):
        """Unified method to set up the results display area with consistent sizing and scrolling."""
        # Show/hide result count
        if count_text:
            self.result_count_label.set_text(count_text)
            self.result_count_label.show()
        else:
            self.result_count_label.set_text("")
            self.result_count_label.hide()

        # Calculate display height - always use results window height for consistency
        display_height = self.window_height_results - self.window_height
        self.resize(self.window_width, self.window_height_results)
        self.scrolled.set_size_request(-1, display_height)

        # Set scrolling policy based on number of items
        if len(items) > 5:
            self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.ALWAYS)
            self.scrolled.set_overlay_scrolling(False)
        else:
            self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)

        # Scroll to top when results change
        vadj = self.scrolled.get_vadjustment()
        if vadj:
            vadj.set_value(vadj.get_lower())

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

        # First, adjust scores based on history for all current results
        # Apply deduplication based on plugin scores (no double scoring needed)
        self.current_results = self.result_deduplicator.deduplicate_results(
            self.current_results
        )

        # Sort by score only - history plugin already has prioritized scores
        self.current_results.sort(key=lambda r: r.score, reverse=True)

        # Truncate results - cache max_results to avoid repeated config lookups
        if not hasattr(self, "_cached_max_results"):
            self._cached_max_results = self.config.get("general", {}).get(
                "max_results", 15
            )
        self.current_results = self.current_results[: self._cached_max_results]

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
        # Cancel any pending search
        if self._search_timeout_id:
            GLib.source_remove(self._search_timeout_id)

        self._search_timeout_id = GLib.timeout_add(
            self._search_delay_ms, self._perform_search
        )

    def _perform_search(self) -> bool:
        """Actually perform the search (called after debounce delay)"""
        self._search_timeout_id = None  # Clear timeout ID

        # Cancel any pending result updates from previous search
        if self._result_update_timeout_id:
            GLib.source_remove(self._result_update_timeout_id)
            self._result_update_timeout_id = None

        self.user_navigating = False  # Reset navigation state
        query = self.entry.get_text().strip()

        self.current_results.clear()
        self.autocomplete_matches.clear()
        self.autocomplete_index = -1

        if not query:
            self._clear_list_box_and_hide()
            self._show_recent_history()
            return False

        # Check for autocomplete matches - cache history manager check
        if self.history_manager:
            self.autocomplete_matches = self.history_manager.get_matching_history(
                query, 5
            )

        self.active_search_id += 1
        self.plugin_manager.search(
            query,
            self.active_search_id,
            self.handle_plugin_results,
            self.handle_search_finished,
        )
        return False

    def _navigate_selection(self, direction: int, state) -> bool:
        """Navigate selection in the results list by direction (+1 down, -1 up), wrapping around.
        Updates the entry line with the selected row's user_input without triggering a search.
        """
        self.user_navigating = True
        children = self.list_box.get_children()
        if not children:
            return True

        selected_row = self.list_box.get_selected_row()
        if selected_row:
            index = selected_row.get_index()
            target_index = (index + direction) % len(children)
        else:
            target_index = 0 if direction > 0 else len(children) - 1

        target_row = self.list_box.get_row_at_index(target_index)

        if not (state & Gdk.ModifierType.SHIFT_MASK):
            self.list_box.unselect_all()
        self.list_box.select_row(target_row)

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
            if self.scrolled.get_visible() and self.plugin_manager is not None:
                selected_row = self.list_box.get_selected_row()
                row = selected_row
                if not row and self.list_box.get_children():
                    row = self.list_box.get_row_at_index(0)
                if row:
                    # Prefer using the SearchResult if available
                    if hasattr(row, "result"):
                        self.execute_result(row.result, event)
                        return True
                    # Fallback: if it's a raw history entry without a result
                    if hasattr(row, "history_entry"):
                        self._execute_history_item(row.history_entry)
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
                    entries_to_remove = []

                    for row in selected_rows:
                        # If this row corresponds to a history entry, capture it for removal
                        if hasattr(row, "history_entry"):
                            entries_to_remove.append(row.history_entry)
                        elif (
                            hasattr(row, "result") and row.result.plugin_id == "history"
                        ):
                            history_entry = row.result.metadata.get("history_entry")
                            if history_entry:
                                entries_to_remove.append(history_entry)

                    if entries_to_remove:
                        removed_count = (
                            self.history_manager.remove_history_entries_by_ids(
                                entries_to_remove
                            )
                        )
                        if removed_count > 0:
                            count_text = f"{removed_count} history {'entry' if removed_count == 1 else 'entries'}"
                            logger.info(f"Removed {count_text} with Shift+Delete.")

                            # If no query text, we're showing recent history; otherwise refresh search
                            if not self.entry.get_text().strip():
                                self._refresh_history_view_after_delete()
                            else:
                                # Refresh the current search to update results
                                self.on_entry_changed(self.entry)
                        return True
                return False  # Allow other handlers if no selection

        return False

    def on_row_activated(self, list_box, row) -> None:
        """Handle activation of a row in the results list"""
        if row:
            if hasattr(row, "history_entry"):
                # History item activated - execute it directly
                self._execute_history_item(row.history_entry)
            elif hasattr(row, "result"):
                # Regular search result activated
                self.execute_result(row.result, None)

    def _build_executed_command(self, result: SearchResult) -> str:
        """
        Build the complete command that represents what was actually executed.
        This should be the actual command that was passed to subprocess, not a display name.

        Args:
            result: The SearchResult that was executed

        Returns:
            Actual command string that was executed (or would be executed)
        """
        actual_command = result.metadata.get("actual_executed_command")
        if actual_command:
            return actual_command

        command = result.metadata.get("command")
        if command:
            args = result.metadata.get("args", [])
            if args:
                return command + " " + " ".join(args)
            return command

        base_command = result.name
        args = result.metadata.get("args", [])
        if args:
            base_command = base_command + " " + " ".join(args)
        return base_command

    def execute_result(self, result: SearchResult, event=None) -> None:
        """Execute the given search result"""
        if not self._validate_managers():
            return

        self._capture_modifier_state(result, event)

        if self.plugin_manager.execute(result):
            self._handle_history_tracking(result)
            result.metadata["history_manager"] = self.history_manager
            self.close_window()

    def _validate_managers(self) -> bool:
        """Validate that required managers are initialized"""
        if self.history_manager is None or self.plugin_manager is None:
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

        user_input = self.entry.get_text().strip()
        should_store = self.history_manager.should_store_in_history(user_input, result)

        if should_store:
            self._store_new_history_entry(result, user_input)
        else:
            self._increment_existing_usage(result, user_input)

    def _store_new_history_entry(self, result: SearchResult, user_input: str) -> None:
        """Store a new history entry for the executed result"""
        if not result.metadata.get("original_plugin_id"):
            result.metadata["original_plugin_id"] = result.plugin_id
        if not result.metadata.get("original_item_id"):
            result.metadata["original_item_id"] = result.item_id

        self.history_manager.add_execution(result, user_input)

    def _increment_existing_usage(self, result: SearchResult, user_input: str) -> None:
        """Increment usage count for existing history entries"""
        self.history_manager.increment_usage_count(result.plugin_id, result.item_id)

    def show_and_focus(self):
        """Show window at consistent position and grab focus"""

        # Clear entry and reset state
        self.entry.set_text("")
        self._clear_list_box_and_hide()

        # Show history if managers are already initialized (e.g., when toggling existing instance)
        if self.history_manager is not None:
            self._show_recent_history()

        # Present window and grab focus
        self.show_all()
        self.present()

        # Use GLib.idle_add to ensure positioning and focus happen after window is mapped

        GLib.idle_add(self._delayed_focus_and_position)

    def _delayed_focus_and_position(self):
        """Position window and grab focus after window is fully shown and mapped"""
        try:
            if not self.get_visible() or not self.get_mapped():
                GLib.timeout_add(10, self._delayed_focus_and_position)
                return False

            if self.get_window():
                self.get_window().raise_()
                self.get_window().focus(0)

            self.entry.grab_focus()
            self.present()
            self.activate_focus()

        except Exception:
            pass

        return False

    def on_delete_event(self, widget, event):
        """Handle window delete event - hide or quit in foreground mode"""
        if self.foreground_mode:
            # In foreground mode, closing the window should quit the app via GTK loop
            self.request_quit("window delete")
        else:
            # In singleton mode, just hide the window
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
            # Route quit through launcher's quit logic
            self.request_quit("Ctrl+Q")
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
            # Quit GTK loop through launcher's own method
            self.request_quit("close_window")
        else:
            self.hide()
        return True

    def request_quit(self, reason: str = ""):
        """Schedule quitting the main loop once, allowing cleanup in finally blocks.

        This keeps GTK knowledge within the launcher window and avoids main importing Gtk.
        """
        if LauncherWindow._quit_scheduled:
            return
        LauncherWindow._quit_scheduled = True
        logger.info(f"LauncherWindow requested quit: {reason}")
        # Quit on idle to ensure signal handlers and UI events complete
        self._schedule_quit(reason)

    def update_with_full_config(self, plugin_manager, history_manager, config):
        """Update the window with the full configuration after initialization"""
        self.plugin_manager = plugin_manager
        self.history_manager = history_manager
        self.history_plugin = self.plugin_manager.plugins.get(
            "history"
        )  # Add this line
        self.config = config

        # Update window size if needed - cache general config
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

        # Show recent history now that history_manager is available
        # Only show if the entry is empty (initial launch state)
        if not self.entry.get_text().strip():
            self._show_recent_history()

    def _refresh_history_view_after_delete(self):
        """
        Refreshes the history view after items have been deleted.
        This clears the current view and re-shows the updated recent history.
        """
        self.entry.set_text("")
        self._clear_list_box_and_hide()
        self._show_recent_history()
        self.entry.grab_focus()
