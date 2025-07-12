# AI Trading Agent Architecture

This document outlines the architecture of the AI Trading Agent. The architecture is designed for resilience, maintainability, and robustness, incorporating several key design patterns.

```mermaid
graph TD
    subgraph "Core Application"
        A[User starts main.py] --> B{Validate Config};
        B -- ✅ Valid --> C[Initialize Services];
        C --> D[Start Telegram Bot];
        D --> E((Trading Loop));
    end

    subgraph "Services & State"
        style "Services & State" fill:#f0f8ff,stroke:#333,stroke-width:1px
        S1[state.py]
        S2[errors.py]
        S3[circuit_breaker.py]
        S4[health_check.py]
        S5[logger.py]
        S6[validators.py]
    end
    
    C --> S1;
    C --> S2;
    C --> S3;
    C --> S4;
    C --> S5;
    C --> S6;

    subgraph "Main Trading Cycle"
        style "Main Trading Cycle" fill:#e6f3e6,stroke:#333,stroke-width:1px
        E --> F{Is Market Open?};
        F -- Yes --> G[Clear Daily Cache];
        G --> H[Phase 1: Manage Holdings];
        H --> I[Phase 2: Manage Watchlist];
        I --> J[Phase 3: Find Opportunities];
        J --> K[Log Portfolio Summary];
        K --> E;
        F -- No --> E;
    end

    subgraph "API Interaction with Circuit Breaker"
        style "API Interaction with Circuit Breaker" fill:#fff0f0,stroke:#333,stroke-width:1px
        API_CALL[Any function using @retry_api_call] --> CB{Circuit Breaker};
        CB -- Closed --> KITE[Kite API];
        KITE -- Success --> API_CALL;
        KITE -- Failure --> CB;
        CB -- Open --> EXC1[Throw CriticalTradingError];
    end

    subgraph "User Interaction"
        style "User Interaction" fill:#f5f5dc,stroke:#333,stroke-width:1px
        U[User] <-->|/start, /stop, /status| D;
        U -->|/health| HC[Health Check Command];
        HC --> S4;
        S4 -->|Checks| KITE;
        S4 -->|Checks| S1;
        S4 -->|Checks| S3;
        HC --> U;
    end
    
    subgraph "Shutdown"
        style "Shutdown" fill:#fafad2,stroke:#333,stroke-width:1px
        SIG[Signal (Ctrl+C)] --> E;
        E -->|asyncio.CancelledError| FIN[Finally Block in main];
        FIN --> CLEAN[Clean Shutdown];
    end

    H & I & J --> API_CALL;
```

## Key Architectural Concepts

- **Centralized State Management (`state.py`):** To avoid circular dependencies and make the application easier to reason about, all shared, mutable state (like the portfolio, caches, and agent running status) is stored in a single `state.py` module. This provides a single source of truth.

- **Custom Error Classification (`errors.py`):** The agent uses a hierarchy of custom exceptions (`TradingError`, `CriticalTradingError`, `MinorTradingError`). This allows the main trading loop to handle different types of errors intelligently, retrying minor issues while shutting down safely on critical failures.

- **Circuit Breaker (`circuit_breaker.py`):** All calls to the external Kite API are wrapped in a Circuit Breaker pattern. If the API starts failing repeatedly, the circuit "opens," and the agent stops trying to make calls for a configured cool-down period. This prevents the agent from spamming a failing service and allows it to recover gracefully.

- **Proactive Health Checks (`health_check.py`):** A comprehensive health check system, triggered by the `/health` Telegram command, allows for real-time diagnostics of the agent. It checks API connectivity, memory usage, cache status, and the state of the circuit breaker, providing a complete operational overview.

- **Asynchronous Operations (`utils.py`):** The `AsyncKiteClient` class acts as an adapter, allowing the asynchronous `asyncio` event loop to communicate safely with the synchronous Kite Connect library via a dedicated worker thread. This prevents blocking calls from freezing the entire application.

- **Graceful Shutdown:** The application is designed to catch system shutdown signals (like `Ctrl+C`). This is handled by the `asyncio` event loop, which raises a `CancelledError` to allow the main trading loop to exit cleanly and perform any necessary cleanup.

