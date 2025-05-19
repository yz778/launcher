# Plugin Architecture for Launcher

## Overview

The launcher uses a plugin-based architecture where different sources can
provide searchable items. This makes it easy to add new functionality without
modifying the core code.

## Core Components

1. **Plugin Interface**: Define a common interface that all plugins must
   implement
2. **Plugin Manager**: Load and manage plugins
3. **Search Result**: Common data structure for search results from any plugin
4. **Launcher Core**: Main application that coordinates plugins and UI

## Plugin Interface

Each plugin must implement:

- `get_id()`: Return the plugin ID
- `get_name()`: Return the plugin name
- `get_description()`: Return the plugin description
- `initialize(config)`: Set up the plugin with configuration
- `search(query)`: Search for items matching the query
- `execute(item)`: Execute the selected item

## Plugin Loading Process

1. The Plugin Manager scans the plugins directory
2. It loads each plugin module and instantiates the plugin class
3. Each plugin is initialized with its configuration
4. Plugins are registered for search queries

## Search Process

1. User enters a query in the launcher
2. Query is sent to all enabled plugins
3. Each plugin returns matching results
4. Results are combined, sorted by relevance, and displayed
5. User selects a result, which is executed by the corresponding plugin

## Adding New Plugins

To create a new plugin, create a Python file in the `plugins` directory that
implements the `Plugin` interface from `plugins.base`. See existing plugins for
examples.
