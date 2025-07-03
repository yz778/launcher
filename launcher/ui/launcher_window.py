#!/usr/bin/env python3

import logging
from typing import Dict, Any, List

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GLib

from plugins.base import SearchResult
from core.plugin_manager import PluginManager
from core.history_manager import HistoryManager
from ui.css_manager import CssManager

logger = logging.getLogger(__name__)


class HighlightSegment:
    """Represents a segment of text to be highlighted"""

    def __init__(self, start: int, end: int, match_type: str = "exact"):
        self.start = start
        self.end = end
        self.match_type = match_type  # "exact", "fuzzy", "prefix", "word", etc.

    def __repr__(self):
        return f"HighlightSegment({self.start}, {self.end}, {self.match_type})"


class TextHighlighter:
    """Flexible text highlighter that supports multiple matching strategies"""

    def __init__(self):
        pass

    def get_highlight_segments(self, text: str, query: str) -> List[HighlightSegment]:
        """
        Get highlight segments for the given text and query.
        Returns a list of HighlightSegment objects representing parts to highlight.
        """
        if not text or not query:
            return []

        segments = []

        # Try different matching strategies in order of preference
        segments.extend(self._exact_match(text, query))
        if not segments:
            segments.extend(self._prefix_match(text, query))
        if not segments:
            segments.extend(self._word_boundary_match(text, query))
        if not segments:
            segments.extend(self._fuzzy_match(text, query))

        # Merge overlapping segments and sort by position
        return self._merge_segments(segments)

    def _exact_match(self, text: str, query: str) -> List[HighlightSegment]:
        """Find exact substring matches (case-insensitive)"""
        segments = []
        text_lower = text.lower()
        query_lower = query.lower()

        start = 0
        while True:
            pos = text_lower.find(query_lower, start)
            if pos == -1:
                break
            segments.append(HighlightSegment(pos, pos + len(query), "exact"))
            start = pos + 1

        return segments

    def _prefix_match(self, text: str, query: str) -> List[HighlightSegment]:
        """Find prefix matches"""
        text_lower = text.lower()
        query_lower = query.lower()

        if text_lower.startswith(query_lower):
            return [HighlightSegment(0, len(query), "prefix")]
        return []

    def _word_boundary_match(self, text: str, query: str) -> List[HighlightSegment]:
        """Find matches at word boundaries"""
        import re

        segments = []

        # Create pattern for word boundary matching
        pattern = r"\b" + re.escape(query.lower())

        for match in re.finditer(pattern, text.lower()):
            segments.append(HighlightSegment(match.start(), match.end(), "word"))

        return segments

    def _fuzzy_match(self, text: str, query: str) -> List[HighlightSegment]:
        """
        Find fuzzy matches - individual characters that match in sequence.
        This is useful for fuzzy search where 'calc' might match 'Calculator'
        by highlighting 'C', 'a', 'l', 'c'.
        """
        segments = []
        text_lower = text.lower()
        query_lower = query.lower()

        text_idx = 0
        query_idx = 0

        while text_idx < len(text_lower) and query_idx < len(query_lower):
            if text_lower[text_idx] == query_lower[query_idx]:
                # Found a matching character
                segments.append(HighlightSegment(text_idx, text_idx + 1, "fuzzy"))
                query_idx += 1
            text_idx += 1

        # Only return segments if we matched the entire query
        if query_idx == len(query_lower):
            return segments
        return []

    def _merge_segments(
        self, segments: List[HighlightSegment]
    ) -> List[HighlightSegment]:
        """Merge overlapping or adjacent segments"""
        if not segments:
            return []

        # Sort by start position
        segments.sort(key=lambda s: s.start)

        merged = [segments[0]]

        for current in segments[1:]:
            last = merged[-1]

            # If segments overlap or are adjacent, merge them
            if current.start <= last.end:
                # Extend the last segment to include the current one
                merged[-1] = HighlightSegment(
                    last.start,
                    max(last.end, current.end),
                    last.match_type,  # Keep the type of the first segment
                )
            else:
                merged.append(current)

        return merged

    def _get_css_class(self, match_type: str) -> str:
        """Get the CSS class name for a specific match type"""
        return f"highlight-{match_type}"

    def build_markup(
        self, text: str, segments: List[HighlightSegment], widget: Gtk.Widget
    ) -> str:
        """Build Pango markup string from text and highlight segments using CSS styles"""
        if not segments:
            return GLib.markup_escape_text(text)

        markup_parts = []
        last_end = 0

        for segment in segments:
            # Add text before this segment
            if segment.start > last_end:
                before_text = text[last_end : segment.start]
                markup_parts.append(GLib.markup_escape_text(before_text))

            # Add highlighted segment with CSS-based styling
            highlight_text = text[segment.start : segment.end]
            escaped_text = GLib.markup_escape_text(highlight_text)

            # Get CSS class for this match type
            css_class = self._get_css_class(segment.match_type)

            # Extract style from CSS using GTK style context
            style_attrs = self._get_style_from_css(widget, css_class)
            markup_parts.append(f"<span {style_attrs}>{escaped_text}</span>")

            last_end = segment.end

        # Add remaining text after last segment
        if last_end < len(text):
            remaining_text = text[last_end:]
            markup_parts.append(GLib.markup_escape_text(remaining_text))

        return "".join(markup_parts)

    def _get_style_from_css(self, widget: Gtk.Widget, css_class: str) -> str:
        """Extract style attributes from CSS for the given class"""
        try:
            # Create a temporary widget with the CSS class to extract styles
            temp_widget = Gtk.Label()
            style_context = temp_widget.get_style_context()
            style_context.add_class(css_class)

            # Get color
            color = style_context.get_color(Gtk.StateFlags.NORMAL)
            color_hex = f"#{int(color.red * 255):02x}{int(color.green * 255):02x}{int(color.blue * 255):02x}"

            # Get font weight and style
            font_desc = style_context.get_font(Gtk.StateFlags.NORMAL)
            weight = "normal"
            style = "normal"

            if font_desc.get_weight() >= 700:  # Pango.Weight.BOLD
                weight = "bold"

            if font_desc.get_style() != 0:  # Pango.Style.NORMAL
                style = "italic"

            # Build attribute string
            attrs = [f'foreground="{color_hex}"']
            if weight != "normal":
                attrs.append(f'weight="{weight}"')
            if style != "normal":
                attrs.append(f'style="{style}"')

            return " ".join(attrs)

        except Exception as e:
            logger.debug(f"Could not extract CSS styles for {css_class}: {e}")
            # Fallback to default highlighting
            return 'foreground="#8be9fd" weight="bold"'


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
        vbox.pack_start(desc_label, True, True, 0)

        hbox.pack_start(vbox, True, True, 0)
        self.add(hbox)

        if result.description:
            self.set_tooltip_text(result.description)

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
            # Get highlight segments from the highlighter
            highlighter = TextHighlighter()
            segments = highlighter.get_highlight_segments(text, query)

            if not segments:
                # No matches found, just set plain text
                label.set_text(text)
                return

            # Build markup from segments using CSS styles
            markup = highlighter.build_markup(text, segments, label)
            label.set_markup(markup)

        except Exception as e:
            logger.error(f"Error applying highlighting for '{text}': {e}")
            # Fallback to plain text if highlighting fails
            label.set_text(text)


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

        CssManager._load_css_from_string(CssManager.DEFAULT_CSS)

        self.plugin_manager = plugin_manager
        self.history_manager = history_manager
        self.config = config
        self.foreground_mode = foreground_mode
        # Cache general config to avoid repeated lookups
        general_config = config.get("general", {})
        self.icon_size = general_config.get("icon_size")
        self.window_width = general_config.get("window_width")
        self.window_height = general_config.get("window_height")
        self.window_height_results = general_config.get("window_height_results")

        self.saved_x = None
        self.saved_y = None

        self.set_decorated(False)
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
        """Show all history items when launcher opens with empty input, with scrolling support."""
        if not self.history_manager:
            return

        # Get all history items instead of just 5
        all_history = self.history_manager.get_recent_history(100)  # Get up to 100 items
        if not all_history:
            return

        # Clear previous items
        for child in self.list_box.get_children():
            child.destroy()

        # Create history result items
        for i, history_entry in enumerate(all_history):
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
                # Fallback to history icon
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
                query="",  # No highlighting for history items
            )
            list_item.set_name("history-item")
            list_item.user_input = user_input  # Store the input for selection
            list_item.history_entry = history_entry  # Store full history entry
            self.list_box.add(list_item)

        self.list_box.show_all()
        self.scrolled.show()
        self.showing_history = True

        # Use the same display logic as search results for consistency
        self._setup_results_display(all_history, f"{len(all_history)} history item{'s' if len(all_history) != 1 else ''}")

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
            self.list_box.add(list_item)

        self.list_box.show_all()
        self.scrolled.show()
        # Scroll to top when results change
        vadj = self.scrolled.get_vadjustment()
        if vadj:
            vadj.set_value(vadj.get_lower())

        # Use unified display setup
        count_text = f"{len(results_to_display)} result{'s' if len(results_to_display) != 1 else ''}" if results_to_display else ""
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
            logger.debug(
                f"Ignoring stale results from plugin {plugin_id} for search_id {search_id} (current is {self.active_search_id})"
            )
            return

        logger.debug(
            f"Received {len(plugin_results)} results from plugin {plugin_id} for search_id {search_id}"
        )

        # No need to handle highlighting here - UI layer will handle it based on current query

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

        # Sort by score only - history plugin already has prioritized scores
        self.current_results.sort(key=lambda r: r.score, reverse=True)

        # Truncate results - cache max_results to avoid repeated config lookups
        if not hasattr(self, '_cached_max_results'):
            self._cached_max_results = self.config.get("general", {}).get("max_results", 15)
        self.current_results = self.current_results[:self._cached_max_results]

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
        query_text = self.entry.get_text().strip()
        if query_text and not self.current_results:
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

        # Check for autocomplete matches - cache history manager check
        if self.history_manager:
            self.autocomplete_matches = self.history_manager.get_matching_history(query, 5)

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

            # Handle Shift+Delete to remove selected history entries (single or multiple)
            elif keyval == Gdk.KEY_Delete and state & Gdk.ModifierType.SHIFT_MASK:
                selected_rows = self.list_box.get_selected_rows()
                if selected_rows:
                    entries_to_remove = []
                    
                    for row in selected_rows:
                        # Check if this is a recent history item
                        if self.showing_history and hasattr(row, "history_entry"):
                            entries_to_remove.append(row.history_entry)
                        # Check if this is a history plugin search result
                        elif hasattr(row, "result") and row.result.plugin_id == "history":
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
                            
                            if self.showing_history:
                                self._refresh_history_view_after_delete()
                            else:
                                # Refresh the current search to update results
                                self.on_entry_changed(self.entry)
                        return True
                return (
                    False  # Allow other handlers if no selection
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
