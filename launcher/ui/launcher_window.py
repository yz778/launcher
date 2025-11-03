import logging
from typing import List

from gi.repository import Gdk, GLib, Gtk, Pango

from launcher import services
from launcher.plugins.base import SearchResult
from launcher.utils.icon_cache import ICON_CACHE
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
        self.icon_widget = None  # Store reference to icon widget for async updates

        # Add plugin-specific CSS class
        style_context = self.get_style_context()
        style_context.add_class(f"{result.plugin_id}-result")

        # Create a horizontal box to hold the icon and text
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        # Load and display icon
        icon_pixbuf = self._load_result_icon(result, icon_size)
        icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        icon_box.set_size_request(icon_size, icon_size)

        if icon_pixbuf:
            self.icon_widget = Gtk.Image.new_from_pixbuf(icon_pixbuf)
            icon_box.pack_start(self.icon_widget, True, False, 0)
        else:
            self.icon_widget = None

        hbox.pack_start(icon_box, False, False, 0)

        # Create a vertical box for name and description
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.set_name("app-list-item-text")

        # Create a horizontal box for name and count
        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

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
            name_box.pack_end(count_label, False, False, 0)

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
        """Load icon for a search result using icon_spec with caching"""
        # First check the cache
        cached = ICON_CACHE.get(result.icon_spec, size)
        if cached:
            return cached

        if result.icon_spec:

            def icon_callback(pixbuf):
                if pixbuf and self.icon_widget is not None:
                    self.update_icon(pixbuf)
                    ICON_CACHE.set(result.icon_spec, size, pixbuf)

            return load_custom_icon(result.icon_spec, size, callback=icon_callback)
        else:
            return get_fallback_icon(size)

    def update_icon(self, pixbuf):
        """Update the icon widget with a new pixbuf"""
        if self.icon_widget is not None and pixbuf is not None:
            self.icon_widget.set_from_pixbuf(pixbuf)
        elif self.icon_widget is None and pixbuf is not None:
            parent = self.get_children()[0].get_children()[0]  # hbox -> icon_box
            self.icon_widget = Gtk.Image.new_from_pixbuf(pixbuf)
            parent.pack_start(self.icon_widget, True, False, 0)
            self.icon_widget.show()

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
            hilight = getattr(self.result, "hilight", None)
            indices = hilight.get_indices_for_field(field_type) if hilight else None

            if indices:
                highlighter = TextHighlighter()
                markup = highlighter.build_markup_from_indices(text, indices)
                label.set_markup(markup)
            else:
                label.set_text(text)

        except Exception:
            label.set_text(text)


