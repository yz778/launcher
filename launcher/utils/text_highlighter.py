from gi.repository import GLib

from launcher import services


class TextHighlighter:
    """Simple text highlighter that works with provided character indices"""

    def build_markup_from_indices(self, text: str, indices) -> str:
        """Build Pango markup from exact character indices using config colors"""
        if not indices or not text:
            return GLib.markup_escape_text(text)

        # Get highlight styling from the CSS manager
        highlight_color, highlight_weight = (
            services.instance.css_manager.get_highlight_style()
        )

        # Create a list to track which characters should be highlighted
        highlighted = [False] * len(text)
        for idx in indices:
            if 0 <= idx < len(text):
                highlighted[idx] = True

        # Build the markup string with config-based styling
        markup_parts = []
        i = 0
        while i < len(text):
            if highlighted[i]:
                # Start highlight span with config styling
                markup_parts.append(
                    f'<span foreground="{highlight_color}" weight="{highlight_weight}">'
                )
                # Add highlighted characters
                while i < len(text) and highlighted[i]:
                    markup_parts.append(GLib.markup_escape_text(text[i]))
                    i += 1
                markup_parts.append("</span>")
            else:
                # Add non-highlighted characters
                start = i
                while i < len(text) and not highlighted[i]:
                    i += 1
                markup_parts.append(GLib.markup_escape_text(text[start:i]))

        return "".join(markup_parts)
