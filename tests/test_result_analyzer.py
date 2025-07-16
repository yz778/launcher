#!/usr/bin/env python3

import unittest
import sys
import os

# Add the launcher directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from launcher.plugins.base import SearchResult
from launcher.utils.result_analyzer import ResultAnalyzer


class TestResultAnalyzer(unittest.TestCase):
    """Test cases for the ResultAnalyzer class"""

    def setUp(self):
        """Set up test fixtures"""
        # Create sample search results for testing
        self.firefox_result = SearchResult(
            plugin_id="desktop_file",
            item_id="firefox",
            name="Firefox",
            description="Web Browser",
            score=100.0
        )

        self.calculator_result = SearchResult(
            plugin_id="desktop_file",
            item_id="calc",
            name="Calculator",
            description="Perform mathematical calculations",
            score=90.0
        )

        self.terminal_result = SearchResult(
            plugin_id="desktop_file",
            item_id="terminal",
            name="Terminal",
            description="Command line interface",
            score=85.0
        )

        # Result with empty description
        self.simple_result = SearchResult(
            plugin_id="test",
            item_id="simple",
            name="SimpleApp",
            description="",
            score=75.0
        )

    def test_is_exact_match_with_name(self):
        """Test exact match detection with result name"""
        # Exact match (case insensitive)
        self.assertTrue(ResultAnalyzer.is_exact_match("firefox", self.firefox_result))
        self.assertTrue(ResultAnalyzer.is_exact_match("Firefox", self.firefox_result))
        self.assertTrue(ResultAnalyzer.is_exact_match("FIREFOX", self.firefox_result))

        # Not exact match
        self.assertFalse(ResultAnalyzer.is_exact_match("fire", self.firefox_result))
        self.assertFalse(ResultAnalyzer.is_exact_match("firefox browser", self.firefox_result))

    def test_is_exact_match_with_description(self):
        """Test exact match detection with result description"""
        # Exact match with description
        self.assertTrue(ResultAnalyzer.is_exact_match("web browser", self.firefox_result))
        self.assertTrue(ResultAnalyzer.is_exact_match("Web Browser", self.firefox_result))

        # Not exact match
        self.assertFalse(ResultAnalyzer.is_exact_match("web", self.firefox_result))

    def test_is_exact_match_edge_cases(self):
        """Test exact match with edge cases"""
        # Empty query
        self.assertFalse(ResultAnalyzer.is_exact_match("", self.firefox_result))
        self.assertFalse(ResultAnalyzer.is_exact_match("   ", self.firefox_result))

        # None values
        self.assertFalse(ResultAnalyzer.is_exact_match(None, self.firefox_result))
        self.assertFalse(ResultAnalyzer.is_exact_match("firefox", None))

        # Empty description
        self.assertTrue(ResultAnalyzer.is_exact_match("SimpleApp", self.simple_result))
        self.assertFalse(ResultAnalyzer.is_exact_match("", self.simple_result))

    def test_is_partial_match_basic(self):
        """Test basic partial match detection"""
        # Partial matches
        self.assertTrue(ResultAnalyzer.is_partial_match("fire", self.firefox_result))
        self.assertTrue(ResultAnalyzer.is_partial_match("fox", self.firefox_result))
        self.assertTrue(ResultAnalyzer.is_partial_match("web", self.firefox_result))
        self.assertTrue(ResultAnalyzer.is_partial_match("browser", self.firefox_result))

        # Query longer than result name
        self.assertTrue(ResultAnalyzer.is_partial_match("firefox browser", self.firefox_result))

        # Not partial matches
        self.assertFalse(ResultAnalyzer.is_partial_match("chrome", self.firefox_result))
        self.assertFalse(ResultAnalyzer.is_partial_match("xyz", self.firefox_result))

    def test_is_partial_match_excludes_exact(self):
        """Test that partial match excludes exact matches"""
        # These should be exact matches, not partial
        self.assertFalse(ResultAnalyzer.is_partial_match("firefox", self.firefox_result))
        self.assertFalse(ResultAnalyzer.is_partial_match("Firefox", self.firefox_result))
        self.assertFalse(ResultAnalyzer.is_partial_match("web browser", self.firefox_result))

    def test_is_partial_match_edge_cases(self):
        """Test partial match with edge cases"""
        # Empty query
        self.assertFalse(ResultAnalyzer.is_partial_match("", self.firefox_result))

        # None values
        self.assertFalse(ResultAnalyzer.is_partial_match(None, self.firefox_result))
        self.assertFalse(ResultAnalyzer.is_partial_match("fire", None))

    def test_has_command_arguments_basic(self):
        """Test basic command argument detection"""
        # Commands with arguments
        self.assertTrue(ResultAnalyzer.has_command_arguments("firefox --private-window", self.firefox_result))
        self.assertTrue(ResultAnalyzer.has_command_arguments("firefox -P profile", self.firefox_result))
        self.assertTrue(ResultAnalyzer.has_command_arguments("firefox https://example.com", self.firefox_result))

        # Commands without arguments
        self.assertFalse(ResultAnalyzer.has_command_arguments("firefox", self.firefox_result))
        self.assertFalse(ResultAnalyzer.has_command_arguments("Firefox", self.firefox_result))

    def test_has_command_arguments_various_patterns(self):
        """Test command argument detection with various argument patterns"""
        # Different argument types
        self.assertTrue(ResultAnalyzer.has_command_arguments("terminal --working-directory=/home", self.terminal_result))
        self.assertTrue(ResultAnalyzer.has_command_arguments("terminal ~/Documents", self.terminal_result))
        self.assertTrue(ResultAnalyzer.has_command_arguments("terminal /usr/bin", self.terminal_result))
        self.assertTrue(ResultAnalyzer.has_command_arguments("calculator 2+2", self.calculator_result))

        # Quoted arguments
        self.assertTrue(ResultAnalyzer.has_command_arguments('firefox "https://example.com"', self.firefox_result))
        self.assertTrue(ResultAnalyzer.has_command_arguments("terminal 'ls -la'", self.terminal_result))

    def test_has_command_arguments_edge_cases(self):
        """Test command argument detection edge cases"""
        # Empty or short queries
        self.assertFalse(ResultAnalyzer.has_command_arguments("", self.firefox_result))
        self.assertFalse(ResultAnalyzer.has_command_arguments("f", self.firefox_result))

        # None values
        self.assertFalse(ResultAnalyzer.has_command_arguments(None, self.firefox_result))
        self.assertFalse(ResultAnalyzer.has_command_arguments("firefox --help", None))

        # Single word that doesn't match result
        self.assertFalse(ResultAnalyzer.has_command_arguments("chrome --help", self.firefox_result))

        # Malformed shell commands
        self.assertFalse(ResultAnalyzer.has_command_arguments('firefox "unclosed quote', self.firefox_result))

    def test_has_command_arguments_partial_name_match(self):
        """Test command argument detection with partial name matches"""
        # Partial matches with arguments should return True
        self.assertTrue(ResultAnalyzer.has_command_arguments("fire --private", self.firefox_result))
        self.assertTrue(ResultAnalyzer.has_command_arguments("calc 2+2", self.calculator_result))

        # But only if there are actual arguments
        self.assertFalse(ResultAnalyzer.has_command_arguments("fire", self.firefox_result))

    def test_get_match_quality(self):
        """Test overall match quality determination"""
        # Exact matches
        self.assertEqual(ResultAnalyzer.get_match_quality("firefox", self.firefox_result), "exact")
        self.assertEqual(ResultAnalyzer.get_match_quality("web browser", self.firefox_result), "exact")

        # Partial matches
        self.assertEqual(ResultAnalyzer.get_match_quality("fire", self.firefox_result), "partial")
        self.assertEqual(ResultAnalyzer.get_match_quality("web", self.firefox_result), "partial")

        # Fuzzy matches (assuming positive score)
        fuzzy_result = SearchResult("test", "fuzzy", "SomeApp", "Some description", score=50.0)
        self.assertEqual(ResultAnalyzer.get_match_quality("different", fuzzy_result), "fuzzy")

        # No match
        no_match_result = SearchResult("test", "none", "SomeApp", "Some description", score=0.0)
        self.assertEqual(ResultAnalyzer.get_match_quality("different", no_match_result), "none")

        # Edge cases
        self.assertEqual(ResultAnalyzer.get_match_quality("", self.firefox_result), "none")
        self.assertEqual(ResultAnalyzer.get_match_quality(None, self.firefox_result), "none")
        self.assertEqual(ResultAnalyzer.get_match_quality("firefox", None), "none")

    def test_whitespace_handling(self):
        """Test that methods handle whitespace correctly"""
        # Leading/trailing whitespace should be ignored
        self.assertTrue(ResultAnalyzer.is_exact_match("  firefox  ", self.firefox_result))
        self.assertTrue(ResultAnalyzer.is_partial_match("  fire  ", self.firefox_result))
        self.assertTrue(ResultAnalyzer.has_command_arguments("  firefox --help  ", self.firefox_result))

    def test_case_insensitive_matching(self):
        """Test that all matching is case insensitive"""
        # Different cases should all work
        test_cases = ["firefox", "Firefox", "FIREFOX", "FiReFoX"]

        for case in test_cases:
            self.assertTrue(ResultAnalyzer.is_exact_match(case, self.firefox_result))

        partial_cases = ["fire", "FIRE", "Fire", "FiRe"]
        for case in partial_cases:
            self.assertTrue(ResultAnalyzer.is_partial_match(case, self.firefox_result))


if __name__ == '__main__':
    unittest.main()