#!/usr/bin/env python3

import unittest
from unittest.mock import Mock, patch, MagicMock
import logging
import sys
import os
import tempfile
import json
import time

# Add the launcher directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from launcher.core.history_manager import HistoryManager
from launcher.plugins.base import SearchResult
from launcher.utils.result_analyzer import ResultAnalyzer


class TestHistoryStorage(unittest.TestCase):
    """Test cases for smart history storage logic"""

    def setUp(self):
        """Set up test fixtures"""
        # Create temporary history file
        self.temp_dir = tempfile.mkdtemp()
        self.history_file = os.path.join(self.temp_dir, "test_history.json")

        # Create HistoryManager with test config
        config = {"general": {"history_file": self.history_file}}
        self.history_manager = HistoryManager(config)

        # Set up logging to capture debug messages
        self.log_messages = []
        self.log_handler = logging.Handler()
        self.log_handler.emit = lambda record: self.log_messages.append(
            record.getMessage()
        )

        logger = logging.getLogger("launcher.core.history_manager")
        logger.addHandler(self.log_handler)
        logger.setLevel(logging.DEBUG)

    def tearDown(self):
        """Clean up after tests"""
        # Remove log handler
        logger = logging.getLogger("launcher.core.history_manager")
        logger.removeHandler(self.log_handler)

        # Clean up temp files
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_search_result(self, plugin_id, item_id, name, description="", score=1.0):
        """Helper to create SearchResult objects"""
        return SearchResult(
            plugin_id=plugin_id,
            item_id=item_id,
            name=name,
            description=description,
            icon=None,
            score=score,
        )

    def test_should_store_exact_match(self):
        """Test that exact matches are always stored"""
        user_input = "firefox"
        executed_result = self.create_search_result(
            "desktop_file", "firefox.desktop", "firefox"
        )
        search_results = [executed_result]

        should_store = self.history_manager.should_store_in_history(
            user_input, search_results, executed_result
        )

        self.assertTrue(should_store)
        self.assertTrue(
            any("Storing exact match in history" in msg for msg in self.log_messages)
        )

    def test_should_store_partial_match_with_arguments(self):
        """Test that partial matches with command arguments are stored"""
        user_input = "firefox --private-window"
        executed_result = self.create_search_result(
            "desktop_file", "firefox.desktop", "firefox"
        )
        search_results = [executed_result]

        should_store = self.history_manager.should_store_in_history(
            user_input, search_results, executed_result
        )

        self.assertTrue(should_store)
        self.assertTrue(
            any(
                "Storing partial match with command arguments" in msg
                for msg in self.log_messages
            )
        )

    def test_should_not_store_partial_match_without_arguments(self):
        """Test that partial matches without command arguments are not stored"""
        user_input = "fire"  # Partial match for "firefox"
        executed_result = self.create_search_result(
            "desktop_file", "firefox.desktop", "firefox"
        )
        search_results = [executed_result]

        should_store = self.history_manager.should_store_in_history(
            user_input, search_results, executed_result
        )

        self.assertFalse(should_store)
        self.assertTrue(
            any(
                "Skipping storage of partial match without command arguments" in msg
                for msg in self.log_messages
            )
        )

    def test_should_store_fuzzy_match(self):
        """Test that fuzzy matches are stored"""
        user_input = "fire"
        executed_result = self.create_search_result(
            "desktop_file", "firefox.desktop", "Firefox Browser", score=0.8
        )
        search_results = [executed_result]

        # Mock the get_match_quality to return "fuzzy"
        with patch.object(ResultAnalyzer, "get_match_quality", return_value="fuzzy"):
            should_store = self.history_manager.should_store_in_history(
                user_input, search_results, executed_result
            )

        self.assertTrue(should_store)
        self.assertTrue(
            any("Storing fuzzy match in history" in msg for msg in self.log_messages)
        )

    def test_should_store_fallback_on_missing_input(self):
        """Test fallback behavior when user input is missing"""
        should_store = self.history_manager.should_store_in_history(
            "", [], self.create_search_result("test", "test", "test")
        )

        self.assertTrue(should_store)
        self.assertTrue(any("storing by default" in msg for msg in self.log_messages))

    def test_should_store_fallback_on_missing_result(self):
        """Test fallback behavior when executed result is missing"""
        should_store = self.history_manager.should_store_in_history("test", [], None)

        self.assertTrue(should_store)
        self.assertTrue(any("storing by default" in msg for msg in self.log_messages))

    def test_should_store_fallback_on_analysis_error(self):
        """Test fallback behavior when analysis fails"""
        user_input = "test"
        executed_result = self.create_search_result("test", "test", "test")
        search_results = [executed_result]

        # Mock ResultAnalyzer to raise an exception
        with patch.object(
            ResultAnalyzer, "get_match_quality", side_effect=Exception("Analysis error")
        ):
            should_store = self.history_manager.should_store_in_history(
                user_input, search_results, executed_result
            )

        self.assertTrue(should_store)
        self.assertTrue(
            any("Error analyzing match quality" in msg for msg in self.log_messages)
            or any(
                "Critical error analyzing match quality" in msg
                for msg in self.log_messages
            )
            or any(
                "Unexpected error in match quality analysis" in msg
                for msg in self.log_messages
            )
        )
        self.assertTrue(
            any(
                "Falling back to default storage behavior" in msg
                for msg in self.log_messages
            )
            or any("storing by default" in msg for msg in self.log_messages)
        )

    def test_increment_usage_count_success(self):
        """Test successful usage count increment"""
        # Add initial history entry
        self.history_manager.add_user_input_history(
            "firefox", "desktop_file", "firefox.desktop", description="Firefox Browser"
        )

        # Verify initial usage count
        self.assertEqual(len(self.history_manager.user_input_history), 1)
        self.assertEqual(self.history_manager.user_input_history[0]["usage_count"], 1)

        # Increment usage count
        result = self.history_manager.increment_usage_count(
            "desktop_file", "firefox.desktop"
        )

        self.assertTrue(result)
        self.assertEqual(self.history_manager.user_input_history[0]["usage_count"], 2)
        self.assertTrue(
            any("Incremented usage count" in msg for msg in self.log_messages)
        )

    def test_increment_usage_count_with_user_input_match(self):
        """Test usage count increment with specific user input matching"""
        # Add two history entries for the same plugin/item but different user inputs
        self.history_manager.add_user_input_history(
            "firefox", "desktop_file", "firefox.desktop", description="Firefox Browser"
        )
        self.history_manager.add_user_input_history(
            "fire", "desktop_file", "firefox.desktop", description="Firefox Browser"
        )

        # Should have 2 entries initially
        self.assertEqual(len(self.history_manager.user_input_history), 2)

        # Increment usage count for specific user input
        result = self.history_manager.increment_usage_count(
            "desktop_file", "firefox.desktop", "firefox"
        )

        self.assertTrue(result)

        # Find the entry that was incremented
        firefox_entry = None
        for entry in self.history_manager.user_input_history:
            if entry["user_input"] == "firefox":
                firefox_entry = entry
                break

        self.assertIsNotNone(firefox_entry)
        self.assertEqual(firefox_entry["usage_count"], 2)

    def test_increment_usage_count_not_found(self):
        """Test usage count increment when entry is not found"""
        result = self.history_manager.increment_usage_count("nonexistent", "plugin.id")

        self.assertFalse(result)
        self.assertTrue(
            any("No existing history entry found" in msg for msg in self.log_messages)
        )

    def test_increment_usage_count_error_handling(self):
        """Test error handling in usage count increment"""
        # Create a history manager with invalid history file to trigger save error
        invalid_history_manager = HistoryManager()
        invalid_history_manager.history_file = "/invalid/path/history.json"

        # Add an entry manually
        invalid_history_manager.user_input_history = [
            {
                "user_input": "test",
                "plugin_id": "test",
                "item_id": "test",
                "usage_count": 1,
            }
        ]

        # This should handle the save error gracefully
        result = invalid_history_manager.increment_usage_count("test", "test")

        # Should still return True because the increment succeeded, even if save failed
        self.assertTrue(result)

    def test_increment_usage_count_updates_timestamp(self):
        """Test that usage count increment updates the timestamp"""
        import time

        # Add initial history entry
        initial_time = time.time() - 100  # 100 seconds ago
        self.history_manager.add_user_input_history(
            "firefox",
            "desktop_file",
            "firefox.desktop",
            timestamp=initial_time,
            description="Firefox Browser",
        )

        # Get initial timestamp
        initial_timestamp = self.history_manager.user_input_history[0]["timestamp"]
        self.assertEqual(initial_timestamp, initial_time)

        # Wait a small amount to ensure timestamp difference
        time.sleep(0.01)

        # Increment usage count
        result = self.history_manager.increment_usage_count(
            "desktop_file", "firefox.desktop"
        )

        self.assertTrue(result)

        # Verify timestamp was updated
        updated_timestamp = self.history_manager.user_input_history[0]["timestamp"]
        self.assertGreater(updated_timestamp, initial_timestamp)

    def test_integration_exact_match_storage_decision(self):
        """Integration test for exact match storage decision"""
        user_input = "calculator"
        executed_result = self.create_search_result("calculator", "calc1", "calculator")
        search_results = [executed_result]

        # Test the decision
        should_store = self.history_manager.should_store_in_history(
            user_input, search_results, executed_result
        )
        self.assertTrue(should_store)

        # If we were to store it (simulated)
        if should_store:
            self.history_manager.add_user_input_history(
                user_input,
                executed_result.plugin_id,
                executed_result.item_id,
                description=executed_result.description,
            )

        # Verify it was stored
        self.assertEqual(len(self.history_manager.user_input_history), 1)
        self.assertEqual(
            self.history_manager.user_input_history[0]["user_input"], user_input
        )

    def test_integration_partial_match_with_args_storage_decision(self):
        """Integration test for partial match with arguments storage decision"""
        user_input = "vim /etc/hosts"
        executed_result = self.create_search_result("executable", "/usr/bin/vim", "vim")
        search_results = [executed_result]

        # Test the decision
        should_store = self.history_manager.should_store_in_history(
            user_input, search_results, executed_result
        )
        self.assertTrue(should_store)

        # If we were to store it (simulated)
        if should_store:
            self.history_manager.add_user_input_history(
                user_input,
                executed_result.plugin_id,
                executed_result.item_id,
                description=executed_result.description,
            )

        # Verify it was stored
        self.assertEqual(len(self.history_manager.user_input_history), 1)
        self.assertEqual(
            self.history_manager.user_input_history[0]["user_input"], user_input
        )

    def test_integration_partial_match_without_args_no_storage(self):
        """Integration test for partial match without arguments - should not store"""
        user_input = "vi"  # Partial match for "vim"
        executed_result = self.create_search_result("executable", "/usr/bin/vim", "vim")
        search_results = [executed_result]

        # Test the decision
        should_store = self.history_manager.should_store_in_history(
            user_input, search_results, executed_result
        )
        self.assertFalse(should_store)

        # Simulate not storing it
        if should_store:
            self.history_manager.add_user_input_history(
                user_input,
                executed_result.plugin_id,
                executed_result.item_id,
                description=executed_result.description,
            )

        # Verify it was not stored
        self.assertEqual(len(self.history_manager.user_input_history), 0)

    def test_complex_scenario_mixed_storage_decisions(self):
        """Test complex scenario with multiple storage decisions"""
        # Scenario 1: Exact match - should store
        user_input1 = "firefox"
        result1 = self.create_search_result(
            "desktop_file", "firefox.desktop", "firefox"
        )
        should_store1 = self.history_manager.should_store_in_history(
            user_input1, [result1], result1
        )
        self.assertTrue(should_store1)

        # Scenario 2: Partial match with args - should store
        user_input2 = "vim /etc/passwd"
        result2 = self.create_search_result("executable", "/usr/bin/vim", "vim")
        should_store2 = self.history_manager.should_store_in_history(
            user_input2, [result2], result2
        )
        self.assertTrue(should_store2)

        # Scenario 3: Partial match without args - should not store
        user_input3 = "fire"
        result3 = self.create_search_result(
            "desktop_file", "firefox.desktop", "firefox"
        )
        should_store3 = self.history_manager.should_store_in_history(
            user_input3, [result3], result3
        )
        self.assertFalse(should_store3)

        # Store the ones that should be stored
        if should_store1:
            self.history_manager.add_user_input_history(
                user_input1, result1.plugin_id, result1.item_id
            )
        if should_store2:
            self.history_manager.add_user_input_history(
                user_input2, result2.plugin_id, result2.item_id
            )
        if should_store3:
            self.history_manager.add_user_input_history(
                user_input3, result3.plugin_id, result3.item_id
            )

        # Should have 2 entries stored
        self.assertEqual(len(self.history_manager.user_input_history), 2)
        stored_inputs = [
            entry["user_input"] for entry in self.history_manager.user_input_history
        ]
        self.assertIn(user_input1, stored_inputs)
        self.assertIn(user_input2, stored_inputs)
        self.assertNotIn(user_input3, stored_inputs)

    def test_usage_count_increment_with_existing_entries(self):
        """Test usage count increment with multiple existing entries"""
        # Add multiple entries for the same plugin/item
        self.history_manager.add_user_input_history(
            "firefox", "desktop_file", "firefox.desktop", description="Firefox"
        )
        self.history_manager.add_user_input_history(
            "firefox --private",
            "desktop_file",
            "firefox.desktop",
            description="Firefox",
        )

        # Should have 2 entries
        self.assertEqual(len(self.history_manager.user_input_history), 2)

        # Increment usage count (should find the first matching entry)
        result = self.history_manager.increment_usage_count(
            "desktop_file", "firefox.desktop"
        )
        self.assertTrue(result)

        # One of the entries should have incremented usage count
        usage_counts = [
            entry["usage_count"] for entry in self.history_manager.user_input_history
        ]
        self.assertIn(2, usage_counts)  # One entry should be incremented to 2

    def test_error_handling_in_should_store_with_invalid_result(self):
        """Test error handling when SearchResult has invalid attributes"""
        user_input = "test"

        # Create a mock result that will cause errors
        invalid_result = Mock()
        invalid_result.name = None  # This might cause issues
        invalid_result.description = None

        # Should handle gracefully and fall back to default behavior
        should_store = self.history_manager.should_store_in_history(
            user_input, [invalid_result], invalid_result
        )

        # Should default to storing
        self.assertTrue(should_store)


