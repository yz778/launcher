# Launcher

A customizable launcher with plugins for desktop files, executables, and
calculator.

## Features

- **Plugin Architecture**: Easily extend with new plugins
- **Core Plugins**:
  - **Calculator Plugin**: Evaluate mathematical expressions
  - **Desktop File Plugin**: Launch applications from .desktop files
  - **Executable Plugin**: Launch executables from custom search path
- **Customizable**: Configure through YAML configuration file
- **Theming**: Customizable styling through CSS

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

The launcher supports custom styling through CSS:

1. **Default Styling**: Built-in CSS is always applied first
2. **Custom CSS**: If available, custom CSS from is applied on top of defaults

This allows you to override specific styles while inheriting the rest from the
default theme.

Example custom CSS:

```css
/* Change only the entry field background */
#launcher-entry {
   background: rgba(30, 30, 30, 0.98);
   border-color: #3498db;
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

- **Type** to search
- **Up/Down** to navigate results
- **Enter** to launch the selected result
- **Shift+Enter** to launch the selected result in terminal window
- **Tab** to autocomplete with the selected result
- **Escape** to clear or exit

## License

MIT
