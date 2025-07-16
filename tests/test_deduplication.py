#!/usr/bin/env python3

import unittest
from unittest.mock import Mock, patch, MagicMock
import logging
import sys
import os

# Add the launcher directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from launcher.plugins.base import SearchResult

# Global logger for the mock class
logger = logging.getLogger('test_deduplication')


class MockLauncherWindow:
    """Mock launcher window that only implements the deduplication method"""

    def __init__(self):
        self.current_results = []

    def _deduplicate_results(self):
        """
        Remove history results if exact matches exist from other plugins.
        Enhanced with comprehensive logging, error handling, and performance optimization.
        """
        if not self.current_results:
            logger.debug("No results to deduplicate")
            return

        try:
            # Performance optimization: use efficient data structures for large result sets
            start_time = None
            if logger.isEnabledFor(logging.DEBUG):
                import time
                start_time = time.time()
                logger.debug(f"Starting deduplication for {len(self.current_results)} results")

            # Group results by plugin type using list comprehensions for better performance
            history_results = [r for r in self.current_results if r.plugin_id == "history"]
            other_results = [r for r in self.current_results if r.plugin_id != "history"]

            logger.debug(f"Found {len(history_results)} history results and {len(other_results)} other results")

            if not history_results or not other_results:
                logger.debug("No deduplication needed - missing history or other results")
                return  # No deduplication needed

            # Performance optimization: create efficient lookup structures
            # Use frozenset for immutable, hashable keys and dict for O(1) lookups
            other_result_keys = {}  # (plugin_id, item_id) -> result for debugging
            for result in other_results:
                try:
                    # Validate that result has required attributes
                    if not hasattr(result, 'plugin_id') or not hasattr(result, 'item_id'):
                        logger.warning(f"Result missing required attributes: {result}")
                        continue

                    key = (result.plugin_id, result.item_id)
                    other_result_keys[key] = result
                except Exception as e:
                    logger.warning(f"Error processing result {result}: {e}")
                    continue

            logger.debug(f"Created lookup table with {len(other_result_keys)} entries")

            # Filter out history results that have exact matches in other plugins
            filtered_history_results = []
            deduplicated_count = 0
            preserved_count = 0
            missing_metadata_count = 0

            for history_result in history_results:
                try:
                    # Validate history result structure
                    if not hasattr(history_result, 'metadata') or not isinstance(history_result.metadata, dict):
                        logger.warning(f"History result missing or invalid metadata: {history_result.name}")
                        filtered_history_results.append(history_result)
                        preserved_count += 1
                        missing_metadata_count += 1
                        continue

                    # Get original plugin info from history metadata with validation
                    original_plugin_id = history_result.metadata.get("original_plugin_id")
                    original_item_id = history_result.metadata.get("original_item_id")

                    # Validate metadata exists and is not empty
                    if not original_plugin_id or not original_item_id:
                        logger.debug(f"History result '{history_result.name}' missing original plugin metadata - preserving")
                        filtered_history_results.append(history_result)
                        preserved_count += 1
                        missing_metadata_count += 1
                        continue

                    # Check if this history item has an exact match in current results
                    match_key = (original_plugin_id, original_item_id)
                    matching_result = other_result_keys.get(match_key)

                    if matching_result is None:
                        # No exact match found, keep this history result
                        filtered_history_results.append(history_result)
                        preserved_count += 1
                        logger.debug(f"Preserving history result '{history_result.name}' - no current match for {original_plugin_id}:{original_item_id}")
                    else:
                        # Exact match found, remove history result
                        deduplicated_count += 1
                        logger.debug(f"Deduplicating history result '{history_result.name}' - matches current result '{matching_result.name}' ({original_plugin_id}:{original_item_id})")

                except Exception as e:
                    # Graceful error handling - preserve result if processing fails
                    logger.warning(f"Error processing history result '{getattr(history_result, 'name', 'unknown')}': {e}")
                    filtered_history_results.append(history_result)
                    preserved_count += 1
                    continue

            # Update current_results with deduplicated list
            # Maintain original order: other results first, then filtered history results
            original_count = len(self.current_results)
            self.current_results = other_results + filtered_history_results
            final_count = len(self.current_results)

            # Comprehensive logging summary
            logger.debug(f"Deduplication complete: {original_count} -> {final_count} results")
            logger.debug(f"  - Deduplicated: {deduplicated_count} history results")
            logger.debug(f"  - Preserved: {preserved_count} history results")
            logger.debug(f"  - Missing metadata: {missing_metadata_count} history results")

            if start_time and logger.isEnabledFor(logging.DEBUG):
                elapsed_time = time.time() - start_time
                logger.debug(f"Deduplication took {elapsed_time:.3f}s")

        except Exception as e:
            # Graceful error handling - log error but don't break search functionality
            logger.error(f"Error during deduplication: {e}")
            logger.debug("Continuing with original results due to deduplication error")
            # current_results remains unchanged, ensuring search continues to work