class TestHistoryStoragePerformance(unittest.TestCase):
    """Performance tests for history storage with large datasets"""

    def setUp(self):
        """Set up test fixtures"""
        # Create temporary history file
        self.temp_dir = tempfile.mkdtemp()
        self.history_file = os.path.join(self.temp_dir, "test_history.json")

        # Create HistoryManager with test config
        config = {"general": {"history_file": self.history_file}}
        self.history_manager = HistoryManager(config)

    def tearDown(self):
        """Clean up after tests"""
        # Clean up temp files
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_performance_with_large_search_results(self):
        """Test storage decision performance with large search result sets"""
        # Create a large number of search results
        large_search_results = []
        for i in range(1000):
            large_search_results.append(
                SearchResult(
                    plugin_id=f"plugin_{i % 10}",
                    item_id=f"item_{i}",
                    name=f"App {i}",
                    description=f"Description {i}",
                    icon=None,
                    score=100.0 - i * 0.01,
                )
            )

        executed_result = large_search_results[0]

        # Measure performance
        import time

        start_time = time.time()

        # Test multiple storage decisions
        for i in range(100):
            user_input = f"test_query_{i}"
            should_store = self.history_manager.should_store_in_history(
                user_input, large_search_results, executed_result
            )

        end_time = time.time()

        # Should complete quickly even with large result sets
        elapsed_time = end_time - start_time
        self.assertLess(
            elapsed_time,
            1.0,
            f"Storage decisions took {elapsed_time:.3f}s, expected < 1.0s",
        )

    def test_usage_count_increment_performance(self):
        """Test usage count increment performance with large history"""
        # Add many history entries
        for i in range(1000):
            self.history_manager.add_user_input_history(
                f"command_{i}",
                f"plugin_{i % 10}",
                f"item_{i}",
                description=f"Description {i}",
            )

        # Measure performance of usage count increment
        import time

        start_time = time.time()

        # Test multiple increments
        for i in range(100):
            plugin_id = f"plugin_{i % 10}"
            item_id = f"item_{i}"
            self.history_manager.increment_usage_count(plugin_id, item_id)

        end_time = time.time()

        # Should complete quickly even with large history
        elapsed_time = end_time - start_time
        self.assertLess(
            elapsed_time,
            0.5,
            f"Usage count increments took {elapsed_time:.3f}s, expected < 0.5s",
        )

    def test_memory_usage_with_large_history(self):
        """Test memory usage with large history datasets"""
        import gc

        # Force garbage collection before test
        gc.collect()
        initial_objects = len(gc.get_objects())

        # Add large number of history entries
        for i in range(2000):
            self.history_manager.add_user_input_history(
                f"command_{i}",
                f"plugin_{i % 20}",
                f"item_{i}",
                description=f"Description {i}",
            )

        # Force garbage collection after test
        gc.collect()
        final_objects = len(gc.get_objects())

        # Memory usage should not have grown excessively
        object_growth = final_objects - initial_objects
        max_allowed_growth = initial_objects * 0.3  # Allow 30% growth
        self.assertLess(
            object_growth,
            max_allowed_growth,
            f"Memory usage grew by {object_growth} objects, expected < {max_allowed_growth}",
        )


