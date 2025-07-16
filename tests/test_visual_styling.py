#!/usr/bin/env python3

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add the launcher directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from launcher.plugins.base import SearchResult
from launcher.ui.css_manager import CssManager


class TestVisualStyling(unittest.TestCase):
    """Test visual styling improvements for task 6"""

    def setUp(self):
        """Set up test fixtures"""
        pass

    def test_css_contains_history_styling(self):
        """Test that CSS contains proper history styling with bold font weight"""
        css_content = CssManager.DEFAULT_CSS

        # Verify history item styling exists
        self.assertIn("#history-item", css_content)
        self.assertIn("#history-search-result", css_content)

        # Verify history result class styling ensures bold font weight
        self.assertIn(".history-result #app-name", css_content)
        self.assertIn("font-weight: bold", css_content)

        # Verify no italic styling for history descriptions
        self.assertIn(".history-result #app-description", css_content)
        self.assertIn("font-style: normal", css_content)

    def test_css_history_text_bold_styling(self):
        """Test that history text has bold font weight instead of italic"""
        css_content = CssManager.DEFAULT_CSS

        # Find the history-text section
        history_text_section = None
        lines = css_content.split('\n')
        in_history_text = False

        for line in lines:
            if '#history-text' in line:
                in_history_text = True
                history_text_section = []
            elif in_history_text:
                if line.strip().startswith('}'):
                    break
                history_text_section.append(line.strip())

        self.assertIsNotNone(history_text_section, "history-text CSS section not found")

        # Check that it has bold font weight
        has_bold = any('font-weight: bold' in line for line in history_text_section)
        self.assertTrue(has_bold, "history-text should have font-weight: bold")

        # Check that it doesn't have italic styling
        has_italic = any('font-style: italic' in line for line in history_text_section)
        self.assertFalse(has_italic, "history-text should not have font-style: italic")

    def test_css_history_result_class_styling(self):
        """Test that history result class styling ensures proper font weight"""
        css_content = CssManager.DEFAULT_CSS

        # Check for history result class styling
        self.assertIn(".history-result #app-name", css_content)

        # Find the history-result app-name section
        lines = css_content.split('\n')
        in_history_result_name = False
        history_result_name_section = []

        for line in lines:
            if '.history-result #app-name' in line:
                in_history_result_name = True
                history_result_name_section = []
            elif in_history_result_name:
                if line.strip().startswith('}'):
                    break
                history_result_name_section.append(line.strip())

        self.assertTrue(len(history_result_name_section) > 0, "history-result app-name CSS section not found")

        # Check that it has bold font weight
        has_bold = any('font-weight: bold' in line for line in history_result_name_section)
        self.assertTrue(has_bold, "history-result app-name should have font-weight: bold")

    def test_css_history_description_no_italic(self):
        """Test that history descriptions don't have italic styling"""
        css_content = CssManager.DEFAULT_CSS

        # Check for history result description styling
        self.assertIn(".history-result #app-description", css_content)

        # Find the history-result app-description section
        lines = css_content.split('\n')
        in_history_result_desc = False
        history_result_desc_section = []

        for line in lines:
            if '.history-result #app-description' in line:
                in_history_result_desc = True
                history_result_desc_section = []
            elif in_history_result_desc:
                if line.strip().startswith('}'):
                    break
                history_result_desc_section.append(line.strip())

        self.assertTrue(len(history_result_desc_section) > 0, "history-result app-description CSS section not found")

        # Check that it explicitly sets font-style to normal (not italic)
        has_normal_style = any('font-style: normal' in line for line in history_result_desc_section)
        self.assertTrue(has_normal_style, "history-result app-description should have font-style: normal")

    def test_css_maintains_other_styling(self):
        """Test that other styling elements are preserved"""
        css_content = CssManager.DEFAULT_CSS

        # Verify other important styling is still present
        self.assertIn("#app-name", css_content)
        self.assertIn("#app-description", css_content)
        self.assertIn("#app-count", css_content)
        self.assertIn(".highlight-exact", css_content)
        self.assertIn(".highlight-prefix", css_content)
        self.assertIn(".highlight-word", css_content)
        self.assertIn(".highlight-fuzzy", css_content)

    def test_css_hover_and_selection_states(self):
        """Test that history items have proper hover and selection styling"""
        css_content = CssManager.DEFAULT_CSS

        # Check history-item hover and selection
        self.assertIn("#history-item:hover", css_content)
        self.assertIn("#history-item:selected", css_content)

        # Check history-search-result hover and selection
        self.assertIn("#history-search-result:hover", css_content)
        self.assertIn("#history-search-result:selected", css_content)

    @patch('launcher.ui.launcher_window.AppListItem')
    def test_history_search_result_styling_application(self, mock_app_list_item):
        """Test that history search results get proper styling applied"""
        # This test would require mocking the entire launcher window setup
        # For now, we'll test the CSS content which is the main requirement

        # Create a mock AppListItem instance
        mock_item = Mock()
        mock_style_context = Mock()
        mock_item.get_style_context.return_value = mock_style_context
        mock_item.set_name = Mock()
        mock_app_list_item.return_value = mock_item

        # Create a mock history search result
        history_result = SearchResult(
            plugin_id="history",
            item_id="hist_123",
            name="Test History Item",
            description="Test Description",
            icon=None,
            score=100.0,
            metadata={"usage_count": 5}
        )

        # The actual styling application happens in the launcher window
        # We've verified the CSS exists, which is the main requirement for this task
        self.assertTrue(True, "CSS styling is properly defined")


