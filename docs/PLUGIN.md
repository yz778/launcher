# Plugin Architecture for Launcher

## Overview

The launcher uses a sophisticated plugin-based architecture that separates search logic from presentation. Plugins focus purely on finding and executing items, while the UI layer handles all presentation concerns including highlighting, theming, and user interaction.

## Plugin Directory Structure

Each plugin is organized in its own directory with a standardized structure:

```
launcher/plugins/
├── base.py                    # Base plugin classes and interfaces
├── my_plugin/                 # Individual plugin directory
│   ├── plugin.py             # Main plugin implementation (required)
│   ├── config.yaml           # Plugin-specific configuration (optional)
│   ├── assets/               # Plugin assets like icons (optional)
│   └── helpers/              # Additional helper modules (optional)
└── another_plugin/
    └── plugin.py
```

### Key Requirements:
- Each plugin must be in its own directory under `launcher/plugins/`
- The main plugin class must be in a file named `plugin.py`
- The plugin class must inherit from the `Plugin` base class
- Plugin directories can contain additional files and subdirectories as needed

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

```python
from ..base import Plugin, SearchResult
from typing import Dict, Any, List

class MyPlugin(Plugin):
    def get_id(self) -> str:
        """Return unique plugin identifier"""

    def get_name(self) -> str:
        """Return human-readable plugin name"""

    def get_description(self) -> str:
        """Return plugin description"""

    def get_config_defaults(self) -> Dict[str, Any]:
        """Return default configuration values"""

    def search(self, query: str) -> List[SearchResult]:
        """Search for items matching the query"""

    def execute(self, result: SearchResult) -> bool:
        """Execute the given search result"""
```

### Optional Methods

```python
def get_default_css(self) -> str:
    """Return default CSS styling for this plugin"""
    return ""

def initialize(self, config: Dict[str, Any], config_manager) -> bool:
    """Initialize plugin with configuration"""
    super().initialize(config, config_manager)
    return True

def start(self) -> bool:
    """Perform heavy initialization after GUI startup"""
    return True

def cleanup(self) -> None:
    """Clean up resources when plugin is unloaded"""
    pass

def should_track_history(self) -> bool:
    """Whether executions should be tracked in history"""
    return True
```

## Search Results

All search results must be `SearchResult` objects:

```python
result = SearchResult(
    plugin_id=self.get_id(),
    item_id="unique_item_id",
    name="Display Name",
    description="Optional description",
    icon=icon_pixbuf,  # Optional GTK icon
    score=85.0,        # Match score (0-100)
    metadata={"key": "value"}  # Plugin-specific data
)
```

### Highlighting System

The UI automatically highlights search matches in result names and descriptions. Plugins don't need to handle highlighting - just return clean text and the UI will apply appropriate highlighting based on the search query.

Available highlight classes:
- `.highlight-exact` - Exact substring matches
- `.highlight-prefix` - Prefix matches
- `.highlight-word` - Word boundary matches
- `.highlight-fuzzy` - Fuzzy character matches

## CSS Integration

### Plugin-Specific Styling


Each plugin can provide default CSS through `get_default_css()`. By default, this method will automatically load the contents of a file named `default.css` from the plugin's directory if it exists. You can override this method to return a CSS string directly if you prefer.

```python
def get_default_css(self) -> str:
    # By default, this loads 'default.css' from the plugin's directory if present
    return super().get_default_css()

# Or override to return a CSS string directly:
def get_default_css(self) -> str:
    return """
    .my-plugin-result #app-list-item {
        padding: 8px;
        border-radius: 8px;
    }
    .my-plugin-result #app-name {
        color: #50fa7b;
        font-weight: bold;
    }
    .my-plugin-result #app-description {
        color: #6272a4;
        font-size: 12px;
    }
    """
```

### CSS Class Naming

Use the pattern `.{plugin-id}-result` for plugin-specific styling:
- Calculator: `.calculator-result`
- Terminal: `.terminal-result`
- Desktop Files: `.desktop-file-result`

## Configuration

### Plugin Configuration

Plugins receive configuration through the `initialize()` method:

```python
def get_config_defaults(self) -> Dict[str, Any]:
    return {
        "enabled": True,
        "max_results": 10,
        "custom_setting": "default_value"
    }

def initialize(self, config: Dict[str, Any], config_manager) -> bool:
    super().initialize(config, config_manager)
    self.max_results = config.get("max_results", 10)
    return True
```

### Accessing General Configuration

```python
# Get general launcher configuration
terminal_cmd = self.get_general_config("terminal_command", "gnome-terminal -- ")
icon_size = self.get_general_config("icon_size", 32)
```

## Creating a New Plugin

### Step 1: Create Plugin Directory
```bash
mkdir launcher/plugins/my_plugin
```

### Step 2: Create plugin.py
Create `launcher/plugins/my_plugin/plugin.py`:

```python
from ..base import Plugin, SearchResult
from typing import Dict, Any, List

class MyPlugin(Plugin):
    def get_id(self) -> str:
        return "my_plugin"

    def get_name(self) -> str:
        return "My Plugin"

    def get_description(self) -> str:
        return "Description of what this plugin does"

    def get_config_defaults(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "setting": "default_value"
        }

    def get_default_css(self) -> str:
        return """
        .my-plugin-result #app-name {
            color: #50fa7b;
            font-weight: bold;
        }
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
        if query.lower() in "my plugin":
            results.append(SearchResult(
                plugin_id=self.get_id(),
                item_id="example",
                name="Example Result",
                description="This is an example result",
                score=90.0
            ))
        return results

    def execute(self, result: SearchResult) -> bool:
        # Execution logic
        print(f"Executing: {result.name}")
        return True
```

### Step 3: Test Your Plugin

The plugin will be automatically discovered and loaded when the launcher starts. No registration or import statements needed.

## Plugin Discovery

The plugin manager automatically discovers plugins by:

1. Scanning `launcher/plugins/` for subdirectories
2. Looking for `plugin.py` files in each subdirectory
3. Importing and registering any `Plugin` subclasses found
4. Initializing enabled plugins with their configuration

This structure supports:
- **External plugin directories**: Future support for loading plugins from user directories
- **Plugin packages**: Each plugin can be a complete Python package
- **Asset management**: Plugins can include their own resources and files
- **Modular development**: Clean separation between plugins

## Best Practices

1. **Keep plugins focused**: Each plugin should have a single, clear purpose
2. **Handle errors gracefully**: Always return empty results rather than crashing
3. **Optimize search performance**: Cache data when possible, avoid blocking operations
4. **Use meaningful scores**: Higher scores (closer to 100) for better matches
5. **Provide good descriptions**: Help users understand what each result does
6. **Follow naming conventions**: Use consistent CSS class naming
7. **Test thoroughly**: Ensure your plugin works with various search queries

The plugin system is designed to be simple for basic plugins while supporting advanced features like caching, background processing, and custom styling for more complex use cases.