class TestHistoryStorageEdgeCases(unittest.TestCase):
    """Edge case tests for history storage logic"""

    def setUp(self):
        """Set up test fixtures"""
        # Create temporary history file
        self.temp_dir = tempfile.mkdtemp()
        self.history_file = os.path.join(self.temp_dir, "test_history.json")

        # Create HistoryManager with test config
        config = {"general": {"history_file": self.history_file}}
        self.history_manager = HistoryManager(config)

    def tearDown(self):
        """Clean up after tests"""
        # Clean up temp files
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_storage_decision_with_unicode_queries(self):
        """Test storage decisions with Unicode characters in queries"""
        user_input = "测试应用"  # Chinese characters
        executed_result = SearchResult(
            plugin_id="desktop_file",
            item_id="test_app.desktop",
            name="测试应用",
            description="Test Application",
            icon=None,
            score=100.0,
        )
        search_results = [executed_result]

        should_store = self.history_manager.should_store_in_history(
            user_input, search_results, executed_result
        )

        # Should handle Unicode correctly
        self.assertTrue(should_store)

        # If stored, should preserve Unicode
        if should_store:
            self.history_manager.add_user_input_history(
                user_input,
                executed_result.plugin_id,
                executed_result.item_id,
                description=executed_result.description,
            )

        # Verify Unicode preservation
        self.assertEqual(len(self.history_manager.user_input_history), 1)
        self.assertEqual(
            self.history_manager.user_input_history[0]["user_input"], "测试应用"
        )

    def test_storage_decision_with_very_long_queries(self):
        """Test storage decisions with very long query strings"""
        long_query = "a" * 10000  # 10KB query
        executed_result = SearchResult(
            plugin_id="terminal",
            item_id="long_command",
            name="long_command",
            description="Very long command",
            icon=None,
            score=100.0,
        )
        search_results = [executed_result]

        # Should handle long queries without performance issues
        import time

        start_time = time.time()
        should_store = self.history_manager.should_store_in_history(
            long_query, search_results, executed_result
        )
        end_time = time.time()

        # Should complete quickly even with long strings
        self.assertLess(end_time - start_time, 0.1)
        self.assertTrue(should_store)  # Should still make a decision

    def test_storage_decision_with_special_characters(self):
        """Test storage decisions with special characters in queries"""
        special_queries = [
            "firefox --private-window",
            "grep -r 'pattern' /path/to/files",
            "ssh user@host.com",
            "python -c \"print('hello')\"",
            "find . -name '*.py' | xargs grep 'pattern'",
            "curl -X POST -H 'Content-Type: application/json' -d '{\"key\":\"value\"}' http://api.example.com",
        ]

        for query in special_queries:
            executed_result = SearchResult(
                plugin_id="terminal",
                item_id="terminal_cmd",
                name="terminal",
                description="Terminal Command",
                icon=None,
                score=100.0,
            )
            search_results = [executed_result]

            should_store = self.history_manager.should_store_in_history(
                query, search_results, executed_result
            )

            # Should handle special characters correctly
            # Most of these should be stored as they contain command arguments
            self.assertTrue(
                should_store, f"Failed to store query with special characters: {query}"
            )

    def test_increment_usage_count_with_concurrent_access(self):
        """Test usage count increment with simulated concurrent access"""
        # Add initial entry
        self.history_manager.add_user_input_history(
            "firefox", "desktop_file", "firefox.desktop", description="Firefox"
        )

        # Simulate concurrent increments (in real scenario, this would be from different threads)
        results = []
        for i in range(10):
            result = self.history_manager.increment_usage_count(
                "desktop_file", "firefox.desktop"
            )
            results.append(result)

        # All increments should succeed
        self.assertTrue(all(results))

        # Final usage count should be 11 (1 initial + 10 increments)
        self.assertEqual(self.history_manager.user_input_history[0]["usage_count"], 11)

    def test_storage_decision_with_malformed_search_results(self):
        """Test storage decisions with malformed search results"""
        user_input = "test"

        # Create malformed results
        malformed_results = [
            None,  # None result
            Mock(),  # Mock without proper attributes
            SearchResult(None, None, None, None, None, 0),  # Result with None values
        ]

        # Add a proper result
        proper_result = SearchResult(
            plugin_id="test",
            item_id="test_item",
            name="test",
            description="Test",
            icon=None,
            score=100.0,
        )
        malformed_results.append(proper_result)

        # Should handle malformed results gracefully
        try:
            should_store = self.history_manager.should_store_in_history(
                user_input, malformed_results, proper_result
            )
            # Should default to storing when analysis is difficult
            self.assertTrue(should_store)
        except Exception as e:
            self.fail(f"Storage decision failed with malformed results: {e}")

    def test_increment_usage_count_with_corrupted_history(self):
        """Test usage count increment with corrupted history data"""
        # Manually corrupt history data
        self.history_manager.user_input_history = [
            {
                "user_input": "firefox",
                "plugin_id": "desktop_file",
                "item_id": "firefox.desktop",
                "usage_count": "not_a_number",  # Corrupted usage count
                "timestamp": "not_a_timestamp",  # Corrupted timestamp
            },
            {
                "user_input": "vim",
                # Missing plugin_id and item_id
                "usage_count": 1,
                "timestamp": time.time(),
            },
        ]

        # Should handle corrupted data gracefully
        result = self.history_manager.increment_usage_count(
            "desktop_file", "firefox.desktop"
        )

        # Should handle gracefully (might succeed or fail, but shouldn't crash)
        self.assertIsInstance(result, bool)

    def test_storage_decision_with_empty_or_none_inputs(self):
        """Test storage decisions with various empty or None inputs"""
        test_cases = [
            ("", None, None),
            (None, [], None),
            ("test", None, None),
            ("test", [], None),
            ("", [], SearchResult("test", "test", "test", "", None, 1.0)),
        ]

        for user_input, search_results, executed_result in test_cases:
            # Should handle gracefully and default to storing
            should_store = self.history_manager.should_store_in_history(
                user_input, search_results or [], executed_result
            )
            self.assertTrue(
                should_store,
                f"Failed with inputs: {user_input}, {search_results}, {executed_result}",
            )