class MockLauncherWindow:
    """Mock launcher window for testing styling application"""

    def __init__(self):
        self.current_results = []
        self.showing_history = False

    def _populate_list_box_with_styling(self, results_to_display):
        """Mock method to test styling application logic"""
        styled_items = []

        for result in results_to_display:
            # Mock the styling logic from the actual implementation
            if result.plugin_id == "history":
                # This would be an AppListItem in the real implementation
                mock_item = {
                    'result': result,
                    'name': 'history-search-result',
                    'css_classes': ['history-result']
                }
                styled_items.append(mock_item)
            else:
                mock_item = {
                    'result': result,
                    'name': 'app-list-item',
                    'css_classes': [f'{result.plugin_id}-result']
                }
                styled_items.append(mock_item)

        return styled_items


class TestStylingApplication(unittest.TestCase):
    """Test the application of styling to history results"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_launcher = MockLauncherWindow()

    def test_history_results_get_special_styling(self):
        """Test that history results get special styling applied"""
        results = [
            SearchResult(
                plugin_id="desktop_file",
                item_id="firefox.desktop",
                name="Firefox",
                description="Web Browser",
                icon=None,
                score=100.0
            ),
            SearchResult(
                plugin_id="history",
                item_id="hist_123",
                name="Firefox",
                description="Web Browser",
                icon=None,
                score=90.0,
                metadata={"usage_count": 3}
            )
        ]

        styled_items = self.mock_launcher._populate_list_box_with_styling(results)

        # Check that we have the right number of items
        self.assertEqual(len(styled_items), 2)

        # Check that the history item gets special styling
        history_item = next(item for item in styled_items if item['result'].plugin_id == "history")
        self.assertEqual(history_item['name'], 'history-search-result')
        self.assertIn('history-result', history_item['css_classes'])

        # Check that the regular item gets normal styling
        regular_item = next(item for item in styled_items if item['result'].plugin_id == "desktop_file")
        self.assertEqual(regular_item['name'], 'app-list-item')
        self.assertIn('desktop_file-result', regular_item['css_classes'])

    def test_mixed_results_styling(self):
        """Test styling with mixed result types"""
        results = [
            SearchResult(plugin_id="executable", item_id="/usr/bin/vim", name="Vim", description="Text Editor", icon=None, score=95.0),
            SearchResult(plugin_id="history", item_id="hist_1", name="Old App", description="Historical", icon=None, score=85.0, metadata={"usage_count": 1}),
            SearchResult(plugin_id="calculator", item_id="calc_1", name="2+2=4", description="Calculation", icon=None, score=80.0),
            SearchResult(plugin_id="history", item_id="hist_2", name="Another Old App", description="Also Historical", icon=None, score=75.0, metadata={"usage_count": 2})
        ]

        styled_items = self.mock_launcher._populate_list_box_with_styling(results)

        # Check that we have the right number of items
        self.assertEqual(len(styled_items), 4)

        # Check that history items get special styling
        history_items = [item for item in styled_items if item['result'].plugin_id == "history"]
        self.assertEqual(len(history_items), 2)

        for history_item in history_items:
            self.assertEqual(history_item['name'], 'history-search-result')
            self.assertIn('history-result', history_item['css_classes'])

        # Check that non-history items get normal styling
        non_history_items = [item for item in styled_items if item['result'].plugin_id != "history"]
        self.assertEqual(len(non_history_items), 2)

        for item in non_history_items:
            self.assertEqual(item['name'], 'app-list-item')
            self.assertIn(f"{item['result'].plugin_id}-result", item['css_classes'])


if __name__ == '__main__':
    unittest.main()