# Launcher

A fast, extensible GTK launcher with intelligent search and highlighting.

## Features

- **Plugin Architecture**: Easily extend with new search sources
- **Core Plugins**:
  - **Calculator Plugin**: Evaluate mathematical expressions with SymPy
  - **Desktop File Plugin**: Launch applications from .desktop files
  - **Executable Plugin**: Launch executables from custom directories
  - **QCalculate Plugin**: Advanced calculator with Qalculate! engine
  - **Terminal Plugin**: Execute shell commands directly
- **Intelligent Search**: Multiple matching strategies (exact, prefix, word boundary, fuzzy)
- **Smart Highlighting**: Visual feedback with different styles for different match types
- **History Tracking**: Learns from usage patterns to prioritize frequently used items
- **Customizable**: Configure through YAML configuration file
- **Theming**: Full CSS-based styling system with extensible highlight styles

## Configuration

The launcher uses a layered configuration approach:

1. **Default Configuration**: Built-in defaults are always applied first
2. **User Configuration**: Custom settings in `~/.config/launcher/config.yaml`
   override defaults

Configuration is loaded recursively, so you only need to specify the values you
want to change.

Example configuration:

```yaml
general:
   max_results: 15
   icon_size: 32
plugins:
   calculator:
      precision: 5
```

## Styling

The launcher supports comprehensive CSS-based theming:

1. **Default Styling**: Built-in CSS provides a complete dark theme
2. **Plugin Styles**: Each plugin can contribute its own CSS styles
3. **Custom CSS**: User CSS file overrides defaults and plugin styles
4. **Highlight Styles**: Configurable highlighting for different match types

### CSS Structure

The launcher uses semantic CSS classes for easy customization:

```css
/* Main window and entry */
#launcher-window { /* Main window styling */ }
#launcher-entry { /* Search input field */ }

/* Results list */
#app-list-item { /* Individual result items */ }
#app-name { /* Result title text */ }
#app-description { /* Result description text */ }

/* Plugin-specific styles */
.desktop-file-result { /* Desktop application results */ }
.executable-result { /* Executable file results */ }
.calculator-result { /* Calculator results */ }
.terminal-result { /* Terminal command results */ }

/* Search highlighting */
.highlight-exact { /* Exact substring matches */ }
.highlight-prefix { /* Prefix matches */ }
.highlight-word { /* Word boundary matches */ }
.highlight-fuzzy { /* Fuzzy character matches */ }
```

### Custom Highlighting

Customize search result highlighting by overriding CSS classes:

```css
/* Custom highlighting styles */
.highlight-exact {
    color: #ff6b6b;        /* Red for exact matches */
    font-weight: bold;
}

.highlight-fuzzy {
    color: #4ecdc4;        /* Teal for fuzzy matches */
    font-weight: bold;
    font-style: italic;
    text-decoration: underline;
}

.highlight-word {
    color: #45b7d1;        /* Blue for word matches */
    background-color: rgba(69, 183, 209, 0.2);
}
```

### Example Custom CSS

```css
/* Dark blue theme variant */
#launcher-window {
    background: #1e2030;
    border-color: #4a5568;
}

#launcher-entry {
    color: #e2e8f0;
    font-size: 18px;
}

.desktop-file-result #app-list-item:selected {
    background-color: rgba(66, 153, 225, 0.6);
}
```

### Setup

```bash
./setup.sh
```

## Usage

```bash
./launcher.sh [-h]
```

### Keyboard Shortcuts

- **Type** to search with intelligent matching
- **Up/Down** to navigate results
- **Enter** to launch the selected result
- **Shift+Enter** to launch the selected result in terminal window
- **Tab** to autocomplete with the selected result
- **Escape** to clear or exit
- **F5** or **Ctrl+R** to rescan plugins
- **Ctrl+Q** to quit
- **Shift+Delete** to remove selected history items (single or multiple)

### Search Features

- **Exact Matching**: Direct substring search
- **Prefix Matching**: Matches at the beginning of words
- **Word Boundary Matching**: Matches complete words
- **Fuzzy Matching**: Character-by-character approximate matching
- **History Integration**: Frequently used items appear first
- **Visual Highlighting**: Different colors for different match types

## License

MIT
