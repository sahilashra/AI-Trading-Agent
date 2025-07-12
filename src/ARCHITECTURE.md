# AI Trading Agent Architecture

This document outlines the architecture and workflow of the AI Trading Agent. The following diagram is rendered using Mermaid.

```mermaid
graph TD
    subgraph "Initialization"
        A[User starts main.py] --> B{Load Environment};
        B --> C{Validate API Keys};
        C -- ✅ Valid --> D[Initialize KiteConnect];
        C -- ✅ Valid --> E[Initialize Gemini API];
        D & E --> F[Reconcile Portfolio from Broker];
        F --> G[Start Telegram Bot & Webhook];
    end

    G --> H((Trading Loop));

    subgraph "Main Trading Cycle (Repeats every 5 mins)"
        style "Main Trading Cycle (Repeats every 5 mins)" fill:#f0f8ff,stroke:#333,stroke-width:1px
        H --> I{Is Market Open?};
        I -- Yes --> M{Monitor Pending Orders (Live Only)};
        M --> J[Phase 1: Manage Holdings];
        J --> K[Phase 2: Manage Watchlist];
        K --> L[Phase 3: Find New Opportunities];
        L --> H;
        I -- No --> H;
    end

    subgraph "Data Flow with Caching"
        style "Data Flow with Caching" fill:#e6f3e6,stroke:#333,stroke-width:1px
        J1[Analysis Functions] --> C1{Check Cache for Data};
        C1 -- HIT --> J1;
        C1 -- MISS --> X[Kite API];
        X --> C2[Update Cache];
        C2 --> J1;
    end

    subgraph "Phase 1: Manage Holdings"
        style "Phase 1: Manage Holdings" fill:#fff0f0,stroke:#333,stroke-width:1px
        J --> J2{For each stock in portfolio};
        J2 --> J1;
        J1 -- Data --> J3{Check Sell Conditions? (RSI > 75, SL, etc.)};
        J3 -- Yes --> J4[Place SELL Order];
        J4 --> P([Pending Orders]);
        J3 -- No --> J2;
    end
    
    subgraph "Phase 2: Manage Watchlist"
        style "Phase 2: Manage Watchlist" fill:#f5f5dc,stroke:#333,stroke-width:1px
        K --> K1{For each stock in watchlist};
        K1 --> J1;
        J1 -- Data --> K2{Price > Confirmation?};
        K2 -- Yes --> K3[Place BUY Order];
        K3 --> P;
        K2 -- No --> K1;
    end

    subgraph "Phase 3: Find Opportunities"
        style "Phase 3: Find Opportunities" fill:#e0ffff,stroke:#333,stroke-width:1px
        L --> L1[Screen for Momentum Pullbacks];
        L1 --> J1;
        J1 -- Data --> L2{For each candidate stock};
        L2 --> L3[Analyze with Gemini AI];
        L3 --> Y[Gemini API];
        L3 --> L4{Decision == 'BUY'?};
        L4 -- Yes --> L5[Add to Watchlist];
        L4 -- No --> L2;
    end

    subgraph "Order Execution (Live Mode)"
        style "Order Execution (Live Mode)" fill:#fafad2,stroke:#333,stroke-width:1px
        M --> P;
        P --> M1{Check Order Status};
        M1 --> X;
        X -- Order Data --> M2{Status == 'COMPLETE' ?};
        M2 -- Yes --> M3[Update Portfolio & Cash];
        M3 --> M;
        M2 -- No --> M;
    end

    subgraph "External Services & User"
        U[User] <-->|/start, /stop, /status| G;
    end

```
