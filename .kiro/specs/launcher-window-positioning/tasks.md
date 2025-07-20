# Implementation Plan

- [x] 1. Create WindowPositioner class with core positioning logic
  - Create new WindowPositioner class in launcher_window.py
  - Implement display system detection methods
  - Implement position calculation for center horizontal and 25% vertical
  - Add comprehensive error handling and logging
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 3.3, 4.1, 4.3_

- [x] 2. Implement display information gathering methods
  - Create method to detect current display system (X11, Wayland, etc.)
  - Implement X11-specific display info gathering
  - Implement Wayland-compatible display info gathering
  - Implement fallback display info using GTK methods
  - Add proper error handling for each method
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.3_

- [x] 3. Implement position calculation and application logic
  - Create method to calculate exact pixel coordinates for positioning
  - Implement window positioning using GTK move() method
  - Add bounds checking to ensure window stays on screen
  - Implement fallback positioning strategies
  - _Requirements: 1.1, 1.2, 3.1, 3.2, 3.3_

- [x] 4. Integrate positioning system with LauncherWindow
  - Modify show_and_focus() method to use new positioning system
  - Remove old Gtk.WindowPosition.CENTER usage
  - Add _position_window_consistently() method
  - Ensure positioning happens every time window is displayed
  - _Requirements: 1.4, 3.1, 4.2_

- [x] 5. Add configuration support for positioning behavior
  - Add configuration options for vertical position percentage
  - Add debug mode configuration option
  - Implement configuration loading in WindowPositioner
  - Add validation for configuration values
  - _Requirements: 3.2, 4.1, 4.2_

- [x] 6. Implement comprehensive error handling and fallbacks
  - Add try-catch blocks around all positioning operations
  - Implement graceful degradation when positioning fails
  - Add detailed logging for debugging positioning issues
  - Ensure application never crashes due to positioning failures
  - _Requirements: 2.4, 3.3, 4.3_

- [x] 7. Create unit tests for positioning logic
  - Write tests for display system detection
  - Write tests for position calculation with various display sizes
  - Write tests for error handling and fallback behavior
  - Write tests for configuration loading and validation
  - _Requirements: 4.4_

- [x] 8. Test positioning across different display systems
  - Test positioning behavior on X11 systems
  - Test positioning behavior on Wayland systems
  - Test multi-monitor scenarios
  - Verify consistent 25% vertical positioning across platforms
  - _Requirements: 1.3, 2.1, 2.2, 2.3_