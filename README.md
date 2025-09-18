# Launcher

A fast, extensible GTK launcher with intelligent search and highlighting.

## Features

- **Plugin Architecture**: Easily extend with new search sources
- **Core Plugins**:
  - **Commands Plugin**: Provides internal commands like `:exit` and `:theme`.
  - **Desktop File Plugin**: Launch applications from .desktop files
  - **Executable Plugin**: Launch executables from custom directories
  - **History Plugin**: Search through command execution history
  - **QCalculate Plugin**: Advanced calculator with Qalculate! engine
  - **Terminal Plugin**: Execute shell commands directly
  - **Timezone Plugin**: Convert time between different timezones
  - **Filesystem Plugin**: Search and launch files from the filesystem
- **Intelligent Search**: A scoring system that prioritizes results based on where a query matches (name vs. description) and the type of match (exact, prefix, substring, fuzzy).
- **Smart Highlighting**: Matched characters in results are highlighted.
- **History Tracking**: Learns from usage patterns to prioritize frequently used items
- **Customizable**: Configure through a simple JSON file.
- **Theming**:
  - Full CSS-based styling system.
  - Switch themes on the fly with the `:theme` command or --theme CLI command.
  - Live theme preview as you select different themes.
  - Comes with several built-in themes.

## Architecture

The launcher is built with a modular architecture designed for extensibility and performance.

### Internal Structure

- **Plugin System**: Extensible through plugins that provide search sources and functionality.
- **Services**: Core services include ConfigService for configuration management, ThemeService for theming, and IPCService for inter-process communication.
- **Bootstrap Process**: Handles initialization in phases including argument parsing, IPC checks, and service setup.

### Startup Process

The startup process involves several key steps:

1. **Argument Parsing**: Command-line arguments are parsed to determine configuration and actions.
2. **IPC Instance Checks**: Checks for existing instances to handle single-instance behavior.
3. **Bootstrap Phases**: Initializes services, loads plugins, and prepares the UI.

## Configuration

The launcher uses a layered configuration approach:

1.  **Default Configuration**: Built-in defaults are always applied first.
2.  **User Configuration**: Custom settings in `~/.config/launcher/config.json` override defaults.

Configuration is loaded recursively, so you only need to specify the values you want to change.

Example `~/.config/launcher/config.json`:

```json
{
  "system": {
    "max_results": 15,
    "icon_size": 48,
    "theme": "dracula"
  }
}
```

## Theming

The launcher supports a powerful CSS-based theming system.

### Switching Themes

You can switch themes in two ways:

1.  **Using the `:theme` command**:
    - Type `:theme` in the launcher to see a list of available themes.
    - Select a theme to preview it instantly.
    - Press `Enter` to apply the theme and save it to your configuration.
2.  **Using the command-line**:
    - Run `launcher --theme <theme_name>` to apply a theme to a running instance.

### Built-in Themes

The launcher includes a variety of pre-installed themes:

- `ayu-dark`
- `ayu-light`
- `catppuccin-frappe`
- `catppuccin-latte`
- `catppuccin-macchiato`
- `catppuccin-mocha`
- `cobalt2`
- `dark-blue`
- `dark-green`
- `dark-orange`
- `dark-purple`
- `dark-red`
- `dark-teal`
- `default`
- `dracula`
- `embark`
- `everforest`
- `github-dark`
- `github-light`
- `gruvbox-dark`
- `gruvbox-light`
- `light`
- `monokai`
- `night-owl`
- `nord`
- `one-dark-light`
- `one-dark-pro`
- `solarized-dark`
- `solarized-light`
- `tokyo-night-light`
- `tokyo-night`

Note: The full list of available themes can be viewed using the `:theme` command. Custom themes can override built-in themes by placing CSS files in `~/.config/launcher/themes/`.

### Creating Custom Themes

You can create your own themes by adding a CSS file to `~/.config/launcher/themes/`. The name of the file (without the `.css` extension) will be the name of your theme.

For example, to create a theme named `my-theme`, create the file `~/.config/launcher/themes/my-theme.css`.

The launcher uses semantic CSS variables, CSS IDs and classes for easy customization.

```css
/* Main window and entry */
#launcher-window { /* Main window styling */ }
#launcher-search { /* Search input field */ }

/* Results list */
#app-list-item { /* Individual result items */ }
#app-name { /* Result title text */ }
#app-description { /* Result description text */ }

/* Plugin-specific styles */
.desktop-file-result { /* Desktop application results */ }
.executable-result { /* Executable file results */ }
```

## Setup

```bash
make setup
```

## Usage

```bash
make run
```

You can also control a running instance from the command line:

```bash
# Show the launcher window
./launcher

# Change the theme
./launcher --theme nord
```

In addition to command-line arguments, the launcher supports control via socket (IPC) communication. This enables remote control of running instances for various commands, such as showing the launcher window or changing themes dynamically.

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
