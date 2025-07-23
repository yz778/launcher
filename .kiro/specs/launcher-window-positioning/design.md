# Design Document

## Overview

This design addresses the launcher window positioning issues by implementing a robust, cross-platform positioning system that ensures consistent placement at the center horizontally and 25% vertically on the main display. The solution will replace the current unreliable `Gtk.WindowPosition.CENTER` approach with manual positioning calculations that work across X11, Wayland, and other display systems.

## Architecture

The positioning system will be implemented as a set of methods within the `LauncherWindow` class that handle:

1. **Display Detection**: Identify the current display system and main monitor
2. **Position Calculation**: Calculate the exact pixel coordinates for center horizontal and 25% vertical positioning
3. **Window Positioning**: Apply the calculated position using appropriate GTK methods
4. **Fallback Handling**: Provide reliable fallbacks when primary methods fail

## Components and Interfaces

### Core Components

#### 1. WindowPositioner Class
A dedicated class to handle all positioning logic:

```python
class WindowPositioner:
    def __init__(self, window: Gtk.Window):
        self.window = window
        self.logger = logging.getLogger(__name__)

    def position_window(self) -> bool:
        """Position window at center horizontal, 25% vertical"""

    def get_main_display_info(self) -> Dict[str, int]:
        """Get main display dimensions and position"""

    def calculate_position(self, display_info: Dict, window_size: Tuple[int, int]) -> Tuple[int, int]:
        """Calculate target window position"""

    def apply_position(self, x: int, y: int) -> bool:
        """Apply calculated position to window"""
```

#### 2. Display System Detection
Methods to detect and handle different display systems:

```python
def detect_display_system(self) -> str:
    """Detect current display system (x11, wayland, etc.)"""

def get_display_info_x11(self) -> Dict[str, int]:
    """Get display info using X11 methods"""

def get_display_info_wayland(self) -> Dict[str, int]:
    """Get display info using Wayland-compatible methods"""

def get_display_info_fallback(self) -> Dict[str, int]:
    """Fallback display info using GTK methods"""
```

#### 3. Integration Points
Modified methods in `LauncherWindow`:

```python
def show_and_focus(self):
    """Enhanced to always position window correctly"""

def _position_window_consistently(self):
    """New method to handle positioning every time window is shown"""
```

## Data Models

### Display Information Structure
```python
DisplayInfo = {
    'width': int,           # Display width in pixels
    'height': int,          # Display height in pixels
    'x': int,              # Display X offset (for multi-monitor)
    'y': int,              # Display Y offset (for multi-monitor)
    'scale_factor': float  # Display scaling factor
}
```

### Position Calculation
```python
# Target position calculation
target_x = display_x + (display_width - window_width) // 2  # Center horizontal
target_y = display_y + int(display_height * 0.25)          # 25% from top (eye level)
```

## Error Handling

### Error Scenarios and Responses

1. **Display Detection Failure**
   - Log warning and fall back to GTK default methods
   - Use `Gdk.Screen.get_default()` as last resort

2. **Position Calculation Failure**
   - Fall back to simple center positioning
   - Ensure window stays within screen bounds

3. **Window Positioning Failure**
   - Try alternative positioning methods
   - Log error but don't crash application

### Error Recovery Strategy
```python
def position_window_with_fallback(self):
    try:
        return self._position_window_precise()
    except Exception as e:
        self.logger.warning(f"Precise positioning failed: {e}")
        try:
            return self._position_window_gtk_fallback()
        except Exception as e2:
            self.logger.error(f"Fallback positioning failed: {e2}")
            return False
```

## Testing Strategy

### Unit Tests
1. **Display Detection Tests**
   - Mock different display systems
   - Test detection accuracy
   - Verify fallback behavior

2. **Position Calculation Tests**
   - Test various display sizes
   - Test multi-monitor scenarios
   - Verify 25% vertical positioning

3. **Integration Tests**
   - Test on different display systems
   - Test window positioning accuracy
   - Test fallback mechanisms

### Manual Testing
1. **Cross-Platform Testing**
   - Test on X11 systems
   - Test on Wayland systems
   - Test on different desktop environments

2. **Multi-Monitor Testing**
   - Test with single monitor
   - Test with multiple monitors
   - Test with different monitor arrangements

3. **Edge Case Testing**
   - Test with very small displays
   - Test with high DPI displays
   - Test with display scaling

## Implementation Approach

### Phase 1: Core Positioning Logic
1. Create `WindowPositioner` class
2. Implement display detection methods
3. Implement position calculation
4. Add comprehensive error handling

### Phase 2: Integration
1. Integrate with `LauncherWindow.show_and_focus()`
2. Remove old positioning code
3. Add logging and debugging support

### Phase 3: Testing and Refinement
1. Test across different platforms
2. Refine fallback mechanisms
3. Optimize performance
4. Add configuration options if needed

## Configuration Options

The positioning system will be configurable through the launcher config:

```json
{
  "general": {
    "window_position_vertical_percent": 25,
    "window_position_force_center": true,
    "window_position_debug": false
  }
}
```

## Performance Considerations

1. **Lazy Loading**: Display information will be cached and only recalculated when needed
2. **Minimal Overhead**: Positioning calculations are lightweight and fast
3. **Async Safety**: All positioning operations will be safe for GTK's main thread

## Security Considerations

1. **No External Dependencies**: Uses only GTK and standard Python libraries
2. **Safe Fallbacks**: All error conditions have safe fallback behaviors
3. **Input Validation**: All display dimensions and calculations are validated

## Backward Compatibility

The new positioning system will:
- Maintain the same external API
- Not break existing configuration options
- Provide better behavior than the current implementation
- Be fully backward compatible with existing launcher usage