class TestResultAnalyzerIntegration(unittest.TestCase):
    """Integration tests for ResultAnalyzer with HistoryManager"""

    def setUp(self):
        """Set up test fixtures"""
        # Create temporary history file
        self.temp_dir = tempfile.mkdtemp()
        self.history_file = os.path.join(self.temp_dir, "test_history.json")

        # Create HistoryManager with test config
        config = {"general": {"history_file": self.history_file}}
        self.history_manager = HistoryManager(config)

    def tearDown(self):
        """Clean up after tests"""
        # Clean up temp files
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_result_analyzer_exact_match_integration(self):
        """Test ResultAnalyzer exact match detection integrated with history storage"""
        test_cases = [
            ("firefox", "firefox"),
            ("Firefox", "firefox"),  # Case insensitive
            ("FIREFOX", "firefox"),
            ("calculator", "calculator"),
            ("vim", "vim"),
        ]

        for user_input, result_name in test_cases:
            executed_result = SearchResult(
                plugin_id="test",
                item_id="test_item",
                name=result_name,
                description="Test Description",
                icon=None,
                score=100.0,
            )
            search_results = [executed_result]

            # Should be detected as exact match and stored
            should_store = self.history_manager.should_store_in_history(
                user_input, search_results, executed_result
            )
            self.assertTrue(
                should_store,
                f"Exact match not detected: '{user_input}' -> '{result_name}'",
            )

            # Verify it's actually an exact match according to ResultAnalyzer
            is_exact = ResultAnalyzer.is_exact_match(user_input, executed_result)
            self.assertTrue(
                is_exact,
                f"ResultAnalyzer didn't detect exact match: '{user_input}' -> '{result_name}'",
            )

    def test_result_analyzer_partial_match_integration(self):
        """Test ResultAnalyzer partial match detection integrated with history storage"""
        test_cases = [
            # (user_input, result_name, has_args, should_store)
            ("fire", "firefox", False, False),  # Partial without args - don't store
            ("firefox --private", "firefox", True, True),  # Partial with args - store
            ("vim /etc/hosts", "vim", True, True),  # Partial with args - store
            ("calc", "calculator", False, False),  # Partial without args - don't store
        ]

        for (
            user_input,
            result_name,
            expected_has_args,
            expected_should_store,
        ) in test_cases:
            executed_result = SearchResult(
                plugin_id="test",
                item_id="test_item",
                name=result_name,
                description="Test Description",
                icon=None,
                score=100.0,
            )
            search_results = [executed_result]

            # Test storage decision
            should_store = self.history_manager.should_store_in_history(
                user_input, search_results, executed_result
            )
            self.assertEqual(
                should_store,
                expected_should_store,
                f"Storage decision mismatch for '{user_input}' -> '{result_name}': expected {expected_should_store}, got {should_store}",
            )

            # Verify argument detection
            has_args = ResultAnalyzer.has_command_arguments(user_input, executed_result)
            self.assertEqual(
                has_args,
                expected_has_args,
                f"Argument detection mismatch for '{user_input}' -> '{result_name}': expected {expected_has_args}, got {has_args}",
            )

    def test_result_analyzer_fuzzy_match_integration(self):
        """Test ResultAnalyzer fuzzy match detection integrated with history storage"""
        # Create a result that would be a true fuzzy match (not partial)
        executed_result = SearchResult(
            plugin_id="test",
            item_id="test_item",
            name="Firefox",
            description="Web Browser Application",
            icon=None,
            score=0.8,  # Lower score indicates fuzzy match
        )
        search_results = [executed_result]

        # Test with a query that would be a fuzzy match (not contained in name/description)
        user_input = "web_app"

        # Mock the get_match_quality to return "fuzzy" to test the fuzzy match path
        with patch.object(ResultAnalyzer, "get_match_quality", return_value="fuzzy"):
            should_store = self.history_manager.should_store_in_history(
                user_input, search_results, executed_result
            )

        # Should store fuzzy matches
        self.assertTrue(should_store)

        # Test with actual analyzer - this query should be partial since "browser" is in description
        user_input2 = "browser"
        should_store2 = self.history_manager.should_store_in_history(
            user_input2, search_results, executed_result
        )

        # Should not store partial match without arguments
        self.assertFalse(should_store2)

        # Verify match quality for the partial case
        match_quality = ResultAnalyzer.get_match_quality(user_input2, executed_result)
        self.assertEqual(match_quality, "partial")


if __name__ == "__main__":
    unittest.main()