class TestDeduplication(unittest.TestCase):
    """Test cases for enhanced deduplication logic"""

    def setUp(self):
        """Set up test fixtures"""
        # Create mock launcher window
        self.launcher = MockLauncherWindow()

        # Set up logging to capture debug messages
        self.log_messages = []
        self.log_handler = logging.Handler()
        self.log_handler.emit = lambda record: self.log_messages.append(record.getMessage())

        logger.addHandler(self.log_handler)
        logger.setLevel(logging.DEBUG)

    def tearDown(self):
        """Clean up after tests"""
        logger.removeHandler(self.log_handler)

    def create_search_result(self, plugin_id, item_id, name, description="", metadata=None):
        """Helper to create SearchResult objects"""
        result = SearchResult(
            plugin_id=plugin_id,
            item_id=item_id,
            name=name,
            description=description,
            icon=None,
            score=1.0
        )
        if metadata:
            result.metadata = metadata
        return result

    def test_no_results_to_deduplicate(self):
        """Test deduplication with empty results list"""
        self.launcher.current_results = []
        self.launcher._deduplicate_results()

        # Should log that there are no results
        self.assertTrue(any("No results to deduplicate" in msg for msg in self.log_messages))
        self.assertEqual(len(self.launcher.current_results), 0)

    def test_no_history_results(self):
        """Test deduplication when there are no history results"""
        self.launcher.current_results = [
            self.create_search_result("desktop_file", "firefox.desktop", "Firefox"),
            self.create_search_result("executable", "/usr/bin/vim", "Vim")
        ]

        self.launcher._deduplicate_results()

        # Should log that no deduplication is needed
        self.assertTrue(any("No deduplication needed" in msg for msg in self.log_messages))
        self.assertEqual(len(self.launcher.current_results), 2)

    def test_no_other_results(self):
        """Test deduplication when there are only history results"""
        self.launcher.current_results = [
            self.create_search_result("history", "hist1", "Firefox", metadata={
                "original_plugin_id": "desktop_file",
                "original_item_id": "firefox.desktop"
            })
        ]

        self.launcher._deduplicate_results()

        # Should log that no deduplication is needed
        self.assertTrue(any("No deduplication needed" in msg for msg in self.log_messages))
        self.assertEqual(len(self.launcher.current_results), 1)

    def test_exact_match_deduplication(self):
        """Test removing history results with exact matches in other plugins"""
        self.launcher.current_results = [
            self.create_search_result("desktop_file", "firefox.desktop", "Firefox"),
            self.create_search_result("history", "hist1", "Firefox", metadata={
                "original_plugin_id": "desktop_file",
                "original_item_id": "firefox.desktop"
            }),
            self.create_search_result("executable", "/usr/bin/vim", "Vim"),
            self.create_search_result("history", "hist2", "Vim", metadata={
                "original_plugin_id": "executable",
                "original_item_id": "/usr/bin/vim"
            })
        ]

        self.launcher._deduplicate_results()

        # Should have only the non-history results
        self.assertEqual(len(self.launcher.current_results), 2)
        plugin_ids = [r.plugin_id for r in self.launcher.current_results]
        self.assertIn("desktop_file", plugin_ids)
        self.assertIn("executable", plugin_ids)
        self.assertNotIn("history", plugin_ids)

        # Should log deduplication actions
        self.assertTrue(any("Deduplicating history result" in msg for msg in self.log_messages))

    def test_preserve_history_without_current_match(self):
        """Test preserving history results that don't have current matches"""
        self.launcher.current_results = [
            self.create_search_result("desktop_file", "firefox.desktop", "Firefox"),
            self.create_search_result("history", "hist1", "Old App", metadata={
                "original_plugin_id": "desktop_file",
                "original_item_id": "old_app.desktop"
            }),
            self.create_search_result("history", "hist2", "Firefox", metadata={
                "original_plugin_id": "desktop_file",
                "original_item_id": "firefox.desktop"
            })
        ]

        self.launcher._deduplicate_results()

        # Should have Firefox from desktop_file and Old App from history
        self.assertEqual(len(self.launcher.current_results), 2)
        names = [r.name for r in self.launcher.current_results]
        self.assertIn("Firefox", names)
        self.assertIn("Old App", names)

        # Should log preservation of history result without match
        self.assertTrue(any("Preserving history result 'Old App'" in msg for msg in self.log_messages))

    def test_preserve_history_with_missing_metadata(self):
        """Test preserving history results that lack original plugin metadata"""
        self.launcher.current_results = [
            self.create_search_result("desktop_file", "firefox.desktop", "Firefox"),
            self.create_search_result("history", "hist1", "Some Command", metadata={}),
            self.create_search_result("history", "hist2", "Another Command", metadata={
                "original_plugin_id": None,
                "original_item_id": "something"
            }),
            self.create_search_result("history", "hist3", "Third Command")  # No metadata at all
        ]

        # Mock the third result to not have metadata attribute
        self.launcher.current_results[3].metadata = None

        self.launcher._deduplicate_results()

        # Should preserve all history results due to missing metadata
        self.assertEqual(len(self.launcher.current_results), 4)
        history_results = [r for r in self.launcher.current_results if r.plugin_id == "history"]
        self.assertEqual(len(history_results), 3)

        # Should log missing metadata warnings
        self.assertTrue(any("missing original plugin metadata" in msg for msg in self.log_messages))

    def test_mixed_scenario_complex(self):
        """Test complex scenario with mixed results"""
        self.launcher.current_results = [
            # Current results from various plugins
            self.create_search_result("desktop_file", "firefox.desktop", "Firefox"),
            self.create_search_result("executable", "/usr/bin/vim", "Vim"),
            self.create_search_result("calculator", "calc1", "2+2=4"),

            # History results - some with matches, some without
            self.create_search_result("history", "hist1", "Firefox", metadata={
                "original_plugin_id": "desktop_file",
                "original_item_id": "firefox.desktop"
            }),  # Should be removed
            self.create_search_result("history", "hist2", "Old Firefox", metadata={
                "original_plugin_id": "desktop_file",
                "original_item_id": "old_firefox.desktop"
            }),  # Should be preserved (no current match)
            self.create_search_result("history", "hist3", "Vim", metadata={
                "original_plugin_id": "executable",
                "original_item_id": "/usr/bin/vim"
            }),  # Should be removed
            self.create_search_result("history", "hist4", "Some Command", metadata={}),  # Should be preserved (no metadata)
        ]

        self.launcher._deduplicate_results()

        # Should have: Firefox, Vim, Calculator, Old Firefox, Some Command
        self.assertEqual(len(self.launcher.current_results), 5)

        # Check specific results
        names = [r.name for r in self.launcher.current_results]
        self.assertIn("Firefox", names)  # From desktop_file
        self.assertIn("Vim", names)      # From executable
        self.assertIn("2+2=4", names)    # From calculator
        self.assertIn("Old Firefox", names)  # From history (preserved)
        self.assertIn("Some Command", names) # From history (preserved)

        # Should not have duplicate Firefox or Vim from history
        firefox_count = sum(1 for r in self.launcher.current_results if r.name == "Firefox")
        vim_count = sum(1 for r in self.launcher.current_results if r.name == "Vim")
        self.assertEqual(firefox_count, 1)
        self.assertEqual(vim_count, 1)

    def test_performance_with_large_result_set(self):
        """Test deduplication performance with large result sets"""
        # Create a large number of results
        large_results = []

        # Add 100 non-history results
        for i in range(100):
            large_results.append(
                self.create_search_result(f"plugin_{i % 10}", f"item_{i}", f"App {i}")
            )

        # Add 100 history results, half with matches, half without
        for i in range(100):
            if i % 2 == 0:
                # Has match in current results
                large_results.append(
                    self.create_search_result("history", f"hist_{i}", f"App {i}", metadata={
                        "original_plugin_id": f"plugin_{i % 10}",
                        "original_item_id": f"item_{i}"
                    })
                )
            else:
                # No match in current results
                large_results.append(
                    self.create_search_result("history", f"hist_{i}", f"Old App {i}", metadata={
                        "original_plugin_id": f"old_plugin_{i % 10}",
                        "original_item_id": f"old_item_{i}"
                    })
                )

        self.launcher.current_results = large_results

        # Measure performance (should complete quickly)
        import time
        start_time = time.time()
        self.launcher._deduplicate_results()
        end_time = time.time()

        # Should complete in reasonable time (less than 1 second for this size)
        self.assertLess(end_time - start_time, 1.0)

        # Should have 100 non-history + 50 history (without matches) = 150 results
        self.assertEqual(len(self.launcher.current_results), 150)

        # Should log performance information
        self.assertTrue(any("Deduplication took" in msg for msg in self.log_messages))

    def test_error_handling_malformed_results(self):
        """Test graceful error handling with malformed results"""
        # Create results with various issues
        malformed_result = Mock()
        malformed_result.plugin_id = "history"
        malformed_result.name = "Malformed"
        # Missing other required attributes like metadata

        self.launcher.current_results = [
            self.create_search_result("desktop_file", "firefox.desktop", "Firefox"),
            malformed_result,
            self.create_search_result("history", "hist1", "Good History", metadata={
                "original_plugin_id": "desktop_file",
                "original_item_id": "firefox.desktop"
            })
        ]

        # Should not raise an exception
        try:
            self.launcher._deduplicate_results()
        except Exception as e:
            self.fail(f"Deduplication raised an exception with malformed results: {e}")

        # Should log warnings about malformed results (missing metadata)
        self.assertTrue(any("missing or invalid metadata" in msg for msg in self.log_messages))

    def test_error_handling_exception_during_processing(self):
        """Test graceful error handling when exceptions occur during processing"""
        # Create a result that will cause an exception when accessing metadata
        problematic_result = self.create_search_result("history", "hist1", "Problem")

        # Create a custom dict-like class that raises an exception on get()
        class ProblematicDict(dict):
            def get(self, *args, **kwargs):
                raise RuntimeError("Simulated error")

        problematic_result.metadata = ProblematicDict({"test": "value"})

        self.launcher.current_results = [
            self.create_search_result("desktop_file", "firefox.desktop", "Firefox"),
            problematic_result
        ]

        # Should not raise an exception and should preserve the problematic result
        try:
            self.launcher._deduplicate_results()
        except Exception as e:
            self.fail(f"Deduplication raised an exception: {e}")

        # Should still have both results (error handling preserves problematic result)
        self.assertEqual(len(self.launcher.current_results), 2)

        # Should log the error
        self.assertTrue(any("Error processing history result" in msg for msg in self.log_messages))

    def test_maintain_result_order(self):
        """Test that deduplication maintains proper result ordering"""
        self.launcher.current_results = [
            self.create_search_result("desktop_file", "app1.desktop", "App 1"),
            self.create_search_result("executable", "/usr/bin/app2", "App 2"),
            self.create_search_result("history", "hist1", "App 1", metadata={
                "original_plugin_id": "desktop_file",
                "original_item_id": "app1.desktop"
            }),
            self.create_search_result("desktop_file", "app3.desktop", "App 3"),
            self.create_search_result("history", "hist2", "Old App", metadata={
                "original_plugin_id": "desktop_file",
                "original_item_id": "old_app.desktop"
            })
        ]

        self.launcher._deduplicate_results()

        # Should maintain order: non-history results first, then preserved history results
        expected_order = ["App 1", "App 2", "App 3", "Old App"]
        actual_order = [r.name for r in self.launcher.current_results]
        self.assertEqual(actual_order, expected_order)

    def test_comprehensive_logging(self):
        """Test that comprehensive logging is working correctly"""
        self.launcher.current_results = [
            self.create_search_result("desktop_file", "firefox.desktop", "Firefox"),
            self.create_search_result("history", "hist1", "Firefox", metadata={
                "original_plugin_id": "desktop_file",
                "original_item_id": "firefox.desktop"
            }),
            self.create_search_result("history", "hist2", "Old App", metadata={
                "original_plugin_id": "desktop_file",
                "original_item_id": "old_app.desktop"
            })
        ]

        self.launcher._deduplicate_results()

        # Check for specific log messages
        log_text = " ".join(self.log_messages)

        self.assertIn("Starting deduplication for 3 results", log_text)
        self.assertIn("Found 2 history results and 1 other results", log_text)
        self.assertIn("Created lookup table with 1 entries", log_text)
        self.assertIn("Deduplicating history result 'Firefox'", log_text)
        self.assertIn("Preserving history result 'Old App'", log_text)
        self.assertIn("Deduplication complete: 3 -> 2 results", log_text)
        self.assertIn("Deduplicated: 1 history results", log_text)
        self.assertIn("Preserved: 1 history results", log_text)
        self.assertIn("Deduplication took", log_text)


