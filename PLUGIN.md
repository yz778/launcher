# Plugin Architecture for Launcher

## Overview

The launcher uses a sophisticated plugin-based architecture that separates search logic from presentation. Plugins focus purely on finding and executing items, while the UI layer handles all presentation concerns including highlighting, theming, and user interaction.

## Core Components

1. **Plugin Interface**: Abstract base classes defining the plugin contract
2. **Plugin Manager**: Dynamic loading, lifecycle management, and coordination
3. **Search Result**: Standardized data structure for all search results
4. **Text Highlighter**: UI-layer highlighting with multiple matching strategies
5. **CSS Integration**: Plugin-specific styling and extensible themes
6. **History Manager**: Usage tracking and intelligent result prioritization

## Plugin Interface

### Required Methods

Each plugin must inherit from `Plugin` and implement:

- `get_id()`: Return unique plugin identifier
- `get_name()`: Return human-readable plugin name  
- `get_description()`: Return plugin description
- `get_config_defaults()`: Return default configuration dictionary
- `initialize(config, config_manager)`: Set up plugin with configuration
- `search(query)`: Return list of `SearchResult` objects
- `execute(result)`: Execute the selected search result

### Optional Methods

- `get_default_css()`: Return CSS styles for this plugin
- `start()`: Perform heavy initialization after GUI startup
- `cleanup()`: Clean up resources when plugin is unloaded
- `should_track_history()`: Whether executions should be tracked
- `rescan()`: Refresh plugin data (for file-based plugins)

## Plugin Loading Process

1. The Plugin Manager scans the plugins directory
2. It loads each plugin module and instantiates the plugin class
3. Each plugin is initialized with its configuration
4. Plugins are registered for search queries

## Search Process

1. **User Input**: User types a query in the launcher
2. **Plugin Search**: Query is sent to all enabled plugins asynchronously
3. **Result Processing**: Each plugin returns `SearchResult` objects
4. **History Integration**: Results are scored and prioritized based on usage history
5. **UI Rendering**: Results are displayed with intelligent highlighting
6. **User Selection**: User selects a result for execution
7. **Plugin Execution**: The originating plugin executes the selected item
8. **History Update**: Successful executions are tracked for future prioritization

## Search Result Structure

```python
SearchResult(
    plugin_id="desktop_file",           # Plugin that provided this result
    item_id="/path/to/app.desktop",     # Unique identifier within plugin
    name="Calculator",                  # Display name (will be highlighted)
    description="Perform calculations", # Optional description
    icon=pixbuf_object,                # Optional GTK pixbuf icon
    score=85.5,                        # Match quality score (0-100)
    metadata={                         # Plugin-specific data
        "desktop_file": desktop_obj,
        "track_history": True
    }
)
```

## Highlighting and Presentation

### Separation of Concerns

Plugins should **NOT** handle highlighting or presentation logic. The UI layer automatically handles:

- **Text Highlighting**: Multiple matching strategies (exact, prefix, word, fuzzy)
- **Visual Styling**: CSS-based theming with plugin-specific classes
- **Icon Rendering**: Automatic scaling and fallback handling
- **Layout Management**: Consistent result item presentation

### Highlighting System

The launcher uses a sophisticated highlighting system:

1. **Multiple Match Types**: Exact, prefix, word boundary, and fuzzy matching
2. **CSS-Based Styling**: Each match type has its own CSS class
3. **Automatic Detection**: UI layer determines highlighting based on search query
4. **Extensible**: New match types can be added easily

```css
/* Highlighting CSS classes */
.highlight-exact { color: #8be9fd; font-weight: bold; }
.highlight-prefix { color: #8be9fd; font-weight: bold; }
.highlight-word { color: #50fa7b; font-weight: bold; }
.highlight-fuzzy { color: #ffb86c; font-weight: bold; font-style: italic; }
```

## Plugin Styling

### CSS Integration

Plugins can provide default CSS through `get_default_css()`:

```python
def get_default_css(self) -> str:
    return """
    /* Calculator Plugin CSS */
    .calculator-result #app-list-item {
        background: rgba(255, 183, 108, 0.1);
        border-left: 3px solid #ffb86c;
    }
    
    .calculator-result #app-name {
        color: #ffb86c;
        font-family: monospace;
    }
    """
```

### CSS Class Naming

Plugin results automatically get CSS classes:
- `.{plugin-id}-result` - Applied to the result container
- Standard element IDs: `#app-list-item`, `#app-name`, `#app-description`

## Configuration System

### Default Configuration

```python
def get_config_defaults(self) -> Dict[str, Any]:
    return {
        "enabled": True,
        "locations": ["~/custom/path"],
        "include_patterns": ["*.py", "*.sh"],
        "track_history": True,
        "custom_setting": "default_value"
    }
```

### Configuration Access

```python
def initialize(self, config: Dict[str, Any], config_manager) -> bool:
    super().initialize(config, config_manager)
    
    # Access plugin-specific config
    self.custom_setting = config.get("custom_setting", "default")
    
    # Access general config
    self.icon_size = self.get_general_config("icon_size", 48)
    
    return True
```

## Performance Best Practices

### Initialization vs. Startup

- **`initialize()`**: Light setup only (config, CSS)
- **`start()`**: Heavy operations (file scanning, data loading)

### Background Processing

```python
def start(self) -> bool:
    # Load data in background thread
    threading.Thread(target=self._scan_data, daemon=True).start()
    return True

def _scan_data(self):
    # Heavy processing here
    self._load_files()
    # Update UI on main thread
    GLib.idle_add(self._update_results)
```

### Caching

```python
def _load_from_cache(self):
    cache_file = os.path.join(
        self.config_manager.get_cache_dir(), 
        f"{self.get_id()}_cache.json"
    )
    # Load cached data for faster startup
```

## Adding New Plugins

1. **Create Plugin File**: `plugins/my_plugin.py`
2. **Inherit from Plugin**: `class MyPlugin(Plugin):`
3. **Implement Required Methods**: See interface above
4. **Add Configuration**: Define defaults and handle user config
5. **Add CSS Styling**: Provide default appearance
6. **Test Integration**: Ensure proper loading and execution

### Example Plugin Structure

```python
from plugins.base import Plugin, SearchResult
from typing import Dict, Any, List

class MyPlugin(Plugin):
    def get_id(self) -> str:
        return "my_plugin"
    
    def get_name(self) -> str:
        return "My Plugin"
    
    def get_description(self) -> str:
        return "Description of what this plugin does"
    
    def get_config_defaults(self) -> Dict[str, Any]:
        return {"enabled": True, "setting": "default"}
    
    def get_default_css(self) -> str:
        return """
        .my-plugin-result #app-name { color: #50fa7b; }
        """
    
    def initialize(self, config: Dict[str, Any], config_manager) -> bool:
        super().initialize(config, config_manager)
        # Setup logic here
        return True
    
    def start(self) -> bool:
        # Heavy initialization here
        return True
    
    def search(self, query: str) -> List[SearchResult]:
        # Search logic - return SearchResult objects
        results = []
        # ... search implementation
        return results
    
    def execute(self, result: SearchResult) -> bool:
        # Execution logic
        return True
```

The plugin system is designed to be simple for basic plugins while supporting advanced features like caching, background processing, and custom styling for more complex use cases.
