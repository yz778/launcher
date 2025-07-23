# Requirements Document

## Introduction

The launcher window currently has inconsistent positioning behavior across different display systems (X11, Wayland, etc.). The window should consistently appear centered horizontally and at 25% vertical position (eye level) on the main display every time it's shown, regardless of the underlying display system.

## Requirements

### Requirement 1

**User Story:** As a user, I want the launcher window to consistently appear in the same position every time I open it, so that I have a predictable and comfortable user experience.

#### Acceptance Criteria

1. WHEN the launcher window is displayed THEN the system SHALL position it centered horizontally on the main display
2. WHEN the launcher window is displayed THEN the system SHALL position it at 25% from the top of the main display (eye level)
3. WHEN the launcher window is displayed on any platform (X11, Wayland, etc.) THEN the positioning SHALL be consistent
4. WHEN the launcher window is toggled multiple times THEN it SHALL always return to the same position

### Requirement 2

**User Story:** As a user, I want the launcher positioning to work reliably across different display systems, so that I don't experience different behavior on different Linux distributions or desktop environments.

#### Acceptance Criteria

1. WHEN running on X11 THEN the launcher SHALL position correctly using X11-specific methods
2. WHEN running on Wayland THEN the launcher SHALL position correctly using Wayland-compatible methods
3. WHEN running on any other display system THEN the launcher SHALL fall back to a reliable positioning method
4. IF platform-specific positioning fails THEN the system SHALL use a fallback positioning method

### Requirement 3

**User Story:** As a user, I want the positioning logic to be simple and reliable, so that there are fewer bugs and edge cases.

#### Acceptance Criteria

1. WHEN the window is displayed THEN the positioning check SHALL be performed every time
2. WHEN calculating position THEN the system SHALL use the main display dimensions
3. WHEN positioning fails THEN the system SHALL log the error and use a fallback method
4. WHEN the display configuration changes THEN the positioning SHALL adapt to the new configuration

### Requirement 4

**User Story:** As a developer, I want the positioning code to be maintainable and well-documented, so that future changes are easier to implement.

#### Acceptance Criteria

1. WHEN implementing positioning THEN the code SHALL be organized in dedicated methods
2. WHEN implementing positioning THEN each method SHALL have clear documentation
3. WHEN implementing positioning THEN error handling SHALL be comprehensive
4. WHEN implementing positioning THEN the logic SHALL be testable and modular