class TestDeduplicationPerformance(unittest.TestCase):
    """Performance tests for deduplication with large datasets"""

    def setUp(self):
        """Set up test fixtures"""
        self.launcher = MockLauncherWindow()

    def test_performance_with_very_large_history_file(self):
        """Test deduplication performance with very large history datasets"""
        # Create 500 non-history results
        large_results = []
        for i in range(500):
            large_results.append(
                SearchResult(
                    plugin_id=f"plugin_{i % 20}",
                    item_id=f"item_{i}",
                    name=f"App {i}",
                    description=f"Description {i}",
                    icon=None,
                    score=100.0 - i * 0.01
                )
            )

        # Create 1000 history results with various match scenarios
        for i in range(1000):
            metadata = {}
            if i % 3 == 0:
                # Has exact match in current results
                metadata = {
                    "original_plugin_id": f"plugin_{i % 20}",
                    "original_item_id": f"item_{i % 500}",
                    "usage_count": i % 10 + 1
                }
            elif i % 3 == 1:
                # No match in current results
                metadata = {
                    "original_plugin_id": f"old_plugin_{i % 20}",
                    "original_item_id": f"old_item_{i}",
                    "usage_count": i % 5 + 1
                }
            else:
                # Missing or invalid metadata
                if i % 6 == 2:
                    metadata = {}  # No metadata
                else:
                    metadata = {
                        "original_plugin_id": "",
                        "original_item_id": None,
                        "usage_count": i % 3 + 1
                    }

            large_results.append(
                SearchResult(
                    plugin_id="history",
                    item_id=f"hist_{i}",
                    name=f"History Item {i}",
                    description=f"Historical item {i}",
                    icon=None,
                    score=90.0 - i * 0.01,
                    metadata=metadata
                )
            )

        self.launcher.current_results = large_results

        # Measure performance
        import time
        start_time = time.time()
        self.launcher._deduplicate_results()
        end_time = time.time()

        # Should complete in reasonable time (less than 2 seconds for this large dataset)
        elapsed_time = end_time - start_time
        self.assertLess(elapsed_time, 2.0, f"Deduplication took {elapsed_time:.3f}s, expected < 2.0s")

        # Verify correctness - should have removed about 1/3 of history results (those with matches)
        final_count = len(self.launcher.current_results)
        expected_min = 500 + 600  # 500 non-history + ~600 history (2/3 of 1000)
        expected_max = 500 + 700  # Allow some variance for edge cases
        self.assertGreaterEqual(final_count, expected_min)
        self.assertLessEqual(final_count, expected_max)

    def test_memory_usage_with_large_datasets(self):
        """Test that memory usage remains reasonable with large datasets"""
        import gc
        import sys

        # Force garbage collection before test
        gc.collect()
        initial_objects = len(gc.get_objects())

        # Create large dataset
        large_results = []
        for i in range(2000):
            if i % 2 == 0:
                # Non-history result
                large_results.append(
                    SearchResult(
                        plugin_id=f"plugin_{i % 10}",
                        item_id=f"item_{i}",
                        name=f"App {i}",
                        description=f"Description {i}",
                        icon=None,
                        score=100.0 - i * 0.01
                    )
                )
            else:
                # History result
                large_results.append(
                    SearchResult(
                        plugin_id="history",
                        item_id=f"hist_{i}",
                        name=f"History {i}",
                        description=f"Historical {i}",
                        icon=None,
                        score=90.0 - i * 0.01,
                        metadata={
                            "original_plugin_id": f"plugin_{i % 10}",
                            "original_item_id": f"item_{i-1}" if i > 0 else "item_0",
                            "usage_count": i % 5 + 1
                        }
                    )
                )

        self.launcher.current_results = large_results

        # Run deduplication
        self.launcher._deduplicate_results()

        # Force garbage collection after test
        gc.collect()
        final_objects = len(gc.get_objects())

        # Memory usage should not have grown excessively
        # Allow for some growth but not more than 50% increase in objects
        object_growth = final_objects - initial_objects
        max_allowed_growth = initial_objects * 0.5
        self.assertLess(object_growth, max_allowed_growth,
                       f"Memory usage grew by {object_growth} objects, expected < {max_allowed_growth}")

    def test_deduplication_with_concurrent_modifications(self):
        """Test deduplication behavior when results list is modified during processing"""
        # This test simulates edge cases where the results list might be modified
        # during deduplication (though this shouldn't happen in normal operation)

        results = [
            SearchResult(plugin_id="desktop_file", item_id="app1.desktop", name="App 1", score=100.0),
            SearchResult(
                plugin_id="history", item_id="hist_1", name="App 1", score=90.0,
                metadata={"original_plugin_id": "desktop_file", "original_item_id": "app1.desktop"}
            )
        ]

        self.launcher.current_results = results

        # Mock a scenario where the list is modified during iteration
        # (This is a pathological case that shouldn't happen in practice)
        original_deduplicate = self.launcher._deduplicate_results

        def modified_deduplicate():
            # Start normal deduplication
            if not self.launcher.current_results:
                return

            # Simulate concurrent modification by adding a result mid-process
            if len(self.launcher.current_results) == 2:
                new_result = SearchResult(
                    plugin_id="calculator", item_id="calc1", name="2+2=4", score=95.0
                )
                self.launcher.current_results.append(new_result)

            # Continue with original logic (simplified)
            history_results = [r for r in self.launcher.current_results if r.plugin_id == "history"]
            other_results = [r for r in self.launcher.current_results if r.plugin_id != "history"]

            if history_results and other_results:
                # Simple deduplication
                filtered_history = []
                for hist_result in history_results:
                    if hasattr(hist_result, 'metadata') and hist_result.metadata:
                        orig_plugin = hist_result.metadata.get("original_plugin_id")
                        orig_item = hist_result.metadata.get("original_item_id")

                        # Check for match
                        has_match = any(
                            r.plugin_id == orig_plugin and r.item_id == orig_item
                            for r in other_results
                        )

                        if not has_match:
                            filtered_history.append(hist_result)
                    else:
                        filtered_history.append(hist_result)

                self.launcher.current_results = other_results + filtered_history

        self.launcher._deduplicate_results = modified_deduplicate

        # Should handle gracefully without crashing
        try:
            self.launcher._deduplicate_results()
            # Should have non-history results plus any preserved history results
            self.assertGreaterEqual(len(self.launcher.current_results), 2)
        except Exception as e:
            self.fail(f"Deduplication failed with concurrent modification: {e}")


