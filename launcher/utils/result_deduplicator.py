#!/usr/bin/env python3

import logging
import time
from typing import Dict, Any, List, Optional
from launcher.plugins.base import SearchResult

logger = logging.getLogger(__name__)


class ResultDeduplicator:
    """
    Handles deduplication of search results, specifically removing redundant
    history results when a more canonical result from another plugin exists.
    """

    def __init__(self):
        pass

    def should_deduplicate_history_entry(
        self, history_name: str, current_name: str
    ) -> bool:
        """
        Determine if a history entry should be deduplicated based on similarity to current result.

        Args:
            history_name: Name from the history entry (user input)
            current_name: Name from the current search result

        Returns:
            True if the history entry should be removed (deduplicated), False to keep it
        """
        if not history_name or not current_name:
            return False

        history_lower = history_name.lower().strip()
        current_lower = current_name.lower().strip()

        # Don't deduplicate if they're exactly the same (shouldn't happen but be safe)
        if history_lower == current_lower:
            return True

        # Don't deduplicate if the history entry is significantly longer
        # This preserves entries like "brave gmail.com" when "brave" is found
        if len(history_lower) > len(current_lower) * 1.5:
            return False

        # Don't deduplicate if the history entry contains additional meaningful content
        # Check for URLs, file paths, or additional arguments
        if any(char in history_lower for char in [".", "/", ":", "=", "&", "?"]):
            return False

        # Don't deduplicate if the history entry has multiple words and current is single word
        history_words = history_lower.split()
        current_words = current_lower.split()

        if len(history_words) > 1 and len(current_words) == 1:
            return False

        # Only deduplicate if the history entry is very similar to current result
        # (essentially the same thing with minor variations)
        if (
            history_lower.startswith(current_lower)
            and len(history_lower) <= len(current_lower) + 3
        ):
            return True

        return False

    def deduplicate_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        Remove history results if exact matches exist from other plugins.
        Enhanced with comprehensive logging, error handling, and performance optimization.

        Args:
            results: List of search results to deduplicate

        Returns:
            List of deduplicated results
        """
        if not results:
            logger.debug("No results to deduplicate")
            return results

        try:
            # Performance optimization: use efficient data structures for large result sets
            start_time = None
            if logger.isEnabledFor(logging.DEBUG):
                start_time = time.time()
                logger.debug(f"Starting deduplication for {len(results)} results")

            # Group results by plugin type using list comprehensions for better performance
            history_results = []
            other_results = []

            for result in results:
                try:
                    # Enhanced validation of result structure
                    if not hasattr(result, "plugin_id"):
                        logger.warning(
                            f"Result missing plugin_id attribute: {getattr(result, 'name', 'unknown')}"
                        )
                        continue

                    if result.plugin_id == "history":
                        history_results.append(result)
                    else:
                        other_results.append(result)

                except Exception as e:
                    logger.error(f"Error categorizing result: {e}")
                    # Preserve result in other_results as fallback to avoid data loss
                    other_results.append(result)
                    continue

            logger.debug(
                f"Found {len(history_results)} history results and {len(other_results)} other results"
            )

            if not history_results or not other_results:
                logger.debug(
                    "No deduplication needed - missing history or other results"
                )
                return results  # No deduplication needed

            # Performance optimization: create efficient lookup structures
            # Use dict for O(1) lookups with enhanced error handling
            other_result_keys = {}  # (plugin_id, item_id) -> result for debugging
            invalid_results_count = 0

            for result in other_results:
                try:
                    # Enhanced validation that result has required attributes
                    if not hasattr(result, "plugin_id") or not hasattr(
                        result, "item_id"
                    ):
                        logger.warning(
                            f"Result missing required attributes (plugin_id/item_id): {getattr(result, 'name', 'unknown')}"
                        )
                        invalid_results_count += 1
                        continue

                    # Validate that plugin_id and item_id are not None or empty
                    if not result.plugin_id or not result.item_id:
                        logger.debug(
                            f"Result has empty plugin_id or item_id: {getattr(result, 'name', 'unknown')}"
                        )
                        invalid_results_count += 1
                        continue

                    key = (result.plugin_id, result.item_id)
                    other_result_keys[key] = result

                except AttributeError as e:
                    logger.warning(
                        f"AttributeError processing result {getattr(result, 'name', 'unknown')}: {e}"
                    )
                    invalid_results_count += 1
                    continue
                except Exception as e:
                    logger.error(
                        f"Unexpected error processing result {getattr(result, 'name', 'unknown')}: {e}"
                    )
                    invalid_results_count += 1
                    continue

            logger.debug(
                f"Created lookup table with {len(other_result_keys)} entries ({invalid_results_count} invalid results skipped)"
            )

            # Filter out history results that have exact matches in other plugins
            filtered_history_results = []
            deduplicated_count = 0
            preserved_count = 0
            missing_metadata_count = 0
            error_count = 0

            for history_result in history_results:
                try:
                    # Enhanced validation of history result structure
                    if not hasattr(history_result, "metadata"):
                        logger.warning(
                            f"History result missing metadata attribute: {getattr(history_result, 'name', 'unknown')}"
                        )
                        filtered_history_results.append(history_result)
                        preserved_count += 1
                        missing_metadata_count += 1
                        continue

                    if not isinstance(history_result.metadata, dict):
                        logger.warning(
                            f"History result has invalid metadata type ({type(history_result.metadata)}): {getattr(history_result, 'name', 'unknown')}"
                        )
                        filtered_history_results.append(history_result)
                        preserved_count += 1
                        missing_metadata_count += 1
                        continue

                    # Get original plugin info from history metadata with enhanced validation
                    try:
                        original_plugin_id = history_result.metadata.get(
                            "original_plugin_id"
                        )
                        original_item_id = history_result.metadata.get(
                            "original_item_id"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Error accessing metadata for history result '{getattr(history_result, 'name', 'unknown')}': {e}"
                        )
                        filtered_history_results.append(history_result)
                        preserved_count += 1
                        missing_metadata_count += 1
                        continue

                    # Validate metadata exists and is not empty with type checking
                    if not original_plugin_id or not original_item_id:
                        logger.debug(
                            f"History result '{getattr(history_result, 'name', 'unknown')}' missing original plugin metadata - preserving"
                        )
                        filtered_history_results.append(history_result)
                        preserved_count += 1
                        missing_metadata_count += 1
                        continue

                    # Ensure metadata values are strings
                    if not isinstance(original_plugin_id, str) or not isinstance(
                        original_item_id, str
                    ):
                        logger.warning(
                            f"History result '{getattr(history_result, 'name', 'unknown')}' has non-string metadata values - preserving"
                        )
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
                        logger.debug(
                            f"Preserving history result '{getattr(history_result, 'name', 'unknown')}' - no current match for {original_plugin_id}:{original_item_id}"
                        )
                    else:
                        # Found a matching result, but only deduplicate if the history entry
                        # represents the same user intent (similar input)
                        history_name = getattr(history_result, "name", "")
                        current_name = getattr(matching_result, "name", "")

                        # Only deduplicate if the history entry name is very similar to the current result
                        # This prevents removing "brave gmail.com" when "brave" app is found
                        if self.should_deduplicate_history_entry(
                            history_name, current_name
                        ):
                            deduplicated_count += 1
                            logger.debug(
                                f"Deduplicating history result '{history_name}' - too similar to current result '{current_name}' ({original_plugin_id}:{original_item_id})"
                            )
                        else:
                            filtered_history_results.append(history_result)
                            preserved_count += 1
                            logger.debug(
                                f"Preserving history result '{history_name}' - different intent from current result '{current_name}' ({original_plugin_id}:{original_item_id})"
                            )

                except AttributeError as e:
                    # Graceful error handling for missing attributes
                    logger.warning(f"AttributeError processing history result: {e}")
                    filtered_history_results.append(history_result)
                    preserved_count += 1
                    error_count += 1
                    continue
                except KeyError as e:
                    # Graceful error handling for missing dictionary keys
                    logger.warning(f"KeyError processing history result metadata: {e}")
                    filtered_history_results.append(history_result)
                    preserved_count += 1
                    error_count += 1
                    continue
                except Exception as e:
                    # Graceful error handling - preserve result if processing fails
                    logger.error(
                        f"Unexpected error processing history result '{getattr(history_result, 'name', 'unknown')}': {e}"
                    )
                    filtered_history_results.append(history_result)
                    preserved_count += 1
                    error_count += 1
                    continue

            # Return deduplicated list
            # Maintain original order: other results first, then filtered history results
            deduplicated_results = other_results + filtered_history_results
            original_count = len(results)
            final_count = len(deduplicated_results)

            # Comprehensive logging summary with error reporting
            logger.debug(
                f"Deduplication complete: {original_count} -> {final_count} results"
            )
            logger.debug(f"  - Deduplicated: {deduplicated_count} history results")
            logger.debug(f"  - Preserved: {preserved_count} history results")
            logger.debug(
                f"  - Missing metadata: {missing_metadata_count} history results"
            )

            if error_count > 0:
                logger.warning(
                    f"  - Errors encountered: {error_count} results had processing errors"
                )

            if invalid_results_count > 0:
                logger.warning(
                    f"  - Invalid results: {invalid_results_count} results skipped due to missing attributes"
                )

            if start_time and logger.isEnabledFor(logging.DEBUG):
                elapsed_time = time.time() - start_time
                logger.debug(f"Deduplication took {elapsed_time:.3f}s")

                # Performance warning for slow deduplication
                if elapsed_time > 0.1:  # More than 100ms
                    logger.warning(
                        f"Deduplication took longer than expected: {elapsed_time:.3f}s for {original_count} results"
                    )

            return deduplicated_results

        except MemoryError as e:
            # Handle memory errors specifically
            logger.error(
                f"Memory error during deduplication with {len(results)} results: {e}"
            )
            logger.warning("Skipping deduplication due to memory constraints")
            return results
        except Exception as e:
            # Graceful error handling - log error but don't break search functionality
            logger.error(f"Critical error during deduplication: {e}")
            logger.debug("Continuing with original results due to deduplication error")
            return results
