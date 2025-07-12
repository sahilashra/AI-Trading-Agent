# AI Trading Agent Architecture

This document outlines the architecture and workflow of the AI Trading Agent. The following diagram is rendered using Mermaid and reflects the enhanced reliability and risk management features.

```mermaid
graph TD
    subgraph "Initialization"
        A[User starts main.py] --> B{Validate API Keys};
        B -- ✅ Valid --> C[Initialize Gemini API];
        C --> D[Initialize KiteConnect];
        D --> E[Reconcile Portfolio from Broker];
        E --> F[Start Telegram Bot & Webhook];
    end

    F --> G((Trading Loop));

    subgraph "Main Trading Cycle (Repeats every 5 mins)"
        style "Main Trading Cycle (Repeats every 5 mins)" fill:#f0f8ff,stroke:#333,stroke-width:1px
        G --> H{Is Market Open?};
        H -- Yes --> I{Clear Daily Cache (if new day)};
        I --> J{Monitor Pending Orders (Live Only)};
        J --> K[Phase 1: Manage Holdings];
        K --> L[Phase 2: Manage Watchlist];
        L --> M[Phase 3: Find New Opportunities];
        M --> N[Log Portfolio Summary];
        N --> G;
        H -- No --> G;
    end

    subgraph "Data Flow with Caching"
        style "Data Flow with Caching" fill:#e6f3e6,stroke:#333,stroke-width:1px
        DF1[Analysis Functions] --> C1{Check Cache for Data};
        C1 -- HIT --> DF1;
        C1 -- MISS --> API(Kite API);
        API -- Fetched Data --> C2[Update Cache];
        C2 --> DF1;
    end

    subgraph "Phase 1: Manage Holdings"
        style "Phase 1: Manage Holdings" fill:#fff0f0,stroke:#333,stroke-width:1px
        K --> K1{For each stock in portfolio};
        K1 --> DF1;
        DF1 -- Data --> K2{Check Sell Conditions? (RSI, SL, etc.)};
        K2 -- Yes --> K3[Place SELL Order];
        K3 --> P([Pending Orders]);
        K2 -- No --> K1;
    end
    
    subgraph "Phase 2: Manage Watchlist"
        style "Phase 2: Manage Watchlist" fill:#f5f5dc,stroke:#333,stroke-width:1px
        L --> L1{For each stock in watchlist};
        L1 --> DF1;
        DF1 -- Data --> L2{Price > Confirmation?};
        L2 -- Yes --> L3[Perform Pre-Trade Risk Checks];
        L3 -- ✅ Safe --> L4[Place BUY Order];
        L4 --> P;
        L3 -- ❌ Unsafe --> L1;
        L2 -- No --> L1;
    end

    subgraph "Phase 3: Find Opportunities"
        style "Phase 3: Find Opportunities" fill:#e0ffff,stroke:#333,stroke-width:1px
        M --> M1[Screen for Momentum Pullbacks];
        M1 --> DF1;
        DF1 -- Data --> M2{For each candidate stock};
        M2 --> M3[Analyze with Gemini AI];
        M3 --> GAPI[Gemini API];
        M3 --> M4{Decision == 'BUY'?};
        M4 -- Yes --> M5[Add to Watchlist];
        M4 -- No --> M2;
    end

    subgraph "Order Execution (Live Mode)"
        style "Order Execution (Live Mode)" fill:#fafad2,stroke:#333,stroke-width:1px
        J --> P;
        P --> J1_Monitor{Check Order Status};
        J1_Monitor --> API;
        API -- Order Data --> J2_Check{Status == 'COMPLETE' ?};
        J2_Check -- Yes --> J3_Update[Update Portfolio & Cash];
        J3_Update --> J;
        J2_Check -- No --> J;
    end

    subgraph "External Services & User"
        U[User] <-->|/start, /stop, /status| F;
    end

```