class LauncherWindow(Gtk.Window):
    """Main launcher window"""

    _shutdown_requested = False
    _nav_keys = [
        Gdk.KEY_Up,
        Gdk.KEY_Down,
        Gdk.KEY_Tab,
        Gdk.KEY_Page_Up,
        Gdk.KEY_Page_Down,
    ]
    PAGE_SCROLL_AMOUNT = 5

    def __init__(
        self,
        foreground_mode: bool = False,
    ):
        super().__init__(title="Launcher")

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
        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.vbox.set_name("launcher-container")
        self.add(self.vbox)

        # Create a box for the entry field and result count
        entry_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        entry_box.set_name("launcher-search-container")

        # Initialize the entry field
        self.entry = Gtk.Entry()
        self.entry.set_activates_default(True)
        self.entry.set_name("launcher-search")
        self.entry.connect("key-press-event", self.on_entry_key_press)

        entry_box.pack_start(self.entry, True, True, 0)

        # Initialize the result count label
        self.result_count_label = Gtk.Label()
        self.result_count_label.set_halign(Gtk.Align.END)
        self.result_count_label.get_style_context().add_class("dim-label")
        self.result_count_label.set_name("result-count-label")
        entry_box.pack_end(self.result_count_label, False, False, 0)
        self.result_count_label.hide()

        self.vbox.pack_start(entry_box, False, False, 0)

        # Create a scrolled window for the results
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled.set_shadow_type(Gtk.ShadowType.NONE)
        self.scrolled.set_name("results-scrolled")

        # Set overlay scrolling to False to ensure scrollbar is always visible
        self.scrolled.set_overlay_scrolling(False)
        self.scrolled.set_propagate_natural_height(True)

        self.vbox.pack_start(self.scrolled, False, False, 0)
        self.scrolled.set_max_content_height(self.window_height)

        # Create the list box for results
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        self.list_box.connect("row-activated", self.on_row_activated)
        self.list_box.connect("row-selected", self.on_row_selected)
        self.list_box.connect("key-press-event", self.on_list_box_key_press)
        self.list_box.set_name("results-list")
        self.scrolled.add(self.list_box)

        # Current search results
        self.current_results: List[SearchResult] = []
        self.active_search_id: int = 0
        self.current_query: str = ""
        self.is_searching: bool = False

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

    def _clear_list_box(self):
        """Clear all items from the list box"""
        for child in self.list_box.get_children():
            child.destroy()

    def _populate_list_box(self, results: List[SearchResult]):
        """Populates the list box with the given results and updates UI elements."""

        for child in self.list_box.get_children():
            child.destroy()

        for result in results:
            # Check for custom rendering in priority order as per refactor plan

            # 1. Custom render callback (highest priority)
            if result.render_callback is not None:
                try:
                    widget = result.render_callback()
                    if widget and isinstance(widget, Gtk.Widget):
                        list_row = Gtk.ListBoxRow()
                        list_row.result = (
                            result  # Store result reference for compatibility
                        )
                        list_row.add(widget)
                        self.list_box.add(list_row)
                        continue
                except Exception as e:
                    logger.error(
                        f"Error executing render_callback for result {result.item_id}: {e}"
                    )
                    # Fall back to default rendering

            # 2. Predefined render modes (medium priority)
            elif result.render_mode is not None:
                widget = self._create_widget_for_render_mode(result)
                if widget:
                    list_row = Gtk.ListBoxRow()
                    list_row.result = result  # Store result reference for compatibility
                    list_row.add(widget)
                    self.list_box.add(list_row)
                    continue
                # Fall back to default rendering if widget creation failed

            # 3. Default behavior (backward compatibility)
            history_count = (
                result.metadata.get("usage_count", 0)
                if result.plugin_id == "history"
                else 0
            )

            list_item = AppListItem(
                result,
                icon_size=self.icon_size,
                usage_count=history_count,
                query=self.entry.get_text().strip(),
            )

            self.list_box.add(list_item)

        self.list_box.show_all()
        self.scrolled.show()
        self._update_results_count(results)
        self._scroll_to_top()

    def _create_widget_for_render_mode(self, result: SearchResult) -> Gtk.Widget:
        """Create a widget based on the specified render mode and content."""
        try:
            if result.render_mode == "text_view":
                return self._create_text_view_widget(result)
            elif result.render_mode == "image_buffer":
                return self._create_image_widget(result)
            else:
                logger.warning(f"Unsupported render mode: {result.render_mode}")
                return None
        except Exception as e:
            logger.error(
                f"Error creating widget for render mode {result.render_mode}: {e}"
            )
            return None

    def _create_text_view_widget(self, result: SearchResult) -> Gtk.Widget:
        """Create a TextView widget for displaying formatted text content."""
        text_view = Gtk.TextView()
        text_view.set_editable(False)
        text_view.set_cursor_visible(False)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD)

        buffer = text_view.get_buffer()
        if result.content:
            buffer.set_text(str(result.content))

        # Wrap in a scrolled window for long content
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_max_content_height(400)  # Limit height
        scrolled.add(text_view)

        return scrolled

    def _create_image_widget(self, result: SearchResult) -> Gtk.Widget:
        """Create an Image widget for displaying image content."""
        try:
            if result.content:
                if hasattr(result.content, "get_pixbuf"):
                    # Content is already a pixbuf
                    image = Gtk.Image.new_from_pixbuf(result.content)
                elif isinstance(result.content, str):
                    # Content is a file path
                    image = Gtk.Image.new_from_file(result.content)
                else:
                    logger.warning(
                        f"Invalid content type for Image: {type(result.content)}"
                    )
                    return None

                return image
            else:
                logger.warning("No content provided for image widget")
                return None

        except Exception as e:
            logger.error(f"Error creating image widget: {e}")
            return None

    def _update_results_count(self, results):
        """Unified method to set up the results display area with consistent sizing and scrolling."""

        count = len(results)

        # Show/hide result count
        if count:
            prefix_plugins = services.plugin_manager.get_current_prefix_plugins()
            if prefix_plugins:
                if len(prefix_plugins) == 1:
                    count_text = prefix_plugins[0].get_name()
                else:
                    additional_count = len(prefix_plugins) - 1
                    count_text = f"{prefix_plugins[0].get_name()} +{additional_count} plugin{'s' if additional_count != 1 else ''}"
            else:
                count_text = f"{count} result{'s' if count != 1 else ''}"

            self.result_count_label.set_text(count_text)
            self.result_count_label.show()
        else:
            self.result_count_label.set_text("")
            self.result_count_label.hide()

    def _scroll_to_top(self):
        """Scroll the results list to the top."""
        if self.scrolled.get_vadjustment():
            adjustment = self.scrolled.get_vadjustment()
            adjustment.set_value(0)

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
        """Schedule a result update with adaptive delay based on result type"""

        has_high_priority = any(result.score >= 1000 for result in self.current_results)

        # Use shorter delay for immediate feedback when possible
        delay = self._result_update_delay_ms
        if has_high_priority:
            delay = 10  # Show high-priority results faster
        elif len(self.current_results) < 5:  # Small result sets can update faster
            delay = 25

        if self._result_update_timeout_id:
            GLib.source_remove(self._result_update_timeout_id)

        # Schedule new update
        self._result_update_timeout_id = GLib.timeout_add(
            delay,
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

        # Limit and sort results: use plugin-specific max_results if only one plugin is active, otherwise use global default
        active_plugins = services.plugin_manager.get_current_prefix_plugins()
        max_results = services.config.system.max_results

        if len(active_plugins) == 1:
            plugin = active_plugins[0]
            max_results = plugin.config.get("max_results", max_results)

        self.current_results.sort(key=lambda r: r.score, reverse=True)
        self.current_results = self.current_results[:max_results]

        self._populate_list_box(self.current_results)

        return False  # Remove from timeout queue

    def handle_search_finished(self, search_id: int):
        """Callback for when all plugins have finished searching with proper sync"""
        if search_id != self.active_search_id:
            return

        # Mark search as complete
        self.is_searching = False

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
        """Actually perform the search with better synchronization"""
        self._search_timeout_id = None  # Clear timeout ID

        # Cancel any pending result updates from previous search
        if self._result_update_timeout_id:
            GLib.source_remove(self._result_update_timeout_id)
            self._result_update_timeout_id = None

        query = self.entry.get_text().strip()
        self.current_query = query  # Store current query for reference

        self.current_results.clear()
        self.autocomplete_matches.clear()
        self.autocomplete_index = -1

        if not query:
            self._show_recent_history()
            return False

        # Check for autocomplete matches
        self.autocomplete_matches = services.history_manager.get_matching_history(
            query, 5
        )
        self.active_search_id += 1
        self.is_searching = True  # Flag to track search state

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
            # Clamp target_index to valid range [0, len(children)-1]
            target_index = max(0, min(target_index, len(children) - 1))
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
        self._ensure_row_visible(target_row)

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
        """Handle key presses in the entry field with improved responsiveness"""
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

        # Handle Enter with immediate response and proper synchronization
        if keyval == Gdk.KEY_Return:
            # Cancel any pending search to prevent race conditions
            if self._search_timeout_id:
                GLib.source_remove(self._search_timeout_id)
                self._search_timeout_id = None

            # Process any pending UI events to ensure current state is reflected
            while Gtk.events_pending():
                Gtk.main_iteration()

            if services.plugin_manager is not None:
                selected_row = self.list_box.get_selected_row()

                # If no row is selected, default to the first result
                if not selected_row and self.list_box.get_children():
                    selected_row = self.list_box.get_row_at_index(0)

                # Execute the selected result (or return if no selection available)
                if selected_row and hasattr(selected_row, "result"):
                    self.execute_result(selected_row.result, event)
                    self.entry.set_text("")

                return True
            return True

        if self.scrolled.get_visible():
            # Handle Down arrow
            if keyval == Gdk.KEY_Down:
                return self._navigate_selection(+1, state)

            # Handle Up arrow
            elif keyval == Gdk.KEY_Up:
                return self._navigate_selection(-1, state)

            # Handle Page Down for scrolling
            elif keyval == Gdk.KEY_Page_Down:
                return self._navigate_selection(+self.PAGE_SCROLL_AMOUNT, state)

            # Handle Page Up for scrolling
            elif keyval == Gdk.KEY_Page_Up:
                return self._navigate_selection(-self.PAGE_SCROLL_AMOUNT, state)

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

    def on_row_selected(self, list_box, row) -> None:
        """Handle selection of a row in the results list to preview it"""
        keymap = Gdk.Keymap.get_default()
        state = keymap.get_modifier_state()
        shift_pressed = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if shift_pressed:
            return  # Don't preview on multi-selection

        if row and hasattr(row, "result"):
            result = row.result
            plugin = services.plugin_manager.plugins.get(result.plugin_id)
            if plugin:
                try:
                    plugin.preview(result)
                except Exception as e:
                    logger.error(
                        f"Error previewing result for plugin {result.plugin_id}: {e}"
                    )

    def on_list_box_key_press(self, widget, event) -> bool:
        """Handle key presses on the list box to redirect typing to the entry."""
        keyval = event.keyval

        # For Tab, move focus back to the entry
        if keyval == Gdk.KEY_Tab:
            self.entry.grab_focus()
            return True  # Event handled

        # If at the top of the list, Up arrow focuses entry
        if keyval == Gdk.KEY_Up:
            selected_row = self.list_box.get_selected_row()
            if not selected_row or selected_row.get_index() == 0:
                self.entry.grab_focus()
                return True  # Event handled

        # For any printable character, focus the entry and let it handle the key press
        if Gdk.keyval_to_unicode(keyval) > 0:
            self.entry.grab_focus()
            # Returning False allows the key press to be processed by the newly focused entry
            return False

        # For other navigation keys (Down, etc.), let the default handler work
        return False

    def execute_result(self, result: SearchResult, event=None) -> None:
        """Execute the given search result"""
        if not self._validate_managers():
            return

        self._capture_modifier_state(result, event)

        plugin = services.plugin_manager.plugins.get(result.plugin_id)
        if services.plugin_manager.execute(result):
            result_to_track = result
            if result.plugin_id == "history":
                original_result_dict = result.metadata.get("original_result")
                if original_result_dict:
                    result_to_track = SearchResult.from_dict(original_result_dict)

            if plugin.track_history:
                services.history_manager.add_history(result_to_track)

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

    def show_and_focus(self):
        """Show window and grab focus"""
        self.show_all()
        self.present()
        GLib.timeout_add(self._search_delay_ms, self._select_and_focus)

    def _select_and_focus(self):
        """Select text and grab focus after widget is ready"""
        self.entry.grab_focus()
        self.entry.select_region(0, -1)
        return False  # Remove from idle queue

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

        if keyval == Gdk.KEY_q and state & Gdk.ModifierType.CONTROL_MASK:
            logger.info("Ctrl+Q pressed, quitting via launcher window")
            self.shutdown("Ctrl+Q")
            return True

        if keyval == Gdk.KEY_Escape:
            self.close_window()
            return True

        if keyval not in self._nav_keys and not self.is_active():
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

    def _ensure_row_visible(self, row):
        """Ensure the given row is visible in the scrolled window"""
        if row:
            self.scrolled.get_vadjustment().clamp_page(
                row.get_allocation().y,
                row.get_allocation().y + row.get_allocation().height,
            )

    def start(self):
        """Update the window with the full configuration after initialization"""

        # Store the signal handler ID for later connection/disconnection
        self.connect("delete-event", self.on_delete_event)
        self.entry_changed_handler_id = self.entry.connect(
            "changed", self.on_entry_changed
        )

        self._show_recent_history()
        self.entry.grab_focus()
