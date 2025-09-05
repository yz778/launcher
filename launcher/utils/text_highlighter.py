from gi.repository import Gtk, GLib
from typing import List
import re


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
        segments.extend(self._exact_match(text, query))
        if not segments:
            segments.extend(self._prefix_match(text, query))
        if not segments:
            segments.extend(self._word_boundary_match(text, query))
        if not segments:
            segments.extend(self._fuzzy_match(text, query))

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

        segments = []
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
                segments.append(HighlightSegment(text_idx, text_idx + 1, "fuzzy"))
                query_idx += 1
            text_idx += 1

        if query_idx == len(query_lower):
            return segments
        return []

    def _merge_segments(
        self, segments: List[HighlightSegment]
    ) -> List[HighlightSegment]:
        """Merge overlapping or adjacent segments"""
        if not segments:
            return []

        segments.sort(key=lambda s: s.start)
        merged = [segments[0]]
        for current in segments[1:]:
            last = merged[-1]

            if current.start <= last.end:
                merged[-1] = HighlightSegment(
                    last.start,
                    max(last.end, current.end),
                    last.match_type,
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
            if segment.start > last_end:
                before_text = text[last_end : segment.start]
                markup_parts.append(GLib.markup_escape_text(before_text))

            highlight_text = text[segment.start : segment.end]
            escaped_text = GLib.markup_escape_text(highlight_text)

            css_class = self._get_css_class(segment.match_type)
            style_attrs = self._get_style_from_css(widget, css_class)
            markup_parts.append(f"<span {style_attrs}>{escaped_text}</span>")

            last_end = segment.end

        if last_end < len(text):
            remaining_text = text[last_end:]
            markup_parts.append(GLib.markup_escape_text(remaining_text))

        return "".join(markup_parts)

    def _get_style_from_css(self, widget: Gtk.Widget, css_class: str) -> str:
        """Extract style attributes from CSS for the given class"""
        try:
            temp_widget = Gtk.Label()
            style_context = temp_widget.get_style_context()
            style_context.add_class(css_class)

            color = style_context.get_color(Gtk.StateFlags.NORMAL)
            color_hex = f"#{int(color.red * 255):02x}{int(color.green * 255):02x}{int(color.blue * 255):02x}"

            font_desc = style_context.get_font(Gtk.StateFlags.NORMAL)
            weight = "normal"
            style = "normal"
            if font_desc.get_weight() >= 700:
                weight = "bold"
            if font_desc.get_style() != 0:
                style = "italic"

            attrs = [f'foreground="{color_hex}"']
            if weight != "normal":
                attrs.append(f'weight="{weight}"')
            if style != "normal":
                attrs.append(f'style="{style}"')

            return " ".join(attrs)

        except Exception:
            return 'foreground="#8be9fd" weight="bold"'
