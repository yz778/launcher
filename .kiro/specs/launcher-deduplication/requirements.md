# Requirements Document

## Introduction

The launcher deduplication feature addresses the issue of duplicate search results appearing when the history plugin returns items that are identical to results from other active plugins. This creates a cleaner, more user-friendly search experience by eliminating redundant entries while preserving the valuable history functionality for items that are no longer available through their original plugins.

Additionally, the current system stores partial matches in history when only partial matches are found in results, which pollutes the history with incomplete entries that all resolve to the same target. The system should only store imperfect matches when command line arguments are provided that match a plugin base, in which case both the plugin base and arguments should be retained in history.

## Requirements

### Requirement 1

**User Story:** As a launcher user, I want to see each application or command only once in my search results, so that I can quickly find what I'm looking for without scrolling through duplicates.

#### Acceptance Criteria

1. WHEN a search query returns results from both history plugin and other plugins THEN the system SHALL remove history results that have exact matches from other plugins
2. WHEN a history result has metadata containing original_plugin_id and original_item_id THEN the system SHALL check if a matching (plugin_id, item_id) pair exists in current non-history results
3. WHEN an exact match is found between a history result and a non-history result THEN the system SHALL keep the non-history result and remove the history result
4. WHEN a history result has no exact match in current non-history results THEN the system SHALL keep the history result

### Requirement 2

**User Story:** As a launcher user, I want to still see historical items that are no longer available through their original plugins, so that I can access previously used commands or applications that may have been uninstalled or moved.

#### Acceptance Criteria

1. WHEN a history result has no corresponding match in current plugin results THEN the system SHALL preserve the history result in the final results list
2. WHEN a history result lacks original plugin metadata THEN the system SHALL preserve the history result to avoid data loss
3. WHEN only history results exist for a query THEN the system SHALL display all relevant history results without deduplication

### Requirement 3

**User Story:** As a launcher user, I want the deduplication process to be transparent and not affect search performance, so that my search experience remains fast and responsive.

#### Acceptance Criteria

1. WHEN deduplication is performed THEN the system SHALL complete the process without noticeable delay to the user
2. WHEN deduplication removes results THEN the system SHALL log debug information about which results were deduplicated
3. WHEN deduplication encounters errors THEN the system SHALL gracefully continue without breaking the search functionality
4. WHEN no deduplication is needed THEN the system SHALL skip the deduplication process efficiently

### Requirement 4

**User Story:** As a launcher user, I want the visual distinction between history and current results to be clear, so that I can understand the source and relevance of each result.

#### Acceptance Criteria

1. WHEN history results are displayed THEN the system SHALL use bold font weight for history text instead of italic styling
2. WHEN results are sorted THEN the system SHALL maintain proper score-based ordering after deduplication
3. WHEN deduplication is complete THEN the system SHALL preserve all result metadata and display properties

### Requirement 5

**User Story:** As a launcher user, I want only meaningful commands to be stored in history, so that my history remains clean and useful without partial matches cluttering the results.

#### Acceptance Criteria

1. WHEN only partial matches are found in search results THEN the system SHALL NOT store the partial match in history
2. WHEN a command is executed with command line arguments that match a plugin base THEN the system SHALL store both the plugin base and arguments in history
3. WHEN a full exact match is found and executed THEN the system SHALL store the complete match in history
4. WHEN storing history entries THEN the system SHALL include original plugin metadata (plugin_id, item_id) for future deduplication