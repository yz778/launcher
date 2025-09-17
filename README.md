# Launcher

A fast, extensible GTK launcher with intelligent search and highlighting.

## Features

- **Plugin Architecture**: Easily extend with new search sources
- **Core Plugins**:
  - **Commands Plugin**: Provides internal commands for the launcher.
  - **Desktop File Plugin**: Launch applications from .desktop files
  - **Executable Plugin**: Launch executables from custom directories
  - **History Plugin**: Search through command execution history
  - **QCalculate Plugin**: Advanced calculator with Qalculate! engine
  - **Terminal Plugin**: Execute shell commands directly
  - **Timezone Plugin**: Convert time between different timezones
- **Intelligent Search**: A scoring system that prioritizes results based on where a query matches (name vs. description) and the type of match (exact, prefix, substring, fuzzy).
- **Smart Highlighting**: Matched characters in results are highlighted. The color and style of the highlight is configurable.
- **History Tracking**: Learns from usage patterns to prioritize frequently used items
- **Customizable**: Configure through JSON configuration file
- **Theming**: Full CSS-based styling system.

## Configuration

The launcher uses a layered configuration approach:

1. **Default Configuration**: Built-in defaults are always applied first
2. **User Configuration**: Custom settings in `~/.config/launcher/config.json`
   override defaults

Configuration is loaded recursively, so you only need to specify the values you
want to change.

Example configuration:

```json
{
  "system": {
    "max_results": 15,
    "icon_size": 48,
    "highlight_color": "#ff6b6b",
    "highlight_weight": "bold"
  }
}
```

## Styling

The launcher supports comprehensive CSS-based theming:

1. **Default Styling**: Built-in CSS provides a complete dark theme
2. **Plugin Styles**: Each plugin can contribute its own CSS styles
3. **Custom CSS**: User CSS file overrides defaults and plugin styles

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
```

### Custom Highlighting

Customize search result highlighting by adding the following to your configuration file:
`~/.config/launcher/config.json`:

```json
{
  "system": {
    "highlight_color": "#4ecdc4",
    "highlight_weight": "bold"
  }
}
```
The `highlight_weight` property accepts any valid Pango font weight (e.g., `normal`, `bold`, `700`).

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

## Setup

```bash
make setup
```

## Usage

```bash
make run
```

### Keyboard Shortcuts

- **Type** to search
- **Up/Down** to navigate results
- **Enter** to launch the selected result
- **Shift+Enter** can modify the behavior of some plugins (e.g., running an executable without a terminal)
- **Tab** to autocomplete with the selected result
- **Escape** to clear or exit
- **Ctrl+Q** to quit
- **Shift+Delete** to remove selected history items (single or multiple)

### Search Features

- **Scoring System**: Results are scored and sorted based on a number of factors, including exact matches, prefix matches, and substring matches. Matches in the name of a result are prioritized over matches in the description.
- **History Integration**: Frequently used items appear first
- **Visual Highlighting**: Matched characters are highlighted to provide visual feedback.

## License

MIT
