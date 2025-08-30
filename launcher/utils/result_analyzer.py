#!/usr/bin/env python3

from launcher.plugins.base import SearchResult
import logging
import re
import shlex

logger = logging.getLogger(__name__)


class ResultAnalyzer:
    """Utility class for analyzing search results and queries"""

    @staticmethod
    def is_exact_match(query: str, result: SearchResult) -> bool:
        """
        Check if query exactly matches result name or description

        Args:
            query: The user's search query
            result: The search result to check

        Returns:
            True if query exactly matches result name or description
        """
        try:
            # Enhanced input validation
            if not query:
                return False

            if not result:
                return False

            # Validate query is a string
            if not isinstance(query, str):
                logger.warning(f"Query is not a string ({type(query)}): {repr(query)}")
                return False

            # Validate result has required attributes
            try:
                result_name = getattr(result, "name", None)
                result_description = getattr(result, "description", None)
            except Exception as attr_error:
                logger.warning(f"Error accessing result attributes: {attr_error}")
                return False

            if result_name is None:
                return False

            # Safely normalize strings with type checking
            try:
                query_normalized = query.strip().lower()
            except Exception as e:
                logger.warning(f"Error normalizing query '{query}': {e}")
                return False

            try:
                name_normalized = str(result_name).strip().lower()
            except Exception as e:
                logger.warning(f"Error normalizing result name '{result_name}': {e}")
                return False

            description_normalized = ""
            if result_description:
                try:
                    description_normalized = str(result_description).strip().lower()
                except Exception as e:
                    description_normalized = ""

            # Check exact match with name or description
            is_match = query_normalized == name_normalized or (
                description_normalized and query_normalized == description_normalized
            )

            return is_match

        except Exception as e:
            logger.error(f"Critical error in exact match check: {e}")
            return False

    @staticmethod
    def is_partial_match(query: str, result: SearchResult) -> bool:
        """
        Check if result is only a partial match for the query

        A partial match means the query contains the result name/description
        but has additional content, or the result name/description contains
        the query but is longer.

        Args:
            query: The user's search query
            result: The search result to check

        Returns:
            True if result is only a partial match (not exact)
        """
        try:
            # Enhanced input validation
            if not query or not result:
                return False

            # Validate input types
            if not isinstance(query, str):
                logger.warning(
                    f"Query is not a string in partial match check ({type(query)}): {repr(query)}"
                )
                return False

            # If it's an exact match, it's not a partial match
            try:
                if ResultAnalyzer.is_exact_match(query, result):
                    return False
            except Exception as exact_error:
                logger.warning(
                    f"Error checking exact match in partial match: {exact_error}"
                )
                # Continue with partial match check even if exact match check fails

            # Validate result attributes
            try:
                result_name = getattr(result, "name", None)
                result_description = getattr(result, "description", None)
            except Exception as attr_error:
                logger.warning(
                    f"Error accessing result attributes in partial match: {attr_error}"
                )
                return False

            if result_name is None:
                return False

            # Safely normalize strings
            try:
                query_normalized = query.strip().lower()
            except Exception as e:
                logger.warning(
                    f"Error normalizing query in partial match '{query}': {e}"
                )
                return False

            try:
                name_normalized = str(result_name).strip().lower()
            except Exception as e:
                logger.warning(
                    f"Error normalizing result name in partial match '{result_name}': {e}"
                )
                return False

            description_normalized = ""
            if result_description:
                try:
                    description_normalized = str(result_description).strip().lower()
                except Exception:
                    description_normalized = ""

            # Check if query is contained in name/description or vice versa
            try:
                is_partial = (
                    query_normalized in name_normalized
                    or name_normalized in query_normalized
                    or (
                        description_normalized
                        and query_normalized in description_normalized
                    )
                    or (
                        description_normalized
                        and description_normalized in query_normalized
                    )
                )

                return is_partial

            except Exception as match_error:
                logger.warning(
                    f"Error performing partial match comparison: {match_error}"
                )
                return False

        except Exception as e:
            logger.error(f"Critical error in partial match check: {e}")
            return False

    @staticmethod
    def has_command_arguments(query: str, result: SearchResult) -> bool:
        """
        Check if query contains command line arguments beyond the base command

        This method detects when a user has typed a command followed by
        arguments (e.g., "firefox --private-window" where "firefox" is the base).

        Args:
            query: The user's search query
            result: The search result to check

        Returns:
            True if query appears to contain command arguments
        """
        try:
            # Enhanced input validation
            if not query or not result:
                return False

            # Validate input types
            if not isinstance(query, str):
                logger.warning(
                    f"Query is not a string in command arguments check ({type(query)}): {repr(query)}"
                )
                return False

            # Validate result attributes
            try:
                result_name = getattr(result, "name", None)
            except Exception as attr_error:
                logger.warning(
                    f"Error accessing result name in command arguments check: {attr_error}"
                )
                return False

            if result_name is None:
                return False

            # Safely strip query
            try:
                query_stripped = query.strip()
            except Exception:
                return False

            # If query is empty or too short, no arguments
            if len(query_stripped) < 2:
                return False

            # Parse command line arguments with enhanced error handling
            try:
                parsed_args = shlex.split(query_stripped)
            except ValueError as e:
                return False
            except Exception as e:
                logger.warning(
                    f"Unexpected error parsing query '{query_stripped}': {e}"
                )
                return False

            # If there's only one argument, no additional arguments
            if len(parsed_args) <= 1:
                return False

            # Safely get the first argument (potential command)
            try:
                base_command = parsed_args[0].lower()
                result_name_lower = str(result_name).lower()
            except Exception as e:
                logger.warning(f"Error normalizing command/result name: {e}")
                return False

            # Check if the base command matches the result name exactly or partially
            try:
                command_matches = (
                    base_command == result_name_lower
                    or base_command in result_name_lower
                    or result_name_lower in base_command
                )
            except Exception as e:
                logger.warning(f"Error checking command match: {e}")
                return False

            if command_matches:
                # Check if remaining arguments look like command line options/arguments
                remaining_args = parsed_args[1:]

                # Look for common argument patterns with error handling
                for i, arg in enumerate(remaining_args):
                    try:
                        # Validate argument is a string
                        if not isinstance(arg, str):
                            continue

                        # Arguments starting with - or --
                        if arg.startswith("-"):
                            return True

                        # URLs or file paths
                        if "://" in arg or arg.startswith("/") or arg.startswith("~"):
                            return True

                        # File extensions (but be careful not to match regular words)
                        if "." in arg:
                            try:
                                parts = arg.split(".")
                                if (
                                    len(parts) == 2
                                    and len(parts[1]) <= 4
                                    and parts[1].isalnum()
                                ):
                                    return True
                            except Exception:
                                pass

                        # Mathematical expressions (for calculator)
                        try:
                            if re.search(r"[+\-*/=]", arg):
                                return True
                        except Exception:
                            pass

                    except Exception:
                        continue

                # If we have additional arguments but they don't look like command line args,
                # this might just be a search phrase, not a command with arguments
                return False

            return False

        except Exception as e:
            logger.error(f"Critical error in command arguments check: {e}")
            return False

    @staticmethod
    def get_match_quality(query: str, result: SearchResult) -> str:
        """
        Determine the overall match quality between query and result

        Args:
            query: The user's search query
            result: The search result to analyze

        Returns:
            String indicating match quality: "exact", "partial", "fuzzy", or "none"
        """
        try:
            # Enhanced input validation
            if not query or not result:
                return "none"

            # Validate input types
            if not isinstance(query, str):
                logger.warning(
                    f"Query is not a string in match quality check ({type(query)}): {repr(query)}"
                )
                return "none"

            # Validate result has score attribute
            try:
                result_score = getattr(result, "score", None)
            except Exception as attr_error:
                logger.warning(
                    f"Error accessing result score in match quality check: {attr_error}"
                )
                result_score = 0

            # Check exact match first with error handling
            try:
                if ResultAnalyzer.is_exact_match(query, result):
                    return "exact"
            except Exception as exact_error:
                logger.warning(
                    f"Error checking exact match in match quality: {exact_error}"
                )
                # Continue with other checks

            # Check partial match next with error handling
            try:
                if ResultAnalyzer.is_partial_match(query, result):
                    return "partial"
            except Exception as partial_error:
                logger.warning(
                    f"Error checking partial match in match quality: {partial_error}"
                )
                # Continue with other checks

            # If the result has a positive score but isn't exact or partial, it's fuzzy
            try:
                if result_score is not None and result_score > 0:
                    return "fuzzy"
            except Exception as score_error:
                logger.warning(
                    f"Error checking result score in match quality: {score_error}"
                )

            # No meaningful match
            return "none"

        except Exception as e:
            logger.error(f"Critical error in match quality check: {e}")
            return "none"  # Safe fallback
