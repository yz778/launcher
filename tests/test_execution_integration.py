#!/usr/bin/env python3

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add the launcher directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from launcher.plugins.base import SearchResult


class TestExecutionIntegration(unittest.TestCase):
    """Integration tests for visual styling and deduplication working together"""

    def setUp(self):
        """Set up test fixtures"""
        pass

    def test_deduplication_preserves_score_ordering(self):
        """Test that score-based ordering is maintained after deduplication"""
        # Create mock results with different scores
        results = [
            SearchResult(
                plugin_id="desktop_file",
                item_id="firefox.desktop",
                name="Firefox",
                description="Web Browser",
                icon=None,
                score=95.0,
            ),
            SearchResult(
                plugin_id="history",
                item_id="hist_1",
                name="Firefox",
                description="Web Browser",
                icon=None,
                score=90.0,  # Lower score than current result
                metadata={
                    "original_plugin_id": "desktop_file",
                    "original_item_id": "firefox.desktop",
                    "usage_count": 3,
                },
            ),
            SearchResult(
                plugin_id="executable",
                item_id="/usr/bin/vim",
                name="Vim",
                description="Text Editor",
                icon=None,
                score=85.0,
            ),
            SearchResult(
                plugin_id="history",
                item_id="hist_2",
                name="Old App",
                description="No longer available",
                icon=None,
                score=80.0,  # Should be preserved
                metadata={
                    "original_plugin_id": "desktop_file",
                    "original_item_id": "old_app.desktop",
                    "usage_count": 1,
                },
            ),
        ]

        # Mock the deduplication process
        from tests.test_deduplication import MockLauncherWindow

        launcher = MockLauncherWindow()
        launcher.current_results = results.copy()

        # Apply deduplication
        launcher._deduplicate_results()

        # Check that results are properly ordered by score after deduplication
        final_results = launcher.current_results
        self.assertEqual(len(final_results), 3)  # Firefox history should be removed

        # Verify ordering: Firefox (95.0), Vim (85.0), Old App (80.0)
        self.assertEqual(final_results[0].name, "Firefox")
        self.assertEqual(final_results[0].score, 95.0)
        self.assertEqual(final_results[0].plugin_id, "desktop_file")

        self.assertEqual(final_results[1].name, "Vim")
        self.assertEqual(final_results[1].score, 85.0)

        self.assertEqual(final_results[2].name, "Old App")
        self.assertEqual(final_results[2].score, 80.0)
        self.assertEqual(final_results[2].plugin_id, "history")

    def test_deduplication_preserves_metadata(self):
        """Test that all result metadata is preserved during deduplication"""
        original_metadata = {
            "original_plugin_id": "desktop_file",
            "original_item_id": "old_app.desktop",
            "usage_count": 5,
            "custom_field": "test_value",
            "nested_data": {"key": "value"},
        }

        results = [
            SearchResult(
                plugin_id="desktop_file",
                item_id="firefox.desktop",
                name="Firefox",
                description="Web Browser",
                icon=None,
                score=95.0,
                metadata={"some_field": "some_value"},
            ),
            SearchResult(
                plugin_id="history",
                item_id="hist_1",
                name="Old App",
                description="Historical app",
                icon=None,
                score=80.0,
                metadata=original_metadata.copy(),
            ),
        ]

        from tests.test_deduplication import MockLauncherWindow

        launcher = MockLauncherWindow()
        launcher.current_results = results.copy()

        # Apply deduplication
        launcher._deduplicate_results()

        # Check that metadata is preserved
        final_results = launcher.current_results
        self.assertEqual(len(final_results), 2)  # Both should be preserved (no match)

        # Find the history result
        history_result = next(r for r in final_results if r.plugin_id == "history")

        # Verify all metadata is preserved
        self.assertEqual(history_result.metadata["original_plugin_id"], "desktop_file")
        self.assertEqual(history_result.metadata["original_item_id"], "old_app.desktop")
        self.assertEqual(history_result.metadata["usage_count"], 5)
        self.assertEqual(history_result.metadata["custom_field"], "test_value")
        self.assertEqual(history_result.metadata["nested_data"]["key"], "value")

    def test_deduplication_preserves_display_properties(self):
        """Test that display properties (name, description, icon) are preserved"""
        mock_icon = Mock()

        results = [
            SearchResult(
                plugin_id="desktop_file",
                item_id="firefox.desktop",
                name="Firefox Browser",
                description="Mozilla Firefox Web Browser",
                icon=mock_icon,
                score=95.0,
            ),
            SearchResult(
                plugin_id="history",
                item_id="hist_1",
                name="Old Firefox",
                description="Previous Firefox installation",
                icon=mock_icon,
                score=80.0,
                metadata={
                    "original_plugin_id": "desktop_file",
                    "original_item_id": "old_firefox.desktop",
                    "usage_count": 2,
                },
            ),
        ]

        from tests.test_deduplication import MockLauncherWindow

        launcher = MockLauncherWindow()
        launcher.current_results = results.copy()

        # Apply deduplication
        launcher._deduplicate_results()

        # Check that display properties are preserved
        final_results = launcher.current_results
        self.assertEqual(len(final_results), 2)  # Both preserved (different item_ids)

        # Verify display properties
        firefox_result = next(r for r in final_results if r.name == "Firefox Browser")
        self.assertEqual(firefox_result.description, "Mozilla Firefox Web Browser")
        self.assertEqual(firefox_result.icon, mock_icon)

        history_result = next(r for r in final_results if r.name == "Old Firefox")
        self.assertEqual(history_result.description, "Previous Firefox installation")
        self.assertEqual(history_result.icon, mock_icon)

    def test_visual_styling_integration_with_deduplication(self):
        """Test that visual styling works correctly with deduplicated results"""
        # This test verifies the integration between deduplication and styling

        # Create results that will go through deduplication
        results = [
            SearchResult(
                plugin_id="desktop_file",
                item_id="firefox.desktop",
                name="Firefox",
                description="Web Browser",
                icon=None,
                score=95.0,
            ),
            SearchResult(
                plugin_id="history",
                item_id="hist_1",
                name="Firefox",
                description="Web Browser",
                icon=None,
                score=90.0,
                metadata={
                    "original_plugin_id": "desktop_file",
                    "original_item_id": "firefox.desktop",
                    "usage_count": 3,
                },
            ),
            SearchResult(
                plugin_id="history",
                item_id="hist_2",
                name="Old App",
                description="Historical app",
                icon=None,
                score=80.0,
                metadata={
                    "original_plugin_id": "desktop_file",
                    "original_item_id": "old_app.desktop",
                    "usage_count": 1,
                },
            ),
        ]

        # Mock the launcher window's styling logic
        class MockLauncherWithStyling:
            def __init__(self):
                self.current_results = []
                self.styled_items = []

            def _deduplicate_results(self):
                """Apply the same deduplication logic"""
                if not self.current_results:
                    return

                history_results = [
                    r for r in self.current_results if r.plugin_id == "history"
                ]
                other_results = [
                    r for r in self.current_results if r.plugin_id != "history"
                ]

                if not history_results or not other_results:
                    return

                other_result_keys = {}
                for result in other_results:
                    key = (result.plugin_id, result.item_id)
                    other_result_keys[key] = result

                filtered_history_results = []
                for history_result in history_results:
                    if not hasattr(history_result, "metadata") or not isinstance(
                        history_result.metadata, dict
                    ):
                        filtered_history_results.append(history_result)
                        continue

                    original_plugin_id = history_result.metadata.get(
                        "original_plugin_id"
                    )
                    original_item_id = history_result.metadata.get("original_item_id")

                    if not original_plugin_id or not original_item_id:
                        filtered_history_results.append(history_result)
                        continue

                    match_key = (original_plugin_id, original_item_id)
                    if match_key not in other_result_keys:
                        filtered_history_results.append(history_result)

                self.current_results = other_results + filtered_history_results

            def _apply_styling(self):
                """Apply styling logic similar to the real implementation"""
                self.styled_items = []
                for result in self.current_results:
                    styled_item = {
                        "result": result,
                        "name": "history-search-result"
                        if result.plugin_id == "history"
                        else "app-list-item",
                        "css_classes": ["history-result"]
                        if result.plugin_id == "history"
                        else [f"{result.plugin_id}-result"],
                    }
                    self.styled_items.append(styled_item)

        launcher = MockLauncherWithStyling()
        launcher.current_results = results.copy()

        # Apply deduplication first
        launcher._deduplicate_results()

        # Then apply styling
        launcher._apply_styling()

        # Verify results after deduplication
        self.assertEqual(
            len(launcher.current_results), 2
        )  # Firefox history should be removed

        # Verify styling is applied correctly
        self.assertEqual(len(launcher.styled_items), 2)

        # Check that the remaining history item gets proper styling
        history_styled_item = next(
            item
            for item in launcher.styled_items
            if item["result"].plugin_id == "history"
        )
        self.assertEqual(history_styled_item["name"], "history-search-result")
        self.assertIn("history-result", history_styled_item["css_classes"])
        self.assertEqual(history_styled_item["result"].name, "Old App")

        # Check that the regular item gets normal styling
        regular_styled_item = next(
            item
            for item in launcher.styled_items
            if item["result"].plugin_id == "desktop_file"
        )
        self.assertEqual(regular_styled_item["name"], "app-list-item")
        self.assertIn("desktop_file-result", regular_styled_item["css_classes"])
        self.assertEqual(regular_styled_item["result"].name, "Firefox")

    def test_score_ordering_after_deduplication_complex(self):
        """Test complex score ordering scenario after deduplication"""
        results = [
            # High score current result
            SearchResult(
                plugin_id="desktop_file",
                item_id="app1.desktop",
                name="App 1",
                score=100.0,
            ),
            # History result that should be removed (matches app1)
            SearchResult(
                plugin_id="history",
                item_id="hist_1",
                name="App 1",
                score=95.0,
                metadata={
                    "original_plugin_id": "desktop_file",
                    "original_item_id": "app1.desktop",
                },
            ),
            # Medium score current result
            SearchResult(
                plugin_id="executable",
                item_id="/usr/bin/app2",
                name="App 2",
                score=85.0,
            ),
            # History result that should be preserved (no current match)
            SearchResult(
                plugin_id="history",
                item_id="hist_2",
                name="Old App",
                score=90.0,
                metadata={
                    "original_plugin_id": "desktop_file",
                    "original_item_id": "old_app.desktop",
                },
            ),
            # Low score current result
            SearchResult(
                plugin_id="calculator", item_id="calc1", name="Calculator", score=70.0
            ),
            # Another history result that should be preserved
            SearchResult(
                plugin_id="history",
                item_id="hist_3",
                name="Another Old App",
                score=75.0,
                metadata={
                    "original_plugin_id": "desktop_file",
                    "original_item_id": "another_old.desktop",
                },
            ),
        ]

        from tests.test_deduplication import MockLauncherWindow

        launcher = MockLauncherWindow()
        launcher.current_results = results.copy()

        # Apply deduplication
        launcher._deduplicate_results()

        # Sort by score (this happens in the real implementation)
        launcher.current_results.sort(key=lambda r: r.score, reverse=True)

        # Verify final ordering by score
        final_results = launcher.current_results
        self.assertEqual(len(final_results), 5)  # One history result removed

        # Expected order: App 1 (100), Old App (90), App 2 (85), Another Old App (75), Calculator (70)
        expected_order = [
            ("App 1", 100.0, "desktop_file"),
            ("Old App", 90.0, "history"),
            ("App 2", 85.0, "executable"),
            ("Another Old App", 75.0, "history"),
            ("Calculator", 70.0, "calculator"),
        ]

        for i, (expected_name, expected_score, expected_plugin) in enumerate(
            expected_order
        ):
            self.assertEqual(final_results[i].name, expected_name)
            self.assertEqual(final_results[i].score, expected_score)
            self.assertEqual(final_results[i].plugin_id, expected_plugin)


if __name__ == "__main__":
    unittest.main()
