#!/usr/bin/env python3

import unittest
from unittest.mock import Mock, patch, MagicMock
import time
import logging

# Set up logging for tests
logging.basicConfig(level=logging.DEBUG)

from launcher.plugins.history.plugin import HistoryPlugin
from launcher.plugins.base import SearchResult


class TestHistoryPluginMetadata(unittest.TestCase):
    """Test history plugin metadata handling"""

    def setUp(self):
        """Set up test fixtures"""
        self.plugin = HistoryPlugin()
        self.plugin.config = {
            "enabled": True,
            "max_results": 10,
            "min_query_length": 2,
            "boost_recent": True,
            "boost_frequent": True,
            "icon_size": 48,
        }

        # Mock history manager
        self.mock_history_manager = Mock()
        self.plugin.history_manager = self.mock_history_manager

        # Mock plugin manager
        self.mock_plugin_manager = Mock()
        self.plugin.plugin_manager = self.mock_plugin_manager

    def create_history_entry(self, user_input="test", plugin_id="test_plugin",
                           item_id="test_item", description="Test Description",
                           usage_count=1, timestamp=None):
        """Helper to create history entry"""
        if timestamp is None:
            timestamp = time.time()

        return {
            "user_input": user_input,
            "executed_command": user_input,
            "description": description,
            "plugin_id": plugin_id,
            "item_id": item_id,
            "usage_count": usage_count,
            "timestamp": timestamp,
        }

    def test_create_history_result_with_valid_metadata(self):
        """Test creating history result with valid original plugin metadata"""
        entry = self.create_history_entry(
            user_input="firefox",
            plugin_id="desktop_file",
            item_id="firefox.desktop",
            description="Firefox Web Browser"
        )

        with patch.object(self.plugin, '_get_history_icon', return_value=None):
            result = self.plugin._create_history_result(entry, 100.0, "firefox")

        self.assertIsNotNone(result)
        self.assertEqual(result.plugin_id, "history")
        self.assertEqual(result.name, "firefox")
        self.assertEqual(result.description, "Firefox Web Browser")
        self.assertEqual(result.score, 100.0)

        # Check metadata
        metadata = result.metadata
        self.assertEqual(metadata["original_plugin_id"], "desktop_file")
        self.assertEqual(metadata["original_item_id"], "firefox.desktop")
        self.assertEqual(metadata["usage_count"], 1)
        self.assertTrue(metadata["has_original_metadata"])
        self.assertFalse(metadata["track_history"])
        self.assertEqual(metadata["history_entry"], entry)

    def test_create_history_result_with_missing_plugin_id(self):
        """Test creating history result when plugin_id is missing"""
        entry = self.create_history_entry(
            user_input="firefox",
            plugin_id="",  # Empty plugin_id
            item_id="firefox.desktop",
            description="Firefox Web Browser"
        )

        with patch.object(self.plugin, '_get_history_icon', return_value=None):
            result = self.plugin._create_history_result(entry, 100.0, "firefox")

        self.assertIsNotNone(result)

        # Check metadata handling for missing plugin_id
        metadata = result.metadata
        self.assertEqual(metadata["original_plugin_id"], "")
        self.assertEqual(metadata["original_item_id"], "firefox.desktop")
        self.assertFalse(metadata["has_original_metadata"])  # Should be False due to missing plugin_id

    def test_create_history_result_with_missing_item_id(self):
        """Test creating history result when item_id is missing"""
        entry = self.create_history_entry(
            user_input="firefox",
            plugin_id="desktop_file",
            item_id="",  # Empty item_id
            description="Firefox Web Browser"
        )

        with patch.object(self.plugin, '_get_history_icon', return_value=None):
            result = self.plugin._create_history_result(entry, 100.0, "firefox")

        self.assertIsNotNone(result)

        # Check metadata handling for missing item_id
        metadata = result.metadata
        self.assertEqual(metadata["original_plugin_id"], "desktop_file")
        self.assertEqual(metadata["original_item_id"], "")
        self.assertFalse(metadata["has_original_metadata"])  # Should be False due to missing item_id

    def test_create_history_result_with_no_metadata(self):
        """Test creating history result when both plugin_id and item_id are missing"""
        entry = {
            "user_input": "firefox",
            "executed_command": "firefox",
            "description": "Firefox Web Browser",
            "usage_count": 1,
            "timestamp": time.time(),
            # No plugin_id or item_id
        }

        with patch.object(self.plugin, '_get_history_icon', return_value=None):
            result = self.plugin._create_history_result(entry, 100.0, "firefox")

        self.assertIsNotNone(result)

        # Check metadata handling for completely missing metadata
        metadata = result.metadata
        self.assertEqual(metadata["original_plugin_id"], "")
        self.assertEqual(metadata["original_item_id"], "")
        self.assertFalse(metadata["has_original_metadata"])

    def test_validate_original_plugin_id_with_valid_string(self):
        """Test plugin_id validation with valid string"""
        entry = {"plugin_id": "desktop_file"}
        result = self.plugin._validate_original_plugin_id(entry)
        self.assertEqual(result, "desktop_file")

    def test_validate_original_plugin_id_with_whitespace(self):
        """Test plugin_id validation with whitespace"""
        entry = {"plugin_id": "  desktop_file  "}
        result = self.plugin._validate_original_plugin_id(entry)
        self.assertEqual(result, "desktop_file")

    def test_validate_original_plugin_id_with_empty_string(self):
        """Test plugin_id validation with empty string"""
        entry = {"plugin_id": ""}
        result = self.plugin._validate_original_plugin_id(entry)
        self.assertEqual(result, "")

    def test_validate_original_plugin_id_with_none(self):
        """Test plugin_id validation with None value"""
        entry = {"plugin_id": None}
        result = self.plugin._validate_original_plugin_id(entry)
        self.assertEqual(result, "")

    def test_validate_original_plugin_id_with_invalid_type(self):
        """Test plugin_id validation with invalid type"""
        entry = {"plugin_id": 123}
        result = self.plugin._validate_original_plugin_id(entry)
        self.assertEqual(result, "")

    def test_validate_original_plugin_id_missing_key(self):
        """Test plugin_id validation when key is missing"""
        entry = {}
        result = self.plugin._validate_original_plugin_id(entry)
        self.assertEqual(result, "")

    def test_validate_original_item_id_with_valid_string(self):
        """Test item_id validation with valid string"""
        entry = {"item_id": "firefox.desktop"}
        result = self.plugin._validate_original_item_id(entry)
        self.assertEqual(result, "firefox.desktop")

    def test_validate_original_item_id_with_whitespace(self):
        """Test item_id validation with whitespace"""
        entry = {"item_id": "  firefox.desktop  "}
        result = self.plugin._validate_original_item_id(entry)
        self.assertEqual(result, "firefox.desktop")

    def test_validate_original_item_id_with_empty_string(self):
        """Test item_id validation with empty string"""
        entry = {"item_id": ""}
        result = self.plugin._validate_original_item_id(entry)
        self.assertEqual(result, "")

    def test_validate_original_item_id_with_none(self):
        """Test item_id validation with None value"""
        entry = {"item_id": None}
        result = self.plugin._validate_original_item_id(entry)
        self.assertEqual(result, "")

    def test_validate_original_item_id_with_invalid_type(self):
        """Test item_id validation with invalid type"""
        entry = {"item_id": ["not", "a", "string"]}
        result = self.plugin._validate_original_item_id(entry)
        self.assertEqual(result, "")

    def test_validate_original_item_id_missing_key(self):
        """Test item_id validation when key is missing"""
        entry = {}
        result = self.plugin._validate_original_item_id(entry)
        self.assertEqual(result, "")

    def test_create_history_result_with_different_executed_command(self):
        """Test creating history result when executed_command differs from user_input"""
        entry = self.create_history_entry(
            user_input="ff",
            plugin_id="desktop_file",
            item_id="firefox.desktop",
            description="Firefox Web Browser"
        )
        entry["executed_command"] = "firefox"

        with patch.object(self.plugin, '_get_history_icon', return_value=None):
            result = self.plugin._create_history_result(entry, 100.0, "ff")

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "ff")  # Should use user_input as name
        # Should combine executed_command and description since they're different
        self.assertEqual(result.description, "firefox - Firefox Web Browser")

    def test_create_history_result_with_complex_description(self):
        """Test creating history result with complex description building"""
        entry = self.create_history_entry(
            user_input="ff",
            plugin_id="desktop_file",
            item_id="firefox.desktop",
            description="Firefox Web Browser"
        )
        entry["executed_command"] = "firefox --private-window"

        with patch.object(self.plugin, '_get_history_icon', return_value=None):
            result = self.plugin._create_history_result(entry, 100.0, "ff")

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "ff")
        # Should combine executed_command and description
        self.assertEqual(result.description, "firefox --private-window - Firefox Web Browser")

    def test_create_history_result_error_handling(self):
        """Test error handling in _create_history_result"""
        # Create an entry that will cause an exception
        entry = None

        result = self.plugin._create_history_result(entry, 100.0, "test")

        # Should return None on error
        self.assertIsNone(result)

    @patch('launcher.plugins.history.plugin.logger')
    def test_create_history_result_logs_missing_metadata(self, mock_logger):
        """Test that missing metadata is logged for debugging"""
        entry = self.create_history_entry(
            user_input="firefox",
            plugin_id="",  # Missing plugin_id
            item_id="firefox.desktop",
            description="Firefox Web Browser"
        )

        with patch.object(self.plugin, '_get_history_icon', return_value=None):
            result = self.plugin._create_history_result(entry, 100.0, "firefox")

        self.assertIsNotNone(result)

        # Should log debug message about missing metadata
        mock_logger.debug.assert_called()
        debug_calls = [call[0][0] for call in mock_logger.debug.call_args_list]
        self.assertTrue(any("missing original plugin metadata" in call for call in debug_calls))

    def test_create_history_result_preserves_usage_count(self):
        """Test that usage count is properly preserved in metadata"""
        entry = self.create_history_entry(
            user_input="firefox",
            plugin_id="desktop_file",
            item_id="firefox.desktop",
            usage_count=5
        )

        with patch.object(self.plugin, '_get_history_icon', return_value=None):
            result = self.plugin._create_history_result(entry, 100.0, "firefox")

        self.assertIsNotNone(result)
        self.assertEqual(result.metadata["usage_count"], 5)

    def test_create_history_result_generates_unique_item_id(self):
        """Test that history results get unique item IDs based on timestamp"""
        timestamp = 1234567890.0
        entry = self.create_history_entry(
            user_input="firefox",
            plugin_id="desktop_file",
            item_id="firefox.desktop",
            timestamp=timestamp
        )

        with patch.object(self.plugin, '_get_history_icon', return_value=None):
            result = self.plugin._create_history_result(entry, 100.0, "firefox")

        self.assertIsNotNone(result)
        self.assertEqual(result.item_id, f"history_{timestamp}")


if __name__ == '__main__':
    unittest.main()