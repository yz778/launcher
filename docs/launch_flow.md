# Launcher Call Flow Diagram

```mermaid
flowchart TD
    A[Application Entry<br/>launcher/__main__.py] --> B[main from main.py]
    B --> C[Parse Command Line Arguments]
    C --> D{Args count == 1<br/>or --theme flag?}

    D -->|Yes| E[Check for Running Instance<br/>IPCManager.send_command]
    E --> F{IPC Send Successful?}
    F -->|Yes| G[Print Success Message<br/>exit]
    F -->|No| H[Continue Normal Startup]

    D -->|No| H
    H --> I{--create-config flag?}
    I -->|Yes| J[Create Default Config<br/>ConfigManager.create_default_config<br/>exit]
    I -->|No| K{--theme flag?}
    K -->|Yes| L[Show Available Themes<br/>CssManager.get_available_themes<br/>exit]
    K -->|No| M[Set Signal Handlers<br/>SIGTERM, SIGINT]
    M --> N[Change to Home Directory<br/>os.chdir'~']

    subgraph "Bootstrap Phase"
        N --> O[Bootstrapper.bootstrap]
        O --> P[Phase 1: Core Services<br/>ConfigManager<br/>ConfigService]
        P --> Q[Phase 2: Infrastructure Services<br/>CssManager<br/>ThemeService<br/>IPCManager if not foreground]
        Q --> R[Phase 3: Business Services<br/>HistoryManager<br/>PluginManager.load_plugins<br/>Update Theme]
        R --> S[Phase 4: Background Processes<br/>Start IPC Server<br/>Start Plugins threads<br/>Schedule History Cleanup]
    end

    S --> T[Register IPC Handlers<br/>SHOW, THEME if not foreground]
    T --> U[Create LauncherApplication]
    U --> V[LauncherApplication.run]

    subgraph "Application Startup"
        V --> W[do_startup<br/>Setup CSS Manager<br/>Setup Actions]
        W --> X[do_activate<br/>Create LauncherWindow<br/>Add Window to App<br/>Start Window]
    end

    subgraph "Window Startup"
        X --> Y[LauncherWindow.start<br/>Connect Signals<br/>Show Recent History<br/>Focus Entry]
    end

    Y --> Z[Application Ready<br/>Waiting for User Input]

    style A fill:#e1f5fe
    style O fill:#f3e5f5
    style V fill:#e8f5e8
    style Y fill:#fff3e0