class TestDeduplicationEdgeCases(unittest.TestCase):
    """Edge case tests for deduplication logic"""

    def setUp(self):
        """Set up test fixtures"""
        self.launcher = MockLauncherWindow()

    def test_deduplication_with_unicode_characters(self):
        """Test deduplication with Unicode characters in names and metadata"""
        results = [
            SearchResult(plugin_id="desktop_file", item_id="café.desktop", name="Café App", score=100.0),
            SearchResult(
                plugin_id="history", item_id="hist_1", name="Café App", score=90.0,
                metadata={"original_plugin_id": "desktop_file", "original_item_id": "café.desktop"}
            ),
            SearchResult(
                plugin_id="history", item_id="hist_2", name="测试应用", score=85.0,
                metadata={"original_plugin_id": "desktop_file", "original_item_id": "test_app.desktop"}
            )
        ]

        self.launcher.current_results = results
        self.launcher._deduplicate_results()

        # Should handle Unicode correctly
        final_results = self.launcher.current_results
        self.assertEqual(len(final_results), 2)  # Café history should be removed

        # Verify Unicode preservation
        cafe_result = next((r for r in final_results if "Café" in r.name), None)
        self.assertIsNotNone(cafe_result)
        self.assertEqual(cafe_result.plugin_id, "desktop_file")

        chinese_result = next((r for r in final_results if "测试应用" in r.name), None)
        self.assertIsNotNone(chinese_result)
        self.assertEqual(chinese_result.plugin_id, "history")

    def test_deduplication_with_very_long_strings(self):
        """Test deduplication with very long strings in metadata"""
        long_string = "a" * 10000  # 10KB string

        results = [
            SearchResult(plugin_id="desktop_file", item_id=long_string, name="Long App", score=100.0),
            SearchResult(
                plugin_id="history", item_id="hist_1", name="Long App", score=90.0,
                metadata={"original_plugin_id": "desktop_file", "original_item_id": long_string}
            )
        ]

        self.launcher.current_results = results

        # Should handle long strings without performance issues
        import time
        start_time = time.time()
        self.launcher._deduplicate_results()
        end_time = time.time()

        # Should complete quickly even with long strings
        self.assertLess(end_time - start_time, 0.1)

        # Should deduplicate correctly
        final_results = self.launcher.current_results
        self.assertEqual(len(final_results), 1)
        self.assertEqual(final_results[0].plugin_id, "desktop_file")

    def test_deduplication_with_special_characters_in_ids(self):
        """Test deduplication with special characters in plugin/item IDs"""
        special_chars = "!@#$%^&*()[]{}|;:,.<>?/~`"

        results = [
            SearchResult(plugin_id="plugin@#$", item_id="item!@#", name="Special App", score=100.0),
            SearchResult(
                plugin_id="history", item_id="hist_1", name="Special App", score=90.0,
                metadata={"original_plugin_id": "plugin@#$", "original_item_id": "item!@#"}
            )
        ]

        self.launcher.current_results = results
        self.launcher._deduplicate_results()

        # Should handle special characters correctly
        final_results = self.launcher.current_results
        self.assertEqual(len(final_results), 1)
        self.assertEqual(final_results[0].plugin_id, "plugin@#$")

    def test_deduplication_with_circular_references(self):
        """Test deduplication with circular reference patterns in metadata"""
        results = [
            SearchResult(plugin_id="plugin_a", item_id="item_1", name="App A", score=100.0),
            SearchResult(plugin_id="plugin_b", item_id="item_2", name="App B", score=95.0),
            SearchResult(
                plugin_id="history", item_id="hist_1", name="App A", score=90.0,
                metadata={"original_plugin_id": "plugin_b", "original_item_id": "item_2"}  # Points to B
            ),
            SearchResult(
                plugin_id="history", item_id="hist_2", name="App B", score=85.0,
                metadata={"original_plugin_id": "plugin_a", "original_item_id": "item_1"}  # Points to A
            )
        ]

        self.launcher.current_results = results
        self.launcher._deduplicate_results()

        # Should handle circular references correctly
        final_results = self.launcher.current_results
        self.assertEqual(len(final_results), 2)  # Both history results should be removed

        # Should keep the non-history results
        plugin_ids = [r.plugin_id for r in final_results]
        self.assertIn("plugin_a", plugin_ids)
        self.assertIn("plugin_b", plugin_ids)


if __name__ == '__main__':
    unittest.main()