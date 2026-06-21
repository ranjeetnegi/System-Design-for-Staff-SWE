# Chapter 61k: Stock / Trading Feed — Market Data at Low Latency

> The New York Stock Exchange processes 8 billion messages per day.
> A stock price update that arrives 1 millisecond late can cost a trading
> firm millions of dollars. This is the system design problem where
> latency is measured in microseconds, not milliseconds.

---

```
+------------------------------------------------------------------+
|  INTERVIEW OVERVIEW — Stock Trading Feed                         |
|  Time: 45 minutes                                                |
|                                                                  |
|  Min 0-2:   Clarify scope (retail app? exchange? HFT?)          |
|  Min 2-8:   Users and use cases                                 |
|  Min 8-14:  Functional + Non-functional requirements            |
|  Min 14-19: Scale math                                           |
|  Min 19-23: Assumptions                                          |
|  Min 23-42: Architecture + deep dives                           |
|  Min 42-45: Failure modes, extensions                           |
|                                                                  |
|  The clarifying question that changes everything:                |
|  "Is this a retail trading app (Robinhood), a prime broker      |
|   system (Bloomberg terminal), or an exchange matching engine    |
|   (NYSE/NASDAQ)?" These are three completely different systems. |
|   For L5: retail app. For L6: can discuss the matching engine.  |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|  L5 vs L6 AT A GLANCE                                           |
|                                                                  |
|  L5 (Senior SWE):                                               |
|  - Market data pipeline: exchange feed -> Kafka -> Redis ->     |
|    WebSocket to users                                           |
|  - Order placement: validate -> debit -> route to exchange      |
|  - Real-time P&L: portfolio * Redis prices                      |
|  - Strong consistency for orders, eventual for price display    |
|  - Order status: async fills via callback, Kafka events         |
|                                                                  |
|  L6 (Staff):                                                     |
|  - Order book data structure (sorted list + price-time priority)|
|  - Matching engine design (the exchange-side problem)           |
|  - Feed handler: UDP multicast, FIX/FAST protocol parsing       |
|  - Co-location and kernel bypass networking (HFT context)       |
|  - Regulatory compliance: SEC Rule 605, MiFID II reporting      |
+------------------------------------------------------------------+
```

---

## Why This Chapter Matters

Stock trading system design is asked at Bloomberg, Jane Street, Citadel, Two Sigma, Robinhood, Coinbase, and increasingly at big tech companies building financial products (Apple Pay, Google Pay, Stripe, PayPal). The question tests low-latency architecture thinking: where latency budgets in web systems are measured in hundreds of milliseconds, financial systems measure in microseconds. Many concepts transfer to other low-latency pub/sub systems (gaming updates, IoT telemetry, real-time analytics).

The critical clarification: there are three distinct systems that all get called "stock trading":
1. **Retail trading app (Robinhood):** Consumer-facing. Displays prices, accepts orders. L5 scope.
2. **Prime broker / institutional terminal (Bloomberg):** Professional traders, high data volume, advanced analytics. L6 scope.
3. **Exchange matching engine (NYSE/NASDAQ):** The core of the market itself. Processes all orders, matches buyers with sellers, produces the price feed that everyone consumes. L6/Staff scope.

This chapter covers the retail trading app architecture — the most common L5 interview context. The matching engine is explained in the deep concepts section for L6 depth.

---

## Phase 1: Users and Use Cases (Minutes 2-8)

### Clarify first

1. "Retail app (Robinhood) or an exchange-level system?" For L5: retail app.
2. "Real-time prices or delayed (15-minute delay)?" Real-time requires WebSocket push; delayed is much simpler.
3. "Order types: just market orders, or also limit, stop-loss, options?" More order types = more state machines.
4. "Crypto or equities?" Crypto exchanges run 24/7; stock exchanges have market hours (9:30am-4pm ET). This changes the load profile significantly.

For this chapter: retail equities trading app, real-time prices (< 100ms), market and limit orders, US equity markets (NYSE/NASDAQ).

### Who uses the trading system?

**Retail traders:**
- Casual investor checking Apple stock price and placing a market buy for 10 shares
- Active day trader monitoring 50 stocks simultaneously, placing limit orders throughout the day
- Long-term investor checking monthly P&L on their portfolio

**Internal systems:**
- Compliance: every order and trade must be recorded for regulatory reporting (SEC)
- Risk management: real-time check that an order does not exceed a user's buying power
- Notification: "Your limit order for AAPL was filled at $195.42"

**External dependencies:**
- Exchange (NYSE/NASDAQ): sends market data feed, accepts orders, sends fill notifications
- Clearing house (DTCC): settles trades (T+2 settlement — trades settle 2 business days later)
- Market data vendor (Refinitiv, Bloomberg): aggregates and normalizes data from multiple exchanges

### Core use cases

**P0 — Must have:**
- UC1: User sees real-time stock price for any listed stock (< 100ms latency)
- UC2: User places a market order → executed immediately at current best price
- UC3: User places a limit order → executed when price reaches the limit
- UC4: User views their portfolio: holdings + current value + P&L

**P1 — Important:**
- UC5: User views order book (bid/ask spread, market depth)
- UC6: Order fill notification: "Your order for 10 shares of AAPL was filled at $195.42"
- UC7: View order history (placed, filled, cancelled orders)

**Out of scope:**
- Margin trading (leverage)
- Options and derivatives
- Crypto (different exchanges, 24/7 markets, different regulatory framework)
- Tax lot management and tax reporting
- High-frequency trading infrastructure

---

## Phase 2: Functional Requirements (Minutes 8-14)

### Price feed operations

- **F1:** `subscribe_price(stock_symbols[]) -> stream of {symbol, bid, ask, last, volume, ts}`
- **F2:** `get_quote(symbol) -> {bid, ask, last_price, volume, change_pct}` — point-in-time price
- **F3:** `get_order_book(symbol, depth=10) -> {bids: [(price, qty)...], asks: [(price, qty)...]}`
- **F4:** `get_price_history(symbol, period='1d', interval='1m') -> [(ts, open, high, low, close, vol)...]`

### Order management

- **F5:** `place_market_order(user_id, symbol, side, quantity) -> order_id, status`
- **F6:** `place_limit_order(user_id, symbol, side, quantity, limit_price) -> order_id, status`
- **F7:** `cancel_order(user_id, order_id) -> success/failure` — can only cancel unfilled limit orders
- **F8:** `get_order_status(order_id) -> {status, filled_qty, avg_fill_price, ts}`

### Portfolio operations

- **F9:** `get_portfolio(user_id) -> {holdings: [{symbol, shares, avg_cost, current_value, pnl}...], cash, total_value}`
- **F10:** `get_buying_power(user_id) -> cash_available` — how much can the user spend

### Consistency model by operation type

```
Strong consistency required:
  Order placement (F5, F6): must not place an order if user has insufficient funds.
    Read cash_balance -> debit -> submit order must be atomic (no race condition).
  Order fill: when exchange reports a fill, portfolio must be updated exactly once.
    Idempotent fill processing (exchange may re-send fill notifications).

Eventual consistency acceptable:
  Price display (F1, F2): 100ms stale is fine. No financial decision should be made
    on a 100ms-stale price for retail users.
  P&L display (F9): 1-second stale P&L is standard for retail apps.
  Order book depth (F3): 200ms stale is fine for display.
```

---

## Phase 3: Scale and Capacity (Minutes 14-19)

### Market data volume

```
US equity markets:
  Listed stocks: ~10,000 symbols (NYSE + NASDAQ + OTC)
  Price updates per second (combined exchanges): up to 1,000,000/sec during peak
  (A volatile market day in 2024: 500M to 1B quotes across all exchanges)
  
  For a retail app (not all symbols are actively traded):
    Active trading symbols: ~1,000 (S&P 500 + popular stocks)
    Price updates for active symbols: ~50,000/sec
    
  Our system needs to:
    Ingest: 50,000 price updates/sec from exchange feed
    Process: parse, normalize, store in Redis
    Fan-out: push to subscribers (users watching each stock)

Fan-out to users:
  1,000,000 registered users, 100,000 DAU (active trading day)
  Each active user: subscribes to average 20 symbols
  Total subscriptions: 100,000 * 20 = 2,000,000 active subscriptions
  Each symbol updated 50 times/sec (avg across active symbols)
  Total push messages: 50 * 2M / 1000 = 100,000 pushes/sec
  (Divided by 1,000 because only 1 in 1,000 symbol updates is for a subscribed symbol —
   depends on distribution, but the calculation gives the order of magnitude)

Orders:
  Peak: 10,000 orders/sec (high volatility market open, 9:30-10:00 AM ET)
  Normal: 1,000 orders/sec
  Market hours: 6.5 hours/day (9:30 AM - 4:00 PM ET)
  Total orders per day: ~2 million
```

### Storage math

```
Price data (tick data):
  1 tick: symbol (4 bytes) + price (8 bytes) + volume (8 bytes) + ts (8 bytes) = 28 bytes
  50K ticks/sec * 28 bytes = 1.4 MB/sec raw ingestion
  Per day (6.5 hours): 1.4 MB * 23,400 seconds = 32.76 GB/day of tick data
  10 years: 32.76 GB * 252 trading days * 10 years = ~82 TB of tick data
  
  Storage: time-series database (InfluxDB, Cassandra, or custom columnar store)
  Hot (last 30 days): SSD, fast random reads for chart rendering
  Cold (30 days to 10 years): object storage, accessed for backtesting

Orders and trades:
  2M orders/day * 200 bytes/order = 400 MB/day
  Retained forever (regulatory requirement — 7 years)
  2M orders/day * 365 days * 7 years * 200 bytes = ~1 TB total. Trivial.

Portfolio data:
  1M users * 50 holdings avg * 50 bytes = 2.5 GB
  Redis: in-memory holdings cache. Very small.
  Postgres: authoritative holdings + cash balance per user
```

---

## Phase 4: Non-Functional Requirements (Minutes 14-19)

### Latency targets by operation

```
Price update visible to user: < 100ms end-to-end
  (Exchange emits price -> our feed handler -> Kafka -> Redis -> WebSocket -> user)
  This is achievable with a well-designed pipeline.
  For comparison: HFT needs < 1 microsecond. We need < 100,000 microseconds. Very different problems.

Order placement to exchange acknowledgment: < 500ms
  User taps "Buy" -> order submitted to exchange -> "Order received" shown to user.
  Exchange response: sub-millisecond within the data center. Network adds 10-50ms.

Order fill notification to user: < 1 second after fill occurs
  Exchange sends fill via FIX callback -> our order service processes -> Kafka -> notification -> user.

Portfolio P&L update: < 2 seconds after a price change
  Price change -> Redis update -> P&L recalculation -> WebSocket push to user.
```

### Availability

- 99.99% during market hours (9:30 AM - 4:00 PM ET). Users placing orders must not experience outages.
- 99.9% outside market hours (pre-market, after-hours, weekends). Price data may be delayed; orders accepted but queued.

---

## Phase 5: Assumptions and Constraints

- A1: US equities only. Market hours 9:30 AM - 4:00 PM ET, Monday-Friday.
- A2: We consume market data from a data vendor (Refinitiv, CBOE), not directly from exchange multicast.
- A3: Order routing: we route orders to a broker-dealer (not directly to exchanges). The broker-dealer handles exchange connections, best execution, and regulatory compliance.
- A4: Cash accounts only (no margin). Users can only buy stocks up to their cash balance.
- A5: T+2 settlement: when a user buys stock, the cash is deducted immediately but the shares settle 2 days later. Simplified: we track expected cash and available cash separately.
- A6: No fractional shares (whole shares only) for simplicity.

---

## Architecture Design — HLD

### Opening analogy

Think of a stock trading app as a sports scoreboard system for a stadium with 100,000 fans. Each fan watches different players (stocks). The stadium (exchange) sends updates at 50,000 times per second. A central scoreboard server receives all updates, puts them on a big board (Redis), and pushes updates to each fan's personal screen (WebSocket) — but only for the players that fan is watching. When a fan wants to buy a ticket to be a sponsor (place an order), they submit through a ticket office (order service) which processes the transaction against the exchange.

### Full HLD diagram

```
[NYSE / NASDAQ Exchange Feed]
  UDP multicast or data vendor (Refinitiv)
           |
           | market data (tick by tick)
           v
+--------------------+
|  FEED HANDLER      |
|                    |
|  Parse FIX/binary  |
|  Normalize format  |
|  Validate sequence |
+--------------------+
           |
           | normalized tick data
           v
+--------------------+     +--------------------+
|   KAFKA            |     |   REDIS            |
|   Topic:           |---->|   latest price per |
|   market-data      |     |   symbol           |
|   (partition by    |     |   HSET prices AAPL |
|    symbol)         |     |   {bid,ask,last}   |
+--------------------+     +--------------------+
           |                        |
           v                        | push on update
+--------------------+     +--------v-----------+
|  PRICE SERVICE     |     |  WEBSOCKET SERVER  |
|  (Kafka consumer)  |     |                    |
|  - updates Redis   |     |  - per-user sub    |
|  - computes OHLCV  |     |    registry        |
|  - writes to       |     |  - fan-out price   |
|    time-series DB  |     |    updates to      |
|                    |     |    subscribers     |
+--------------------+     +--------------------+
                                    ^
[User App]                          | push updates
  - WebSocket connection ------->---+
  - REST for orders,
    portfolio, history

                    +--------------------+
                    |  ORDER SERVICE     |
[User places order] |                   |
  POST /orders ---->|  1. Validate       |
                    |  2. Risk check     |
                    |  3. Debit cash     |
                    |  4. Route to       |
                    |     exchange       |
                    |  5. Track status   |
                    +--------------------+
                              |
                              | FIX protocol
                              v
                    +--------------------+
                    |  BROKER-DEALER     |
                    |  (Schwab, IEX, etc)|
                    |  Routes to         |
                    |  exchange, handles |
                    |  best execution    |
                    +--------------------+
                              |
                              | fill notifications (async)
                              v
                    +--------------------+
                    |  PORTFOLIO SERVICE |
                    |                   |
                    |  - Update holdings |
                    |  - Credit/debit    |
                    |    cash balance    |
                    |  - Compute P&L     |
                    +--------------------+
```

### Component responsibilities

```
+-------------------+----------------------------------+-----------+------------------+
| Component         | Responsibility                   | Stateful? | Scale target     |
+-------------------+----------------------------------+-----------+------------------+
| Feed Handler      | Parse raw exchange feed,         | NO        | 50K ticks/sec    |
|                   | normalize, publish to Kafka      |           | 5 instances      |
+-------------------+----------------------------------+-----------+------------------+
| Kafka             | market-data topic (partitioned   | YES       | 50K messages/sec |
| (market-data)     | by symbol for ordering)          |           | RF=3             |
+-------------------+----------------------------------+-----------+------------------+
| Price Service     | Kafka consumer: update Redis,    | NO        | 50K updates/sec  |
|                   | write to time-series DB          |           | 10 instances     |
+-------------------+----------------------------------+-----------+------------------+
| Redis             | Latest price per symbol          | YES       | 10K keys         |
|                   | HSET prices:{symbol} bid ask last|           | (symbols)        |
+-------------------+----------------------------------+-----------+------------------+
| WebSocket Server  | Per-user subscription registry, | YES       | 100K connections |
|                   | fan-out price updates to users  |           | 10 servers       |
+-------------------+----------------------------------+-----------+------------------+
| Order Service     | Validate, risk check, debit,    | NO        | 10K orders/sec   |
|                   | route to broker, track status    |           | 5 instances      |
+-------------------+----------------------------------+-----------+------------------+
| Portfolio Service | Holdings, cash balance, P&L.    | NO        | 100K users       |
|                   | Processes exchange fill notifs   |           | DAU              |
+-------------------+----------------------------------+-----------+------------------+
| PostgreSQL        | Orders, holdings, cash balances | YES       | 10K writes/sec   |
|                   | Source of truth for all accounts|           | 1 primary + RR   |
+-------------------+----------------------------------+-----------+------------------+
| Time-Series DB    | OHLCV candles, tick history     | YES       | 32 GB/day writes |
| (InfluxDB/Cassandra|for charts and backtesting       |           |                  |
+-------------------+----------------------------------+-----------+------------------+
```

---

## Component 1: Market Data Pipeline — Exchange Feed to User

**This is the highest-throughput part of the system. Nail the pipeline.**

### The exchange feed

```
Exchanges (NYSE, NASDAQ) publish market data via:
  UDP multicast: each price update is a UDP packet sent to a multicast group.
    All subscribers receive the same packet simultaneously.
    No acknowledgment (fire-and-forget). Packets may be dropped.
    Sequence numbers: each packet has a sequence number. If packet 1000 is followed by 1002,
    packet 1001 was dropped. Feed handler must detect and request retransmission.
  
  Protocol: FIX/FAST (Financial Information eXchange, FAST encoding = binary compression)
    FAST: variable-length binary encoding. 10-byte fields encoded in 3-4 bytes.
    Much faster to parse than text-based FIX. Designed for 1M+ messages/sec.

For a retail app: we don't connect directly to exchange multicast.
  We consume from a market data vendor (Refinitiv, CBOE Global Markets Data).
  Vendor: handles exchange connections, normalizes across exchanges, provides a clean API.
  Our feed handler: connects to the vendor's normalized feed (TCP or FIX over network).
  This eliminates the UDP multicast complexity (vendor handles retransmission, sequencing).
```

### Feed handler design

```
Feed Handler receives: stream of quote updates
  {symbol: "AAPL", bid: 195.40, bid_size: 100, ask: 195.42, ask_size: 200,
   last_trade: 195.41, last_size: 50, timestamp: 1735000000123456789}  (nanosecond precision)

Step 1: Parse
  Binary FIX/FAST: parse binary fields into struct.
  Text FIX: split by delimiter, parse field values. Slower (text parsing).
  For retail app via vendor: usually normalized JSON or Protobuf. Parse easily.

Step 2: Validate sequence
  Each symbol's feed has a sequence number. If sequence gap detected:
    Fetch missing messages from vendor's gap-fill service (TCP request).
    Or: mark a "gap" and serve the last known price until gap is filled.

Step 3: Normalize
  Different exchanges use different field names, precision.
  Normalize: {symbol, bid, ask, last, volume, ts} — consistent internal format.

Step 4: Publish to Kafka
  Key: symbol (ensures all updates for AAPL go to the same Kafka partition)
  Value: normalized tick data (Protobuf or JSON)
  Partition: by symbol hash. AAPL always -> partition 7. GOOGL -> partition 12.
  Kafka ordering guarantee: within a partition, order is preserved.
  So: AAPL price updates are always processed in order. Critical for correct bid/ask.
```

### Price service (Kafka consumer)

```
Kafka consumer group: price-service-group
  Each consumer instance handles a subset of Kafka partitions (symbol subsets).
  
On receiving a tick for AAPL:
  1. Update Redis:
     HSET prices:AAPL bid 195.40 ask 195.42 last 195.41 volume 1234567 ts 1735000000
     O(1). Immediate. Redis holds the latest price for every symbol.

  2. Write to time-series DB (InfluxDB or Cassandra):
     INSERT INTO ticks (symbol, bid, ask, last, volume, ts) VALUES (...)
     Async write (batched): accumulate 1,000 ticks, flush every 100ms.
     Batch insert: 10x throughput improvement vs. individual inserts.

  3. Trigger WebSocket fan-out:
     Publish to internal pub/sub channel: "price_update:AAPL {bid, ask, last}"
     WebSocket servers subscribed to price_update:AAPL: push to all users subscribed to AAPL.
     
     Internal pub/sub: Redis PUBLISH or Kafka internal topic.
     Redis PUBLISH price_update:AAPL {json}
     WebSocket servers: SUBSCRIBE price_update:* -> receive all price updates -> fan out to users.
```

### WebSocket fan-out to subscribers

```
Each user opens a WebSocket connection and sends:
  {action: "subscribe", symbols: ["AAPL", "GOOGL", "MSFT", "AMZN", ...20 stocks...]}

WebSocket server: maintains an in-memory subscription map.
  subscriptions = {
    "AAPL": [ws_connection_1, ws_connection_5, ws_connection_11, ...],
    "GOOGL": [ws_connection_2, ws_connection_5, ws_connection_8, ...],
    ...
  }

On receiving a price update for AAPL (from Redis PUBLISH):
  Look up subscriptions["AAPL"] -> list of WebSocket connections.
  For each connection: send {symbol: "AAPL", bid: 195.40, ask: 195.42, last: 195.41}
  
  Fan-out at 50K price updates/sec:
    If AAPL has 10,000 subscribers and receives 50 updates/sec:
    10,000 * 50 = 500,000 WebSocket sends/sec for AAPL alone.
    At 8 bytes/message: 500K * 40 bytes = 20 MB/sec for AAPL sends.
    
  Throttling: cap the push rate per user per symbol.
    User subscribes to AAPL: receive at most 1 update/second (not 50/second).
    Price service: when AAPL is updated 50 times/sec, deduplicate to the latest value.
    Send to users: latest price once per second (or on significant change, e.g., > 0.01% move).
    
    Why: 50 updates/second per symbol * 20 symbols = 1,000 WebSocket messages/second to each user.
    Most phones cannot render 1,000 UI updates per second. Rate limiting to 1-5/sec per symbol.
    Actual displayed change: 1x per second per stock. Unnoticeable reduction from 50/sec.

Connection routing:
  100K concurrent WebSocket connections across 10 WebSocket servers (10K per server).
  When a price update arrives: which server has subscribers for AAPL?
  
  Option A: all servers subscribe to all price updates.
    Redis PUBLISH aapl_update {data}; all 10 WebSocket servers receive it.
    Each server checks its local subscriptions and sends to its users.
    Redis fan-out: 10 servers * 50K updates/sec = 500K Redis messages/sec. Manageable.
    
  Option B: subscription registry.
    Central registry: {symbol -> [server_ids]}.
    Price service: look up which servers have subscribers, push only to those.
    More complex; not needed at 10 servers.
```

---

## Component 2: Order Placement and Execution

### The order placement flow

```
User places a market order: "Buy 10 shares of AAPL at market price"

Step 1: Validate input
  symbol = "AAPL" -- valid symbol? Check against symbol list.
  quantity = 10 -- positive integer, below max order size (10,000 shares).
  side = "BUY" -- valid side.

Step 2: Risk check (pre-trade)
  current_price = HGET prices:AAPL last  -> 195.41
  estimated_cost = 10 * 195.41 = $1,954.10
  available_cash = GET user:{user_id}:available_cash  -> $5,000
  
  If estimated_cost > available_cash: reject with "Insufficient funds."
  (Market order price can differ from estimated; use worst-case estimate + 1% buffer)

Step 3: Debit estimated cost (hold the funds)
  UPDATE user_accounts SET available_cash = available_cash - 1974 WHERE user_id = ?
  AND available_cash >= 1974  -- atomic check-and-debit
  
  If rows_affected = 0: race condition, insufficient funds. Reject.
  If rows_affected = 1: funds held. Proceed.
  
  Note: actual debit depends on fill price. On fill: reconcile actual cost.
  If fill is at $195.41 but we held $197.41 (1% buffer): refund the difference.

Step 4: Submit to broker-dealer
  Use FIX protocol: send NewOrderSingle message to the broker's FIX gateway.
  FIX message:
    35=D (MsgType=NewOrderSingle)
    49=OUR_COMP_ID
    11={client_order_id=user_id+timestamp}  -- unique order identifier
    55=AAPL  -- symbol
    54=1  -- side (1=Buy, 2=Sell)
    38=10  -- quantity
    40=1  -- order type (1=Market, 2=Limit)
    60={timestamp}  -- transact time
  
  Broker responds:
    35=8 (ExecutionReport)
    If immediate fill (market order): status=2 (FILLED), LastPx=195.41, LastQty=10
    If accepted for routing: status=0 (NEW) or status=1 (PARTIAL_FILL)

Step 5: Store order in Postgres
  INSERT INTO orders (order_id, user_id, symbol, side, quantity, order_type, status, submitted_at)
  VALUES (...)
  
  Return to user: {order_id, status: "PENDING", estimated_fill_price: 195.41}

Step 6: Process fill (async)
  Exchange sends fill via FIX callback to our broker callback endpoint.
  Or: our broker sends us fills via WebSocket/FIX.
  
  Fill message: {order_id, fill_price: 195.41, fill_qty: 10, ts: ...}
  Order Service: UPDATE orders SET status='FILLED', fill_price=195.41 WHERE order_id=?
  Portfolio Service: UPDATE holdings SET shares=shares+10 WHERE user_id=? AND symbol='AAPL'
  Portfolio Service: UPDATE user_accounts SET available_cash = available_cash - (195.41*10)
                     + (held_amount - 195.41*10)  -- refund the buffer
  Publish: Kafka topic: order-fills -> Notification Service: "Order filled at $195.41"
```

### Limit order management

```
Limit order: "Buy 10 shares of AAPL only if price drops to $190"

Submitted to broker: same FIX NewOrderSingle with OrdType=2 (Limit), Price=190.00
Broker routes to exchange: order added to the exchange's order book for AAPL.

Status: "WORKING" (open limit order, not yet filled)

Our system: stores the limit order in Postgres with status=WORKING.
  User can cancel: DELETE from broker's order book via FIX OrderCancelRequest message.

Fill event (if AAPL drops to $190):
  Exchange matches the limit order: fill notification sent to broker -> us.
  Same fill processing as market order.

Partial fills:
  Exchange may fill 5 of 10 shares immediately, then fill the other 5 later.
  First fill message: fill_qty=5, cumulative_qty=5.
  Order status: PARTIALLY_FILLED.
  Second fill: fill_qty=5, cumulative_qty=10. Status: FILLED.

Cancel in flight:
  User cancels while order is partially filled.
  FIX OrderCancelRequest sent.
  Exchange: cancels remaining unfilled shares.
  Response: ExecutionReport with status=CANCELLED, total_filled_qty=5 (the already-filled portion).
  Refund cash held for the cancelled 5 shares.
```

---

## Component 3: Real-Time Portfolio and P&L

### Portfolio value calculation

```
Portfolio P&L formula:
  For each holding: P&L = shares * (current_price - avg_cost)
  Total portfolio value = Σ (shares * current_price) + cash_balance

current_price: fetched from Redis (HGET prices:AAPL last)
  This is the latest market price, updated every second by the Price Service.
  P&L is real-time, accurate to within 1 second.

How to push P&L updates to users:
  Option A: recalculate P&L on every price update for any held stock.
    On AAPL price update: find all users who hold AAPL.
    For each user: recalculate their AAPL P&L -> push via WebSocket.
    
    Problem: 10 million AAPL shareholders * 50 AAPL updates/sec = 500M P&L recalculations/sec.
    Infeasible.
  
  Option B: per-user recalculation on their own update schedule.
    Each user's portfolio is recalculated once per second.
    100K DAU / 1 second = 100K portfolio calculations per second.
    Each calculation: GET prices for all held symbols (pipeline Redis HGET for 20 symbols).
    = 100K * 20 Redis reads/sec = 2M Redis reads/sec. Feasible.
    Push result: 100K WebSocket pushes/sec (one per user, per second).
    
    This is the correct approach. Decouple price updates from P&L calculation.
    Price updates are high-frequency (50K/sec), P&L calculation is user-frequency (1/sec/user).

Portfolio data in Postgres:
  Table: holdings
  +----------+--------+------+----------+-----------+
  | user_id  | symbol | qty  | avg_cost | updated_at|
  +----------+--------+------+----------+-----------+
  | u123     | AAPL   | 10   | 180.00   | 2024-12-01|
  | u123     | GOOGL  | 5    | 140.00   | 2024-11-15|
  +----------+--------+------+----------+-----------+
  
  avg_cost updates on each fill:
    New avg_cost = (old_qty * old_avg_cost + fill_qty * fill_price) / (old_qty + fill_qty)
  
  P&L calculation:
    unrealized_pnl = qty * (current_price - avg_cost)
    realized_pnl = sum(sales) - sum(purchase_costs)  [historical, from orders table]
```

---

## API Design

### Place Order
```
POST /v1/orders
Request:  { account_id: string, symbol: string,
            side: BUY|SELL,
            type: MARKET|LIMIT|STOP,
            quantity: int,
            limit_price: decimal (required if type=LIMIT),
            stop_price: decimal (required if type=STOP),
            idempotency_key: string }
Response: { order_id: string, status: PENDING|REJECTED,
            symbol, side, type, quantity, submitted_at: timestamp }
Errors:   400 insufficient funds, 400 invalid symbol, 400 market closed,
          409 duplicate idempotency_key
```

Notes on idempotency_key: the client generates a UUID before sending. If the network drops and the client retries, the same key is sent again. The server returns the original response without double-submitting the order. This maps to the FIX `client_order_id` field used internally.

### Cancel Order
```
DELETE /v1/orders/{order_id}
Request:  { account_id: string }
Response: { order_id, status: CANCELLED|PARTIALLY_FILLED_CANCEL }
Errors:   404, 409 already filled
```

Notes: cancellation is best-effort for limit orders already at the exchange. The exchange may fill the order in the microseconds between our cancel request and the exchange processing it. The response reflects the state as of the cancel confirmation received from the exchange via FIX `OrderCancelReject` or a fill `ExecutionReport`.

### Get Order Status
```
GET /v1/orders/{order_id}
Response: { order_id, status: PENDING|PARTIAL|FILLED|CANCELLED|REJECTED,
            filled_quantity: int, avg_fill_price: decimal,
            executions: [{exec_id, quantity, price, filled_at}] }
```

Notes: polling this endpoint is the fallback for clients that miss the WebSocket fill notification. The `executions` array lists each partial fill, enabling clients to reconstruct the fill history for multi-fill limit orders.

### Get Portfolio
```
GET /v1/accounts/{account_id}/portfolio
Response: { positions: [{symbol, quantity, avg_cost, current_price,
                         unrealized_pnl, unrealized_pnl_pct}],
            cash_balance: decimal, total_value: decimal }
```

Notes: `current_price` is served from the Redis price cache (HGET prices:{symbol} last). p99 target < 50ms. The response is a snapshot -- prices may shift by the time the client renders it. For live P&L, the client should use the WebSocket stream.

### Subscribe to Market Data (WebSocket)
```
WS  /v1/market-data/stream
Send:   { action: subscribe, symbols: [string] }  -- max 50 symbols
Recv:   { symbol, price, bid, ask, volume, timestamp }
```

Notes: server-side throttle -- one push per symbol per second, implemented via the dirty-flag pattern (a single flush coroutine, NOT one timer per subscriber). At 50K active connections, creating 50K individual timers would exhaust the event loop scheduler. The flush coroutine wakes once per second, snapshots the dirty map, and sends all pending prices in a single `asyncio.gather` call.

### Get Price History (Sparkline)
```
GET /v1/market-data/{symbol}/history?interval=1d&range=1W
Response: { symbol, candles: [{open, high, low, close, volume, timestamp}] }
```

Notes: pre-aggregated OHLCV candles are served from a read replica or a dedicated time-series DB (InfluxDB/TimescaleDB). Raw tick data is downsampled at write time by the Price Service. Serving pre-aggregated candles avoids expensive range scans on the raw ticks table at query time. Cache TTL: 60 seconds for current-day candles (frequently updated), 24 hours for historical candles (immutable).

---

## DB Schema

```sql
CREATE TABLE orders (
  order_id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id       UUID         NOT NULL,
  symbol           VARCHAR(10)  NOT NULL,
  side             VARCHAR(4)   NOT NULL,   -- BUY|SELL
  order_type       VARCHAR(6)   NOT NULL,   -- MARKET|LIMIT|STOP
  quantity         INT          NOT NULL,
  limit_price      DECIMAL(12,4),           -- null for MARKET orders
  stop_price       DECIMAL(12,4),           -- null for non-STOP orders
  status           VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
  idempotency_key  VARCHAR(64)  UNIQUE NOT NULL,
  submitted_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  filled_at        TIMESTAMPTZ
);
CREATE INDEX idx_orders_account ON orders(account_id, submitted_at DESC);
CREATE INDEX idx_orders_symbol  ON orders(symbol, status)
  WHERE status = 'PENDING';               -- partial index: open orders only
```

The partial index on `(symbol, status) WHERE status = 'PENDING'` is a key optimization: open order checks (needed for the stop-order monitor and PDT rule enforcement) scan only pending rows, not the full order history. On a mature platform with millions of historical orders, this difference is orders of magnitude in query speed.

```sql
CREATE TABLE executions (
  exec_id          VARCHAR(64)  PRIMARY KEY,  -- broker-assigned ExecID (FIX field 17)
  order_id         UUID         NOT NULL REFERENCES orders(order_id),
  symbol           VARCHAR(10)  NOT NULL,
  side             VARCHAR(4)   NOT NULL,
  quantity         INT          NOT NULL,
  price            DECIMAL(12,4) NOT NULL,
  filled_at        TIMESTAMPTZ  NOT NULL
);
-- ExecID dedup: INSERT INTO executions ... ON CONFLICT (exec_id) DO NOTHING
CREATE INDEX idx_exec_order ON executions(order_id);
```

The `exec_id` primary key is the idempotency mechanism for fill processing. Because `exec_id` is the PRIMARY KEY (not just a UNIQUE index), Postgres enforces uniqueness at the storage level. The `ON CONFLICT DO NOTHING` pattern means the Portfolio Service can safely be called multiple times for the same fill -- a critical property when Kafka at-least-once delivery replays fill events after a consumer restart.

```sql
CREATE TABLE positions (
  account_id       UUID         NOT NULL,
  symbol           VARCHAR(10)  NOT NULL,
  quantity         INT          NOT NULL DEFAULT 0,
  avg_cost         DECIMAL(12,4) NOT NULL DEFAULT 0,
  PRIMARY KEY (account_id, symbol)
);
```

```sql
CREATE TABLE accounts (
  account_id       UUID         PRIMARY KEY,
  user_id          UUID         NOT NULL UNIQUE,
  available_cash   DECIMAL(15,2) NOT NULL DEFAULT 0,
  total_cash       DECIMAL(15,2) NOT NULL DEFAULT 0,
  is_active        BOOLEAN      NOT NULL DEFAULT true
);
-- Atomic cash debit:
-- UPDATE accounts SET available_cash = available_cash - $cost
-- WHERE account_id = $id AND available_cash >= $cost
-- rows_affected = 0 means insufficient funds
```

`available_cash` is the funds not currently held by any open order. `total_cash` includes funds held for open orders. On order placement: decrement `available_cash` only. On fill: reconcile `total_cash` (subtract actual fill cost, add back the hold buffer if the fill price was lower than estimated). On cancel: return the held amount to `available_cash`. The two-field design makes it impossible for a user to spend funds already reserved for another order, even under concurrent requests, because the WHERE clause is the atomic guard.

```sql
-- SEC 17a-4 audit log (append-only, WORM)
CREATE TABLE trade_audit_log (
  id               BIGSERIAL    PRIMARY KEY,
  event_type       VARCHAR(30)  NOT NULL,
  account_id       UUID         NOT NULL,
  order_id         UUID,
  exec_id          VARCHAR(64),
  payload          JSONB        NOT NULL,  -- full event snapshot
  logged_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
-- This table is write-only from the app; DELETE/UPDATE are denied by DB role policy.
```

The `trade_audit_log` is append-only by policy: the application DB role has INSERT privilege but not UPDATE or DELETE. The `payload` JSONB column stores the complete event state at the time of the write -- not a reference to other tables. This means the audit record is self-contained even if the referenced order or account is later modified. Long-term retention (7 years per SEC Rule 17a-4) is handled by streaming this table to S3 with Object Lock in COMPLIANCE mode.

```
Index summary:
  orders:         PK (order_id), idx on (account_id, submitted_at DESC),
                  partial idx on (symbol, status) WHERE status='PENDING'
  executions:     PK (exec_id), idx on (order_id)
  positions:      PK (account_id, symbol)
  accounts:       PK (account_id), UNIQUE on (user_id)
  trade_audit_log: PK (id -- sequential bigserial for range scans by date)
```

---

## Component 4: The Order Book (L6 Depth)

**Know this to discuss the exchange-side matching engine at L6.**

### What is an order book?

```
An order book is the list of all pending buy and sell orders for one stock,
waiting to be matched with a counterparty.

Example order book for AAPL:

BID SIDE (buy orders, highest price first):
  Price   | Quantity | Time
  $195.42 |    100   | 09:30:00.001
  $195.41 |    200   | 09:30:00.003
  $195.41 |     50   | 09:30:00.005  (second order at same price, later time)
  $195.40 |    500   | 09:30:00.007

ASK SIDE (sell orders, lowest price first):
  Price   | Quantity | Time
  $195.43 |    150   | 09:30:00.002
  $195.44 |    100   | 09:30:00.004
  $195.45 |    300   | 09:30:00.009

Best bid: $195.42. Best ask: $195.43. Spread: $0.01.

"Last trade" price: the price of the most recent executed trade.
The bid-ask spread is how market makers profit (buy at bid, sell at ask).
```

### Price-time priority matching

```
Matching rule: when a new buy order (market or aggressive limit) arrives:
  Match against the lowest ask price first.
  If multiple orders at the same price: match the OLDEST order first (time priority).

Example: a market buy order for 250 shares arrives.
  Best ask: 150 shares @ $195.43 (order from 09:30:00.002)
  Match: buy 150 shares @ $195.43. Order filled: 150/250 done. Remaining: 100 shares.
  
  Next best ask: 100 shares @ $195.44 (order from 09:30:00.004)
  Match: buy 100 shares @ $195.44. Order fully filled.
  
  Fill report: 150 @ $195.43 + 100 @ $195.44 = avg price $195.436 for 250 shares.

Data structure for the order book:
  Per price level: a FIFO queue of orders (oldest first = time priority).
  Across price levels: sorted structure (bid side: max-heap or sorted map, desc; ask side: min-heap or sorted map, asc).
  
  In practice: two sorted maps (Red-Black Tree or skip list):
    bid_side: {price -> FIFO_queue_of_orders}  -- sorted by price DESC
    ask_side: {price -> FIFO_queue_of_orders}  -- sorted by price ASC
  
  O(log N) for insert (new order at a new price level).
  O(1) for peek at best bid/ask.
  O(1) for cancel if we maintain a hash map of {order_id -> order_reference} for O(1) lookup.
  
  cancel_order(order_id):
    order = order_map[order_id]
    Remove from the FIFO queue at order.price_level.
    If FIFO queue becomes empty: remove price level from the sorted map.
```

---

## Failure Scenarios

### Failure 1: Feed handler loses connection to market data vendor

```
Impact: price updates stop flowing. All users see stale prices.

Detection: Feed Handler health check: if no tick received in 5 seconds, alert.
  (Impossible for all 10,000 symbols to go 5 seconds without a tick on an active market day.)

Recovery:
  Feed Handler: reconnect to vendor's FIX gateway (retry with backoff).
  Upon reconnect: request a "snapshot" of the current best bid/ask for all symbols.
  Resume real-time feed from the current sequence number.
  
  During the outage: Redis prices are stale. WebSocket: push a "prices may be stale" flag to users.
  Do NOT allow new market orders during this window (prices unreliable).
  Limit orders: already at the exchange, unaffected.

Duration: most vendor reconnects complete in < 30 seconds.
User impact: stale prices for < 30 seconds. No orders accepted for market orders.
```

### Failure 2: Order submission to broker fails mid-flight

```
Scenario: Order Service submits order via FIX, sends the message, but does not receive an acknowledgment before TCP timeout (30 seconds).

The order may or may not have reached the broker (network partition between submission and ack).

Impact: unknown order state. Did the broker get it?

Fix: unique client_order_id per order.
  The FIX OrderStatusRequest message: "What is the status of client_order_id=xyz?"
  Broker responds with the current status of that order (or UNKNOWN if not received).
  
  On timeout: send OrderStatusRequest.
  If broker knows the order: resume normal tracking.
  If broker does not know: re-submit the order (idempotent via client_order_id).
  
  Why re-submit is safe: FIX standard — if broker receives a duplicate client_order_id for the same account,
  it is rejected as a duplicate. No double-order.

Database state during unknown period:
  Order status: PENDING (submitted but not acknowledged).
  Funds held: yes (debited before submission).
  After OrderStatusRequest: update to WORKING, FILLED, or CANCELLED.
```

### Failure 3: Portfolio service processes the same fill twice

```
Scenario: Exchange sends fill notification. Our service processes it.
  Kafka at-least-once delivery: if the consumer crashes before committing the Kafka offset,
  the fill message will be redelivered after restart.
  Portfolio service processes the fill a second time.
  
  Without idempotency: holdings doubled. User has 20 shares instead of 10.
  Cash double-debited (or double-credited on a sale).

Fix: fill deduplication.
  Each fill from the broker/exchange has a unique ExecID (FIX field 17).
  Before processing a fill:
    INSERT INTO processed_fills (exec_id) VALUES (?) ON CONFLICT DO NOTHING
    If rows_affected = 0: fill already processed. Skip.
    If rows_affected = 1: new fill. Process.
  
  This is an idempotency table. processed_fills stores exec_ids with a 30-day TTL.
  Old records purged by a background job.
  
  Why Postgres and not Redis: fills are financial records. Must be durable.
    Redis (without AOF + persistence): could lose dedup state on crash -> double-processing resumes.
    Postgres: ACID. Once an exec_id is committed, it survives any crash.
```

### Failure 4: Market data gap during high volatility

```
Scenario: a major market event (earnings miss, macro news) causes extreme volatility.
  Quote update rate: spikes to 500,000 updates/sec (10x normal).
  Our Kafka consumer (Price Service): designed for 50K/sec. 
  Kafka consumer lag: grows at 450K messages/sec. After 1 minute: 27M messages behind.
  
  User-visible effect: prices shown are 30+ seconds stale. Users may place orders at wrong prices.
  Risk: users think Apple is at $200 (stale), it's actually $190 (10% gap just happened).

Mitigation:
  1. Auto-scale Price Service consumers on lag threshold.
     Kafka consumer lag monitoring (Burrow or Confluent Control Center).
     Alarm: if lag > 100K messages, add 5 more consumer instances.
     Spin-up time: 30-60 seconds (auto-scaling takes time).
  
  2. For the period of extreme lag: show a "prices may be delayed" banner to users.
     Do NOT accept market orders when price lag > 10 seconds.
  
  3. Better: pre-size the system for 10x normal load (defensive capacity planning).
     If average is 50K/sec: provision for 500K/sec. The extra capacity sits idle 99% of the time
     but prevents degradation on the 1% of extreme events that matter most.
  
  4. Kafka retention: messages retained for 7 days. Even if consumer is 30 minutes behind,
     it will eventually catch up and no data is lost.
```

---

## Deep Concept Explanations

### Concept 1: Why UDP Multicast for Exchange Feeds

```
The exchange sends 1M+ price updates per second to thousands of subscribers (banks, hedge funds).
Why not TCP?

TCP limitations for market data:
  TCP is one-to-one (unicast). Exchange would need 1,000 separate TCP connections for 1,000 subscribers.
  1,000 * 1M updates/sec = 1B messages/sec of TCP traffic from the exchange. Impossible.
  TCP also requires ACKs. At 1M updates/sec: waiting for ACKs from 1,000 subscribers
  would throttle the publisher to the speed of the slowest subscriber. Unacceptable.

UDP multicast:
  Multicast: exchange sends one UDP packet to a multicast IP address.
  All subscribers in the multicast group receive the same packet simultaneously.
  Network switches replicate the packet to each subscriber.
  Exchange network traffic: the same as if it had only one subscriber.
  No ACK overhead. No TCP handshake. Minimal latency.
  
  Packet loss:
  UDP does not retransmit lost packets. Subscribers detect gaps via sequence numbers.
  Gap-fill service: a separate TCP endpoint where subscribers can request missed messages.
    "I missed messages 1001 through 1005. Send them."
  
  Latency:
  UDP multicast latency: < 1 microsecond within a datacenter (for HFT).
  At this level: physical wire length matters. Speed of light in fiber: 200,000 km/sec.
  1 meter of wire = 5 nanoseconds. HFT firms co-locate within feet of the exchange.

For retail apps: we don't use UDP multicast directly.
  Our vendor (Refinitiv) aggregates and normalizes the multicast feed and delivers via TCP.
  We trade latency (TCP vs UDP: +100 microseconds) for simplicity (no multicast complexity).
  For retail users: 100ms latency SLA. 100 microseconds of extra TCP overhead is irrelevant.
```

### Concept 2: FIX Protocol

```
FIX (Financial Information eXchange): the standard messaging protocol for financial markets.
Every broker, exchange, and financial institution speaks FIX.
Established in 1992. Still dominant today.

FIX message format:
  Key-value pairs, each separated by SOH (ASCII 1 character).
  Fields: {tag=value}
  
  Example NewOrderSingle (order placement):
  8=FIX.4.2\19=105\135=D\149=CLIENT_COMP\156=EXCHANGE_COMP\152=20241224\160=092500000\
  111=ORDER_12345\155=AAPL\154=1\138=10\140=1\160=09:25:00\110=0\
  
  Key fields:
    35=D: message type (D = NewOrderSingle)
    11=ORDER_12345: client-assigned order ID (idempotency key)
    55=AAPL: symbol
    54=1: side (1=Buy, 2=Sell)
    38=10: quantity
    40=1: order type (1=Market, 2=Limit)
    44=190.00: limit price (if limit order)
  
  Response ExecutionReport (35=8):
    39=2: status (2=Filled)
    31=195.41: last fill price (LastPx)
    32=10: last fill quantity (LastQty)
    6=195.41: average fill price (AvgPx)

FIX/FAST (FAST = FIX Adapted for STreaming):
  Binary encoding of FIX messages. 60-80% smaller than text FIX.
  At 1M messages/sec: text FIX: 1M * 100 bytes = 100 MB/sec. FAST: 1M * 20 bytes = 20 MB/sec.
  FAST reduces bandwidth by 5x. At 10 Gbps links: FAST allows 10x more messages.
```

### Concept 3: Market Hours and Pre/Post Market Trading

```
US equity market hours:
  Regular session: 9:30 AM - 4:00 PM ET (Monday-Friday, excluding holidays)
  Pre-market (extended hours): 4:00 AM - 9:30 AM ET
  After-hours (extended hours): 4:00 PM - 8:00 PM ET

During regular session:
  Full liquidity (millions of active orders).
  NBBO (National Best Bid and Offer): regulated best price across all exchanges.
  Market orders execute immediately at best available price.

During extended hours:
  Much lower liquidity (fewer participants).
  No NBBO regulation in some jurisdictions.
  Wide spreads (bid-ask gap is larger).
  Market orders: high risk of bad fill (spread may be $1 wide instead of $0.01).
  Limit orders only recommended for extended hours.
  
System differences at market close (4:00 PM ET):
  Order routing: no new orders routed to exchanges (they're closed).
  Open limit orders: remain in exchange order books (good-till-cancel orders persist).
  Price feed: switches from real-time to "end of day" prices. WebSocket pushes stop.
  Portfolio P&L: uses closing prices (official end-of-day prices, not bid-ask).
  
Automated market close handling:
  At 4:00 PM ET: Order Service stops accepting new market orders.
  Sends a "market closed" status to WebSocket server: push to all users.
  Price feed transitions: Feed Handler switches to vendor's end-of-day data source.
```

---

## L5 vs L6 Calibration Table

```
+---------------------+----------------------------+--------------------------------+
| Dimension           | L5 (Senior SWE)             | L6 (Staff)                     |
+---------------------+----------------------------+--------------------------------+
| Market data         | Feed handler -> Kafka ->   | Feed handler details: UDP      |
| pipeline            | Redis -> WebSocket. Basic  | multicast, FIX/FAST parsing,   |
|                     | flow correct.              | sequence gap detection, gap-   |
|                     |                            | fill service. Exchange topology.|
+---------------------+----------------------------+--------------------------------+
| Price display       | WebSocket push, Redis       | Fan-out math: 50K updates/sec  |
|                     | latest price               | * 10K subscribers = 500M       |
|                     |                            | sends/sec. Throttle to 1/sec.  |
|                     |                            | Per-user subscription registry.|
+---------------------+----------------------------+--------------------------------+
| Order placement     | Validate -> debit -> route | FIX protocol fields. Idempotent|
|                     | to broker. Async fills.     | client_order_id. OrderStatus-  |
|                     |                            | Request for unknown state.     |
|                     |                            | Partial fill handling. Cancel- |
|                     |                            | in-flight semantics.           |
+---------------------+----------------------------+--------------------------------+
| Portfolio P&L       | Holdings * Redis prices.   | Decoupled update schedule:     |
|                     | Knows eventual consistency  | price updates 50K/sec, P&L     |
|                     | is acceptable for P&L       | recalc 1/sec/user. Avg cost    |
|                     |                            | formula on fills. Realized vs  |
|                     |                            | unrealized P&L distinction.    |
+---------------------+----------------------------+--------------------------------+
| Order book          | Knows bid/ask spread,       | Data structure: two sorted     |
|                     | matching concept            | maps (Red-Black Tree) with     |
|                     |                            | FIFO queues per price level.   |
|                     |                            | Price-time priority matching.  |
|                     |                            | O(log N) add, O(1) cancel via  |
|                     |                            | order_id hash map.             |
+---------------------+----------------------------+--------------------------------+
| Consistency model   | Knows orders need strong   | Precise: funds debit is atomic |
|                     | consistency, prices do not  | (UPDATE WHERE cash>=cost).     |
|                     |                            | Fill idempotency via exec_id   |
|                     |                            | dedup table in Postgres.       |
|                     |                            | Price: eventual OK for display,|
|                     |                            | stale price detection needed   |
|                     |                            | before accepting market orders.|
+---------------------+----------------------------+--------------------------------+
| Low-latency design  | Mentions caching,          | No GC pauses (off-heap memory  |
|                     | binary protocols           | in Java, or Go/C++). CPU       |
|                     |                            | affinity for latency-sensitive |
|                     |                            | threads. Kernel bypass (DPDK)  |
|                     |                            | for HFT. Co-location economics.|
+---------------------+----------------------------+--------------------------------+
```

---

## Production Incidents

### Incident 1: Knight Capital Group Algorithmic Trading Loss (2012)

**Company:** Knight Capital Group (now KCG)  
**What happened:** Knight Capital deployed a new order routing system to 8 of their 17 servers, but left an old "SMARS" algorithm active on the other 9 servers. When the market opened on August 1, 2012, the old SMARS algorithm on 9 servers received retail order flow and began sending orders to exchanges using a repurposed order flag. In 45 minutes, Knight accumulated a $7 billion unintended equity position (bought millions of shares at high prices, selling them at lower prices). The net loss: $440 million. Knight was nearly insolvent.

**Root cause:** Incomplete deployment — 9 of 17 servers had old code with a bug. No automated check verified that all servers ran the same version. No circuit breaker to halt trading when loss exceeded a threshold.

**Staff lesson:** Automated rollout validation is critical for systems that touch money. Before any algorithmic trading system goes live, verify: all server instances are running the same version, all are healthy, and a "kill switch" circuit breaker is armed. Position limits and daily loss limits must be hard-coded safeties that halt trading automatically — not a human monitoring a dashboard.

---

### Incident 2: Robinhood Outage During Market Open (2020)

**Company:** Robinhood  
**What happened:** On March 2, 2020 (the day after the Federal Reserve announced an emergency rate cut causing extreme volatility), Robinhood experienced a nearly complete outage that lasted most of the trading day. Users could not view prices, place orders, or access their portfolios. The outage was caused by the expiry of a critical domain certificate that had not been rotated. The certificate expiry prevented the DNS infrastructure from resolving, causing cascading failures across all services.

**Root cause:** A TLS certificate for a critical internal service expired. Certificate rotation was a manual process with inadequate monitoring. The certificate expiry was not caught by automated alerting until it caused a production failure.

**Fix:** Implemented automated certificate monitoring: alert at 60, 30, and 7 days before expiry. Implemented automated certificate rotation (Let's Encrypt ACME protocol) for non-internal certificates. Established certificate inventory with expiry tracking dashboard.

**Staff lesson:** Infrastructure dependencies (certificates, API keys, rotated secrets) have expiry dates. Any credential or certificate that can expire must be in an automated rotation pipeline with monitoring. Manual renewal processes always fail eventually.

---

### Incident 3: Facebook IPO NASDAQ Technical Failure (2012)

**Company:** NASDAQ  
**What happened:** During the Facebook IPO on May 18, 2012, NASDAQ's IPO cross (the process of setting the opening price for a new stock and executing all pre-market orders at once) experienced a software bug. The system entered an infinite loop while calculating the opening price because it was simultaneously trying to process cancellation requests for orders that were already in the queue. The opening was delayed 30 minutes. More critically: NASDAQ's systems processed approximately 30 million shares in the opening cross but had no confirmation mechanism — traders who placed orders didn't know for 2 hours whether their orders were filled. Some firms' risk systems, assuming failed execution, placed duplicate orders that were then filled after the first set of confirmations arrived.

**Root cause:** The order cross algorithm had a race condition between order submission and cancellation. The confirmation system had no timeout for pending orders, leaving traders in an unknown state. Without known order state, traders took actions (re-placing orders) that caused double-fills.

**Staff lesson:** Unknown order state is more dangerous than a known failure. A failed order can be retried; an unknown order leads to human intervention that often makes things worse (duplicate orders, position risk). Every order system must have an explicit "unknown" state with a defined resolution protocol (OrderStatusRequest in FIX) and a timeout that escalates unknown orders to manual review.

---

### Incident 4: Cloudflare BGP Leak Causing Trading Platform Outages (2019)

**Company:** Cloudflare (impact on multiple trading platforms)  
**What happened:** A misconfigured Verizon network accepted a BGP (Border Gateway Protocol) route leak from a small ISP, advertising itself as the best path to Cloudflare and many other major networks. This caused internet traffic to be routed through a single small ISP instead of the intended paths. Multiple trading platforms that relied on Cloudflare or the affected IP ranges became unreachable. For 2 hours, retail traders using web-based platforms could not access their accounts.

**Root cause:** BGP, the protocol that routes internet traffic between networks, has limited built-in security. A route leak can redirect traffic globally within minutes. Trading platforms relying on single network paths were vulnerable.

**Fix for trading platforms:** Multi-homed connectivity (2+ independent ISPs/network providers). BGP routing diversity so a single route leak affects only one path. Primary + backup API endpoints on different IP blocks. Users (retail traders) affected: switch to backup endpoints or mobile data (which routes through different ISPs).

**Staff lesson:** Internet routing is not guaranteed. Any system with real-money operations that depends on a single internet path is vulnerable to BGP anomalies, DDoS, or physical cable cuts. Multi-homed network architecture and geographically distributed endpoints are table stakes for financial services.

---

### Incident 5: Binance Incorrect P&L Display Causing Panic Selling (2021)

**Company:** Binance (cryptocurrency exchange)  
**What happened:** A bug in Binance's portfolio P&L calculation caused many users to see dramatically incorrect P&L values for several hours. Some users saw their portfolio show -90% P&L on positions that had barely moved. Panicked users sold their holdings at market prices during the incorrect display period. After the bug was fixed, many users discovered they had sold at a 5-10% loss unnecessarily. Binance was inundated with refund requests; they ultimately offered partial compensation.

**Root cause:** A price feed normalization bug divided prices by a factor of 10 for certain assets due to a missing decimal point conversion. The P&L calculation used the incorrect normalized price. The bug affected display only (orders routed to exchanges used correct prices from a separate feed). But users saw incorrect P&L and made financial decisions based on it.

**Staff lesson:** Portfolio display must be validated against multiple price sources before being shown to users. If the calculated P&L changes by more than 30% from the previous value in one minute, it is almost certainly a data error, not a real market move. Add circuit breakers on displayed values: if the computed value is statistically impossible (30% change in 1 minute), display the last known good value and trigger an alert.

---

## Exercises

### Exercise 1: Price Fan-Out Math

**Problem:** Your system has 50,000 active users each subscribed to 20 stocks. There are 1,000 actively traded symbols, each receiving 100 price updates per second. Calculate: (a) total price updates per second entering your system, (b) total WebSocket push messages per second if you push every update to every subscriber, (c) total WebSocket push messages per second if you throttle to one push per user per symbol per second. What is the reduction factor?

**Solution:**

```
(a) Total price updates entering:
  1,000 symbols * 100 updates/sec = 100,000 price updates/sec

(b) Total WebSocket pushes (no throttle):
  Each update must be pushed to all subscribers of that symbol.
  Users subscribed per symbol: 50,000 users * 20 stocks / 1,000 symbols = 1,000 users/symbol on average.
  Total pushes: 100,000 updates/sec * 1,000 users/symbol = 100,000,000 pushes/sec (100M/sec).
  This is completely infeasible. 100 WebSocket servers would need 1M pushes/sec each.
  Even if each push is 40 bytes: 100M * 40 = 4 GB/sec of network traffic. Saturates 10 Gbps links.

(c) Throttled to 1 push/user/symbol/second:
  Each user receives at most 1 update per symbol per second.
  Total pushes: 50,000 users * 20 subscriptions = 1,000,000 pushes/sec (1M/sec).
  At 40 bytes/push: 1M * 40 = 40 MB/sec of network traffic. Trivially manageable.

Reduction factor: 100M / 1M = 100x reduction.
At 100 updates/sec per symbol, throttling to 1/sec eliminates 99% of WebSocket traffic.
Users see a 1-second-stale price instead of real-time. For retail users: unnoticeable.

Implementation:
  Price Service: for each symbol, maintain the "latest price" in Redis.
    On every update: overwrite HSET prices:AAPL last 195.41 ts 1735000001000
  Scheduled push task (per user, per second):
    For each subscribed symbol: GET Redis latest price
    Compare to last-pushed price for this user-symbol pair
    If changed: push via WebSocket
    If unchanged: no push (no need to push the same price twice)
  
  This collapses 100 updates/sec per symbol into 0 or 1 pushes/sec per user per symbol.
```

---

### Exercise 2: Order Idempotency

**Problem:** A user submits a buy order for 10 shares of AAPL. The Order Service sends the FIX order to the broker but the network drops before receiving the acknowledgment. How does the system determine whether the order was accepted or not? Write the logic, including what FIX message to send and how to handle each possible response.

**Solution:**

```
Situation: Order submitted with client_order_id = "ORD_20241224_USER123_001"
  FIX message sent: NewOrderSingle (35=D), clOrdID = ORD_20241224_USER123_001
  TCP response: not received (timeout after 30 seconds)
  
  Order state in our DB: status = PENDING (submitted, no ack received)

Recovery step: send OrderStatusRequest (35=H)
  FIX message:
    35=H  (MsgType = OrderStatusRequest)
    11=ORD_20241224_USER123_001  (clOrdID we used)
    55=AAPL  (symbol)
    54=1  (side = Buy)

Possible broker responses (ExecutionReport, 35=8):

Response A: order is FILLED (39=2)
  ExecID=FILL_XYZ, LastPx=195.41, LastQty=10, CumQty=10
  Action: update order to FILLED. Update portfolio (holdings +10 AAPL). Debit cash $1,954.10.
  No need to re-submit.

Response B: order is WORKING (39=0 or 39=1, pending or partially filled)
  Action: order is in the exchange's order book. Monitor for fills. No action needed.

Response C: order is REJECTED (39=8)
  Text=39: "Insufficient buying power"
  Action: order failed. Refund the held cash. Notify user: "Order rejected: insufficient buying power."

Response D: order NOT FOUND (broker says no such clOrdID)
  This means our FIX message was dropped and never reached the broker.
  Action: safe to re-submit (use the same clOrdID — if it somehow reaches the broker 
  now, the duplicate check on clOrdID will prevent double-execution).
  Re-submit NewOrderSingle with clOrdID = ORD_20241224_USER123_001.

Why same clOrdID for re-submission:
  FIX standard: a broker rejects a NewOrderSingle with a duplicate clOrdID (same account + clOrdID).
  "DuplicateClOrdID" rejection with tag 39=8, text = "Duplicate order".
  So re-submitting with the same clOrdID is safe: if the first one somehow arrived, the second is rejected as a duplicate. The user's order is not doubled.

Our DB idempotency:
  On fill processing: use exec_id as the idempotency key.
  INSERT INTO processed_fills (exec_id) ON CONFLICT DO NOTHING.
  Even if we receive the fill notification multiple times (broker retry): processed only once.
```

---

## Homework

**Short 1:** Open Robinhood (or Webull, or TD Ameritrade) during market hours. Open the browser DevTools Network tab. Watch for WebSocket messages. How often are price updates pushed to you? Is it every quote change, or throttled to once per second? What does the message format look like (JSON? binary?)?

**Short 2:** Look up the "NBBO" (National Best Bid and Offer) rule. What does it require US broker-dealers to do when routing customer orders? Why does this exist? How does it affect the "best execution" obligation of a retail broker like Robinhood?

**Short 3:** Research the concept of "payment for order flow" (PFOF). Robinhood routes customer orders to market makers (Citadel Securities, Virtu Financial) who pay Robinhood for that right. What do the market makers get from this arrangement? How does this relate to the bid-ask spread on the order book?

**Deep:** Build a simplified order book:
- In-memory order book for one stock (e.g., AAPL).
- Bid side: sorted list of (price, quantity, timestamp) orders, highest price first.
- Ask side: sorted list, lowest price first.
- Implement: add_order(side, price, quantity, order_id), cancel_order(order_id).
- Implement: match_market_order(side, quantity) -> fills [(price, qty), ...].
- Test: add 10 limit orders on each side. Submit a market buy for 300 shares. What fills do you get? What does the order book look like after?
- Measure: how many orders/second can your in-memory order book process on a single CPU core?

---

## Glossary

**Order book:** The list of all pending buy (bid) and sell (ask) orders for a security, sorted by price. Maintained by the exchange. The bid-ask spread is the difference between the highest bid and lowest ask.

**Market order:** An order to buy or sell immediately at the best available price. Guaranteed to execute; price is not guaranteed.

**Limit order:** An order to buy or sell only at a specified price or better. Not guaranteed to execute; guarantees the price if executed.

**Price-time priority:** The matching rule used by most exchanges: orders at better prices execute first; orders at the same price execute in the order they were received (oldest first).

**FIX protocol:** Financial Information eXchange. The standard messaging protocol for submitting orders and receiving fills between broker-dealers, exchanges, and institutional investors. Binary extension FAST (FIX Adapted for Streaming) used for high-throughput market data.

**NBBO (National Best Bid and Offer):** The highest bid price and lowest ask price available across all US exchanges for a given security. Broker-dealers are legally required to route customer orders to the exchange offering the NBBO (or better) at the time of submission.

**Feed handler:** A component that connects to an exchange or market data vendor's data feed, parses the binary/FIX format, normalizes the data, and publishes it to an internal message bus (Kafka). The critical interface between exchange data and internal systems.

**Execution report (FIX 35=8):** The FIX message type for order status updates. Sent by the broker/exchange whenever an order changes state (accepted, rejected, filled, cancelled).

**OHLCV:** Open, High, Low, Close, Volume. The standard representation for a stock's price activity over a time period (candle). Used for chart rendering and historical analysis.

**P&L (Profit and Loss):** The gain or loss on a position. Unrealized P&L: the current value minus the purchase cost for shares still held. Realized P&L: the profit from shares already sold.

**Bid-ask spread:** The difference between the best bid (highest buyer price) and best ask (lowest seller price) in the order book. Represents the market maker's profit and the cost of immediate execution for a market order.

**T+2 settlement:** US equities settle 2 business days after the trade date. The buyer's cash is debited immediately (or held), but legal ownership of shares transfers 2 days later.

**ExecID:** A unique identifier assigned by the exchange to each fill event. Used as an idempotency key to prevent duplicate processing of fill notifications.

---

## The One-Sentence Summary

> "Stock trading feed = exchange market data (feed handler parses binary FIX/FAST → Kafka topic per symbol → Redis latest-price cache) fan-fanned-out to subscribers via WebSocket (throttled to 1 push/sec/user/symbol, not every tick) + order placement (validate buying power → atomic cash debit → submit via FIX with idempotent client_order_id → track async fills via ExecID dedup table) + real-time P&L (portfolio holdings × Redis prices, recalculated 1/sec/user, not on every tick) — the key trade-off is strong consistency for orders (funds debit must be atomic, fills must be idempotent) vs. eventual consistency for price display (100ms stale is fine for retail, catastrophic for HFT)."

---

## Interview Q&A — Most Common Cross-Questions

---

**Q1: What are the three different "stock trading systems" an interviewer might mean, and how do you tell which one they want?**

The three distinct systems are: (1) a retail trading app like Robinhood, where consumers place orders and see prices; (2) an institutional prime broker terminal like Bloomberg, with high data volume, analytics, and professional order management; and (3) an exchange matching engine like NYSE, which is the core market infrastructure that receives all orders and matches buyers with sellers. The clarifying question to ask is: "Are we designing the exchange itself, or the client application that connects to an exchange?" For L5, almost always it's the retail app. For L6, an interviewer might want you to explain the matching engine's order book design. The matching engine is the hardest of the three and involves sub-millisecond matching, the order book data structure (two sorted maps with FIFO queues), and regulatory complexity.

---

**Q2: How does real-time price data flow from the exchange to a user's app?**

The exchange emits price updates via UDP multicast at up to 1 million messages per second. Our feed handler subscribes to the vendor's normalized version of this feed, parses the binary FIX/FAST format, and publishes each price update to a Kafka topic (partitioned by symbol for ordering). A Price Service consumes from Kafka, updates Redis (`HSET prices:AAPL bid 195.40 ask 195.42 last 195.41`), and triggers a fan-out to WebSocket subscribers. The WebSocket server maintains a per-user subscription map and pushes the latest price to all users who subscribed to that symbol. To prevent fan-out from becoming 100 million messages per second, pushes are throttled to once per second per user per symbol — users see a 1-second-stale price, which is imperceptible for retail trading.

---

**Q3: What happens if a user tries to buy $10,000 of stock but only has $8,000 in their account?**

Before routing the order to the exchange, the Order Service performs a risk check: it reads the user's `available_cash` from their account and compares it to the estimated order cost (quantity × current_price × 1.01 buffer for price movement). If the estimated cost exceeds available cash, the order is rejected immediately with "Insufficient funds." This check must be atomic: we cannot read the balance, decide it's sufficient, and then debit it separately — another concurrent order could drain the balance between the read and the debit. The correct approach uses an atomic `UPDATE user_accounts SET available_cash = available_cash - cost WHERE user_id = ? AND available_cash >= cost` and checking that rows_affected = 1. If zero rows were affected, the user lacked sufficient funds at the moment of debit.

---

**Q4: How do you handle a limit order that takes hours to fill?**

When the limit order is placed, it is submitted to the exchange via FIX and stored in our database with status WORKING. The exchange adds the order to its order book. Our system waits passively — no polling needed. When the market price moves to the limit price and the order matches, the exchange sends a fill notification (FIX ExecutionReport, 35=8, OrdStatus=2) asynchronously via a callback connection we maintain with our broker. Our Order Service processes this fill: it updates the order status to FILLED, updates the user's holdings in the portfolio, reconciles the cash balance (the actual fill price may differ slightly from the estimated cost we debited). A notification is sent to the user. If the limit order is cancelled by the user or expires (good-till-date), the exchange sends a cancel confirmation and we update the order status and release the held cash.

---

**Q5: How is P&L calculated in real time?**

Portfolio P&L = Σ (shares_held × current_price − shares_held × avg_cost) across all holdings. The current_price is fetched from Redis, which is updated by the Price Service every time the exchange sends a new quote. We do not recalculate P&L on every price update for every user (that would be 50,000 price updates/sec × 1,000 subscribers per symbol = 50 million recalculations per second). Instead, we recalculate each user's P&L once per second: a scheduled task pipelines 20 Redis HGET calls (for the user's 20 holdings), computes the new P&L, and pushes it via WebSocket. 100,000 active users × 20 Redis reads = 2 million Redis reads per second — manageable. The user sees P&L accurate to within 1 second.

---

**Q6: What is the order book and what data structure implements it?**

The order book is the list of all pending buy (bid) and sell (ask) limit orders for a security, waiting to be matched. Buy orders are sorted by price descending (highest willingness to pay is at the top). Sell orders are sorted by price ascending (lowest asking price is at the top). When a new buy order arrives at a price ≥ the lowest ask, they match and a trade executes. The canonical data structure is two sorted maps (one per side), implemented as a Red-Black Tree or skip list: price is the key, and the value is a FIFO queue of orders at that price. This gives O(log N) for adding a new price level, O(1) for accessing the best bid or ask (the tree's minimum/maximum), and O(1) for order cancellation via a hash map from order_id to the order's position in the FIFO queue.

---

**Q7: How do you make sure the same fill from the exchange is not processed twice?**

The exchange (via our broker) sends fills over a persistent FIX connection with at-least-once delivery semantics. Our system may process the same fill multiple times if the connection drops and reconnects before the broker's acknowledgment is received. Each fill has a unique ExecID (FIX field 17) assigned by the exchange. Before processing a fill, the Order Service inserts the ExecID into an idempotency table: `INSERT INTO processed_fills (exec_id, processed_at) ON CONFLICT (exec_id) DO NOTHING`. If `rows_affected = 0`, this fill was already processed — skip it. If `rows_affected = 1`, process it and update holdings, cash, and order status. This table is stored in Postgres for durability — losing the dedup record on a Redis crash would allow a fill to be processed twice.

---

**Q8: How does your architecture handle pre-market and after-hours trading?**

Pre-market (4:00 AM - 9:30 AM) and after-hours (4:00 PM - 8:00 PM) trading use the same pipeline with two key differences. First, price feeds during extended hours come from electronic communication networks (ECNs) like ARCA and IEX, not the full NBBO — the feed handler connects to the extended-hours data source. Second, liquidity is much lower during extended hours: bid-ask spreads are wider and market orders can fill at far from the "expected" price. Our Order Service restricts market orders during extended hours (only limit orders accepted), warns users of the lower liquidity, and displays the extended-hours-specific bid/ask instead of the regular session's NBBO. The core technical pipeline (Kafka, Redis, WebSocket, order routing via FIX) is identical.

---

*Section 5 — L5 / Senior SWE. Frequently asked at Bloomberg, Robinhood, Coinbase, Stripe, Jane Street, and any company with financial products. Pairs with Ch58 (Payment Flow) for the order settlement and cash management layer.*

---

**Q9: What happens during a trading halt — a stock is suspended from trading?**

Exchanges issue trading halts for circuit breakers (stock dropped > 10% in 5 minutes) or regulatory halts (pending material announcement). A halt event arrives via the same FIX feed as price data: a `SecurityStatus` message (35=f) with the halt reason code. The Feed Handler parses this and publishes to Kafka topic `symbol_status`. The Price Service consumer reads this and updates Redis: `HSET symbol_status:AAPL status HALTED reason CIRCUIT_BREAKER halted_at 1700000000`. The WebSocket fan-out tier reads this status and pushes a halt notification to all subscribers. The Order Service checks symbol status before routing any order: if `symbol_status == HALTED`, reject immediately with "Trading halted — AAPL is not currently accepting orders." When the halt lifts, the `SecurityStatus` message arrives with `status=ACTIVE`, the Redis entry updates, and order routing resumes. The whole pipeline from halt announcement to user notification takes under 500ms.

---

**Q10: How do you implement a stop-loss order? The exchange doesn't hold it — your system must.**

A stop-loss is triggered when the market price crosses a threshold the user set (e.g., "sell if AAPL drops below $180"). The exchange does not hold stop orders on behalf of retail brokers — you must monitor prices and submit the order when triggered.

Implementation: store stop orders in a `pending_stop_orders` table (`user_id`, `symbol`, `stop_price`, `order_type`, `quantity`, `direction`). A Stop Order Monitor service subscribes to the `prices:{symbol}` Redis key for each symbol that has any pending stop orders. When a new price lands in Redis, the monitor queries: `SELECT * FROM pending_stop_orders WHERE symbol='AAPL' AND direction='SELL' AND stop_price >= current_price`. For each triggered order, submit a market sell to the exchange via FIX and mark the stop order as triggered.

Scale consideration: 50 symbols with pending stops × 1,000 users each = 50,000 stop orders. On a big move in AAPL, 1,000 stop orders trigger simultaneously. The monitor must issue 1,000 FIX order submissions in parallel (async) without blocking. Use an async FIX client with a thread pool bounded at 200 concurrent submissions. Orders queue internally and drain in order — acceptable, since stop orders are best-effort (market orders at current price, not time-critical to the microsecond).

---

**Q11: How does the order book matching algorithm work at the exchange level?**

The exchange order book maintains two lists: bids (buy orders, sorted by price DESC) and asks (sell orders, sorted by price ASC). Matching rule: a new buy order at price P matches the lowest ask if ask.price ≤ P. A new sell order at price P matches the highest bid if bid.price ≥ P.

```
Order book state:
  Bids (buyers):       Asks (sellers):
  $195.42 × 500       $195.45 × 300
  $195.41 × 200       $195.46 × 1,000
  $195.40 × 800       $195.48 × 200

New buy order arrives: buy 400 shares at $195.46
Match: 300 shares at $195.45 (full fill of the $195.45 ask)
       100 shares at $195.46 (partial fill of the $195.46 ask, leaves 900 remaining)

Exchange sends two ExecutionReports:
  Fill 1: ExecID=E001, 300 shares at $195.45
  Fill 2: ExecID=E002, 100 shares at $195.46
```

Data structure for the order book: `TreeMap<Price, Queue<Order>>` (Java) or `SortedDict[Decimal, deque[Order]]` (Python). The TreeMap's floor/ceiling operations find the best price in O(log N). The FIFO queue at each price level implements price-time priority: orders at the same price match in the order they arrived. Our system does not implement the order book — the exchange does. We only send orders and receive fill notifications via FIX.

---

**Q12: How do you display the portfolio performance chart — the daily percentage change graph users see on Robinhood?**

The chart shows portfolio value (in dollars) at each minute of the trading day. Three data sources:

1. **Current holdings:** `SELECT symbol, shares FROM holdings WHERE user_id=?` — the user's current portfolio composition.
2. **Intraday prices per minute:** a time-series DB (InfluxDB or TimescaleDB) with 1-minute OHLCV bars per symbol: `SELECT symbol, minute, close FROM intraday_prices WHERE symbol IN (...) AND minute >= market_open`.
3. **Previous close prices:** `SELECT symbol, close FROM daily_prices WHERE date = PREVIOUS_TRADING_DAY`.

Computation: for each minute M, portfolio value = Σ(shares_held × price_at_M). Daily percentage change at minute M = (value_at_M − value_at_open) / value_at_open × 100.

But holdings change during the day (user buys and sells). So the chart is not just prices × static holdings — it must account for trades. The correct approach: replay all trades during the day and compute a running portfolio value at each minute. This is done async in a Portfolio History Service, not in real time per request. The service pre-computes each user's minute-by-minute chart and stores it in Redis (`ZADD portfolio_history:{user_id} timestamp value_cents`). Users see the pre-computed chart. It updates every minute.

---

**Q13: How do you handle options trading differently from equities?**

Options have a fundamentally different data model: each option is defined by 4 dimensions — underlying symbol, expiration date, strike price, option type (call/put). An Apple call option expiring January 2025 at $200 strike is a different instrument from a $200 strike February 2025 call. An active equity like AAPL has 1 stock; its options chain might have 5,000 different contracts (50 strikes × 50 expiry dates × 2 call/put = 5,000).

Price feed differences: options prices arrive via the same FIX feed but with a complex symbol identifier (OSI notation: `AAPL  240119C00200000`). The feed volume is 5,000× the equity feed for a single underlying.

Order differences: options have Greeks (delta, gamma, theta, vega) that affect risk management. The Order Service must compute margin requirements using options-specific formulas (Regulation T margin for defined-risk spreads, portfolio margin for advanced accounts).

Expiration handling: options expire at market close on their expiration date. The Position Service runs a cron at 4:00 PM ET on each expiration day, auto-exercises all in-the-money long options (exercising a call = buying 100 shares at the strike price), lets out-of-the-money options expire worthless, and settles short options that were assigned.

For L5: know the data model complexity and that options require special handling. For L6: know margin calculation, expiration mechanics, and multi-leg strategy orders (spreads, straddles).

---

**Q14: How do you handle a network partition between your system and the exchange's FIX gateway?**

The FIX connection to the exchange is a persistent TCP session. If the session drops: (1) any orders in-flight that received no acknowledgment are in an unknown state — the exchange may or may not have received them. (2) fills that the exchange sent during the disconnection are buffered by the exchange and replayed when the session reconnects (FIX supports gap-fill via sequence number resync). (3) the user's view of their orders becomes stale (no updates flowing in).

Recovery sequence:
```
1. Detect disconnect: FIX heartbeat timeout (no Heartbeat message for 30 seconds)
2. Set order_service status = DEGRADED (reject new order submissions)
3. Log all in-flight orders (orders submitted but not yet acknowledged)
4. Reconnect to FIX gateway (TCP reconnect with sequence number reset)
5. Send Resend Request for any missed sequence numbers during the gap
6. Process replayed messages: fills, order acknowledgments, rejects
7. Reconcile in-flight orders: for each, check if exchange has an open order record
8. Mark order_service status = HEALTHY
9. Notify affected users: "Your order status may have been temporarily delayed"
```

For orders that received no acknowledgment: the Order Service must query the exchange's order status endpoint (`OrderStatusRequest`, FIX 35=H) after reconnect to determine whether each order was received and processed.

---

**Q15: What are the key regulatory constraints that shape your architecture?**

**Regulation NMS (US equities):** Requires executing orders at the best available price across all exchanges (National Best Bid and Offer — NBBO). Our order routing layer must subscribe to the consolidated NBBO feed and route orders to the exchange currently offering the best price, not always the same venue.

**FINRA Rule 4370 (Business Continuity Plan):** Requires a documented plan for system failures. Architecturally: hot-standby Order Service with automatic failover, FIX session backup via secondary line (different ISP), and a read-only "view portfolio" mode during order service outages.

**PCI-DSS (payment card data):** Credit card numbers used to fund accounts must be stored only in a PCI-compliant vault (e.g., Stripe's vault). The trading system stores only a tokenized reference (payment_method_id), never the raw card number.

**SEC Rule 17a-4 (record retention):** All order records, trade confirmations, and account statements must be retained for 6 years and be immediately accessible for 2 years. Use immutable object storage (S3 with Object Lock in COMPLIANCE mode — prevents deletion even by admins) for all transaction records.

**Pattern Day Trader (PDT) rule:** Accounts with < $25,000 in equity are limited to 3 day-trades in a rolling 5-day period. The Order Service must count day-trades (opening and closing the same position on the same day) and reject orders that would violate PDT. This requires a rolling 5-day trade history lookup at order placement time.

---

## Monitoring and Observability

### Key Metrics by Subsystem

**Market data pipeline:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `feed_handler_lag_ms` | < 5ms | > 50ms (feed handler falling behind exchange) |
| `kafka_consumer_lag_messages` per symbol | < 1,000 | > 10,000 (price service lagging) |
| `redis_price_staleness_ms` | < 1,000ms | > 5,000ms (price in Redis is 5s behind exchange) |
| `symbol_status_change_latency_ms` | < 500ms | > 2,000ms (halt notification too slow) |

**Order placement:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `order_submission_latency_p99_ms` | < 200ms | > 1,000ms (FIX gateway degraded) |
| `order_rejection_rate_%` | < 5% | > 20% (exchange rejecting orders — check risk rules) |
| `fix_session_reconnects_per_hour` | 0 | > 2 (unstable FIX connection) |
| `funds_hold_discrepancy_count` | 0 | > 0 (funds debited but order not submitted, or vice versa) |

**P&L and portfolio:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `pnl_recalc_latency_p99_ms` | < 500ms | > 2,000ms (Redis pipeline bottleneck) |
| `portfolio_value_staleness_sec` | < 2s | > 10s (P&L shown to user is significantly stale) |
| `fill_dedup_collision_rate` /hr | < 1 | > 10 (exchange replaying fills excessively) |

**WebSocket fan-out:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `websocket_connected_users` | varies | Drop > 10% in 60s (mass disconnect event) |
| `price_push_latency_p99_ms` | < 200ms | > 1,000ms (fan-out thread pool saturated) |
| `subscriptions_per_connection` | 1–50 | > 500 (one user subscribed to too many symbols) |

### Distributed Trace: Order Placement Flow

```
Trace: place_order (order_id = client_order_id)
  ├─ Span 1: api_gateway (POST /orders)              3ms
  ├─ Span 2: account_lock (SELECT ... FOR UPDATE)    5ms   ← funds check here
  ├─ Span 3: funds_debit (UPDATE available_cash)     4ms
  ├─ Span 4: order_persist (INSERT into orders)      6ms
  ├─ Span 5: fix_submit (FIX NewOrderSingle)         45ms  ← exchange round-trip
  └─ Span 6: order_ack_receive (ExecID logged)       2ms
```

Alert on: Span 3 rows_affected=0 rate > 1% (funds debit failures), Span 5 > 500ms (FIX latency spike), no Span 6 within 5s after Span 5 (order sent but not acknowledged — potential in-flight unknown order).

---

## Capacity Planning — Retail Trading App at Scale

**Assumptions:** 5M registered users, 500K daily active users, 100K concurrent users during peak (market open 9:30 AM ET).

**Price feed volume:**
```
500 tradeable symbols × 100 ticks/sec each = 50,000 tick/sec
Feed handler: single process handles 50,000 msgs/sec (CPU-bound, needs dedicated core)
Kafka: 50,000 msgs/sec × 200 bytes/msg = 10 MB/sec (trivial for Kafka)
Redis price writes: 50,000 HSET/sec on 500 keys → Redis handles at ~50% capacity (comfortable)
```

**WebSocket fan-out:**
```
100K concurrent users × avg 10 subscriptions each = 1M symbol-subscriptions
50,000 ticks/sec × 1M/500 symbols subscriptions per symbol = 100,000 pushes/sec
But throttled to 1 push/sec/user/symbol:
  100K users × 10 symbols = 1M pushes/sec max
  Each push: 100 bytes → 100 MB/sec total WebSocket egress = 800 Mbps
  WebSocket servers: 10 servers × 10K connections × 100 KB/sec = 10 Gbps (need 10× 1 Gbps NIC servers)
```

**P&L recalculation:**
```
100K active users × 1 recalc/sec = 100K recalcs/sec
Each recalc: pipeline 20 HGET calls to Redis = 2M Redis reads/sec
Redis cluster: 3 read replicas, 2M/3 = 667K reads/sec each (comfortable at < 50% capacity)
```

**Order placement:**
```
Market open burst: 500K users × 10% placing orders in first 5 min = 50K orders
50K orders / 300 sec = 167 orders/sec (very manageable)
Each order: 1 Postgres UPDATE + 1 INSERT + 1 FIX submission
Postgres: 334 writes/sec (2× for UPDATE + INSERT) — trivial for a single PG instance
FIX gateway: 167 NewOrderSingle/sec — typical FIX session handles 10K msg/sec
```

**Fill processing:**
```
167 orders/sec × 95% fill rate × avg 1.2 fills/order = 190 fills/sec
Each fill: INSERT INTO processed_fills (idempotency) + UPDATE holdings + UPDATE cash
DB: 570 writes/sec — trivial
Kafka fill events to downstream: 190 events/sec, 3 consumers (P&L, notifications, audit)
```

**Storage sizing:**
```
Orders table:      500K DAU × 2 orders/user/day × 365 days = 365M rows/year
                   365M × 500 bytes = 182 GB/year → partition by year, archive to S3
Filled orders:     180M fills/year × 400 bytes = 72 GB/year
Price history:     500 symbols × 390 trading days × 8h × 3600 sec × 100 Hz = 561B ticks/year
                   NOT stored raw — downsample to 1-min OHLCV bars: 500 × 390 × 8h × 60min × 20 bytes = 1.8 GB/year
```

---

## Common Anti-Patterns

**Anti-pattern 1: Reading balance and debiting in two separate statements**
```sql
-- WRONG: race condition between check and debit
SELECT available_cash FROM accounts WHERE user_id = 123;  -- returns $5,000
-- concurrent order drains to $4,500 here --
UPDATE accounts SET available_cash = available_cash - 5000 WHERE user_id = 123;
-- balance goes to -$500! Oversold.
```
Fix: `UPDATE accounts SET available_cash = available_cash - 5000 WHERE user_id = 123 AND available_cash >= 5000`. Check rows_affected=1.

**Anti-pattern 2: Recalculating P&L on every tick**
```python
# WRONG: O(users × symbols) recalculation on every price update
def on_price_update(symbol, price):
    for user in all_users_holding(symbol):  # could be 100,000 users
        recalculate_portfolio_pnl(user)  # DB read per user!
# 100 ticks/sec × 100K users = 10M DB reads/sec -- impossible
```
Fix: Recalculate P&L on a schedule (1/sec per user) via a background job, not on every tick. The user sees P&L accurate within 1 second, which is imperceptible.

**Anti-pattern 3: No ExecID deduplication**
```python
# WRONG: processing fills without idempotency check
def on_fill(exec_id, shares, price):
    update_holdings(shares, price)  # applies again on replay!
    update_cash_balance(shares * price)
```
Fix: `INSERT INTO processed_fills (exec_id) ON CONFLICT DO NOTHING`. If rows_affected=0, skip. If =1, process. Guarantees exactly-once fill processing even with FIX session reconnects that replay fills.

**Anti-pattern 4: Trusting client-sent price for order cost calculation**
```python
# WRONG: client sends estimated price
def place_order(symbol, quantity, client_price_estimate):
    cost = quantity * client_price_estimate  # malicious client sends $0.01
    if account.cash >= cost:
        submit_order(symbol, quantity)
```
Fix: Always fetch current price from Redis (your own internal price, not client-provided) for risk checks. The actual fill price comes from the exchange and is reconciled after the fill confirmation — not pre-determined by the client.

**Anti-pattern 5: Fan-out pushes on every tick (no throttle)**
```python
# WRONG: push to all subscribers on every exchange tick
def on_tick(symbol, price):
    for user in subscribers[symbol]:  # 100,000 users × 100 ticks/sec = 10M pushes/sec
        websocket.send(user, price)
```
Fix: Throttle to 1 push/sec/user/symbol. Use a "dirty flag" per subscription: mark dirty on each tick, flush once per second in a periodic task.

**Anti-pattern 6: Submitting orders before receiving ACK on prior order**
```
# WRONG: fire-and-forget FIX submission without tracking in-flight
submit_fix_order(order_1)
submit_fix_order(order_2)  # FIX gateway may still be processing order_1
# Sequence number violation → FIX session disconnects
```
Fix: FIX requires strict sequence number ordering. Use a single serial FIX session with a queue for outgoing messages. Or use separate FIX sessions per user/portfolio (each has its own sequence space).

---

## Production Incident Deep Dives (Extended)

### Incident 6: Robinhood March 2020 Outage — DNS + ETCD Exhaustion

**Date:** March 2-3, 2020 (first week of COVID-19 market crash)
**Duration:** ~17 hours across two days

**What happened:** The market crash triggered an unprecedented trading volume — 4-5× normal. The surge in WebSocket connections overwhelmed Robinhood's service discovery infrastructure. The system used etcd (a distributed key-value store) for service registration. Under the connection spike, DNS servers and etcd began experiencing high query rates from service health checks (each new WebSocket connection triggered a service lookup). The etcd cluster became CPU-saturated, causing health check timeouts. Services marked each other as unhealthy, triggering cascading circuit breaker openings across the entire service mesh. The order service, price service, and account service all became unreachable to each other simultaneously.

Ironically, the underlying trading infrastructure (FIX connections, exchange connectivity) was healthy throughout. Users could not trade not because the exchange was down, but because the internal service discovery layer collapsed.

**Root cause:** (1) etcd health check storm: N services × M replicas × health-check-every-5s = O(N²) checks under load. (2) DNS TTL set to 5 seconds — under load, DNS clients re-resolved every 5 seconds instead of caching. (3) No connection pooling between services — every WebSocket accept spawned 3-4 internal HTTP connections.

**Fixes:**
1. **Increase health check interval** to 30 seconds under high load (adaptive health check backoff).
2. **DNS TTL to 60 seconds** for internal service records. Services tolerate 60s stale DNS entries during crashes.
3. **Service mesh connection pooling:** all instances of Service A maintain a pre-warmed pool of 10 connections to Service B. New requests reuse existing connections instead of opening new ones.
4. **etcd isolation:** separate etcd clusters for service discovery vs. distributed locks. Service discovery etcd has no other write load.

**Lesson:** Service infrastructure (service discovery, health checks) must be designed to handle load spikes proportional to traffic spikes, not absolute load. A 5× traffic spike causing a 25× increase in etcd queries is a quadratic scaling failure.

---

### Incident 7: Binance P&L Display Bug — Price Feed Latency Mismatch (2021)

**Date:** Multiple incidents in 2021
**Impact:** Users saw incorrect (sometimes dramatically wrong) P&L values for 10-30 minutes

**What happened:** Binance's price feed for certain altcoins (low-liquidity pairs) had update intervals of 30-60 seconds during low-activity periods. The P&L calculation service used the latest Redis price (updated from this same feed). When the feed was delayed, users' P&L showed the 30-60 second stale price — which for volatile altcoins could be 5-10% off. Worse: during high volatility, the price feed would receive a burst of 50 updates in 1 second after a 30-second gap. The P&L service processed these sequentially — during the processing burst, different users' P&L was computed with prices from different points in the 30-second window, making comparisons between users inconsistent.

**Root cause:** No `price_freshness_timestamp` stored alongside the price in Redis. The P&L service had no way to know if the price it was reading was current or 60 seconds stale.

**Fix:**
```
Redis price structure updated:
HSET prices:ALTCOIN bid 0.00123 ask 0.00124 last 0.00123 
             updated_at 1700000000 exchange_sequence 9999

P&L service:
  price = redis.hgetall("prices:ALTCOIN")
  staleness = current_time - price['updated_at']
  if staleness > 30_seconds:
    # Show price with "Delayed" indicator in UI
    portfolio_value_display = compute_value(price) + " (price delayed)"
  if staleness > 120_seconds:
    # Don't show P&L at all — too unreliable
    portfolio_value_display = "Price unavailable"
```

The UI now shows a "Delayed" badge on any holding whose price is more than 30 seconds old. Users understand the P&L is approximate during low-liquidity periods.

**Lesson:** Always store the timestamp of the price update alongside the price itself. Never compute financial metrics from prices of unknown age.

---

## Additional Exercises

### Exercise 4: Stop-Loss Monitor Design

**Problem:** 1 million users each have an average of 3 stop-loss orders active at any time (3 million pending stops total). At 9:30 AM market open, AAPL drops 5% in 10 seconds, triggering 50,000 AAPL stop orders simultaneously. Design a stop order monitor that can process 50,000 triggers in under 2 seconds.

**Solution:**

```
Data structure:
  Redis ZSET per symbol: "stops:AAPL"
  Score = stop_price (float)
  Member = order_id

  When user creates stop: ZADD stops:AAPL stop_price order_id
  When user cancels stop: ZREM stops:AAPL order_id

  When AAPL price drops to $180.00:
    ZRANGEBYSCORE stops:AAPL 0 180.00  -- all stops with trigger price ≤ current price
    Returns: [order_id_1, order_id_2, ..., order_id_50000]

Processing 50,000 triggered stops:
  Batch: split into 250 batches of 200 orders each
  Parallel: spawn 50 goroutines (or 50 async tasks), each handling 5 batches
  
  For each triggered order:
    1. Load order details from DB (or Redis cache): user_id, shares, order_type
    2. Submit FIX MarketOrder (NewOrderSingle) for the user
    3. Mark stop order as TRIGGERED in DB
    4. ZREM stops:AAPL order_id

FIX submission rate:
  50,000 FIX messages in 2 seconds = 25,000 msg/sec
  Standard FIX session limit: 10,000 msg/sec
  Solution: maintain 3 parallel FIX sessions to the exchange
  Each handles 8,333 msg/sec = 50,000 total in ~2 seconds ✓

Database load:
  50,000 UPDATE stops SET status='TRIGGERED' WHERE order_id IN (...)
  Batch into groups of 1,000: 50 UPDATE statements
  Postgres handles 50 batch updates/sec easily

Why ZSET and not a DB query?
  DB query: SELECT * FROM stops WHERE symbol='AAPL' AND stop_price >= 180.00
  With index: O(log N + K) where K=50,000 — same complexity but Redis is in-memory
  DB adds ~5ms per query vs Redis <1ms: matters when checking 500 symbols × 10/sec = 5,000 checks
```

---

### Exercise 5: Real-Time P&L Under Rapid Position Changes

**Problem:** A day trader places 20 orders in 30 seconds (scalping strategy). Each fill changes their holdings. Meanwhile the P&L recalculation job runs every 1 second. How do you ensure P&L reflects the latest fills without race conditions?

**Solution:**

```python
# Holdings stored in Redis for real-time access:
# HSET holdings:{user_id} AAPL 100 TSLA 50 MSFT 200

# Fill processing updates holdings atomically:
def process_fill(user_id, symbol, shares_delta, fill_price):
    pipeline = redis.pipeline()
    pipeline.hincrbyfloat(f"holdings:{user_id}", symbol, shares_delta)
    pipeline.hset(f"cash:{user_id}", "available",
                  current_cash - shares_delta * fill_price)
    pipeline.execute()  # atomic pipeline
    
    # Also update DB for durability:
    db.execute("""
        INSERT INTO fills (user_id, symbol, shares, price, filled_at)
        VALUES (?, ?, ?, ?, NOW())
    """, [user_id, symbol, shares_delta, fill_price])

# P&L recalculation (1/sec):
def recalculate_pnl(user_id):
    holdings = redis.hgetall(f"holdings:{user_id}")  # {'AAPL': '100', 'TSLA': '50'}
    
    # Pipeline all price lookups:
    pipeline = redis.pipeline()
    for symbol in holdings:
        pipeline.hget(f"prices:{symbol}", "last")
    prices = pipeline.execute()  # one round trip
    
    pnl = sum(
        int(holdings[sym]) * float(price) - avg_cost_basis(user_id, sym)
        for sym, price in zip(holdings, prices)
        if price is not None
    )
    redis.set(f"pnl:{user_id}", pnl, ex=10)  # cache for 10s
    return pnl

# Race condition analysis:
# If a fill arrives during P&L calculation:
#   1. Fill updates holdings atomically (Redis pipeline)
#   2. P&L calc reads holdings snapshot (HGETALL is atomic in Redis — consistent snapshot)
#   3. Worst case: fill occurs between HGETALL and price reads → P&L is 1-tick off for 1 recalc cycle
#   4. Next 1-second cycle picks up the correct holdings
# Acceptable: 1-second maximum P&L staleness, never negative balance
```

---

## L5 vs L6 Calibration Table — Stock Trading Feed

| Topic | L5 Answer | L6/Staff Answer |
|-------|-----------|-----------------|
| Market data pipeline | Feed handler → Kafka → Redis → WebSocket throttled 1/sec/user | Plus: NBBO aggregation across multiple exchanges; co-location for sub-millisecond latency; UDP multicast fan-out for institutional clients |
| Price fan-out | Throttle to 1 push/sec/user/symbol via dirty flag | Plus: delta-encoded binary frames to reduce bandwidth; per-user symbol prioritization (positions are high-priority, watchlist is low-priority); LL-WebSocket for sub-100ms price delivery to premium users |
| Order placement | Atomic cash debit (UPDATE WHERE available_cash >= cost); FIX submission with client_order_id | Plus: pre-trade risk checks (PDT rule, short-selling uptick rule, margin calculation); smart order router for Reg NMS best-execution compliance; FIX session failover with in-flight order reconciliation |
| Fill idempotency | INSERT processed_fills ON CONFLICT DO NOTHING | Plus: FIX sequence number resync on reconnect; multi-leg fill correlation (options strategy fills arrive as separate ExecIDs that must be linked to the parent spread order) |
| P&L calculation | Redis HGET pipeline per user, 1/sec | Plus: position-weighted Greeks for options (delta, gamma, vega per holding); cross-currency P&L normalization; cost basis lot selection (FIFO vs specific lot for tax optimization) |
| Stop orders | Monitor ZSET by symbol; trigger on price cross | Plus: trailing stops (stop_price updates as price moves favorably); bracket orders (linked entry + stop + target); OCO (one-cancels-other) linked order pairs |
| Trading halt handling | Check symbol_status in Redis; reject orders with clear message | Plus: regulatory halt vs. exchange halt distinction; resume order re-submission after halt lifted; cancelled-on-halt notification to users with resting limit orders |
| Audit/compliance | Kafka event log; immutable S3 storage | Plus: FINRA Rule 4370 BCP compliance; SEC Rule 17a-4 WORM storage; PDT rule enforcement at order time; AML (anti-money-laundering) pattern detection in trade history |
| Disaster recovery | Hot standby Order Service; read-only mode during failover | Plus: RPO < 1 second (no confirmed orders can be lost); FIX session state replication; multi-broker connectivity (failover to backup prime broker within 30 seconds) |

---

## Additional Exercises

### Exercise 6: Order Book Snapshot and Incremental Update Feed

**Problem:** Your system receives an exchange's market data in two forms: (1) a full order book snapshot at startup (all bids and asks at that moment), then (2) incremental updates (adds, cancels, modifications). Design the data structure to apply incremental updates correctly.

**Solution:**

```python
from sortedcontainers import SortedDict
from collections import defaultdict, deque
import heapq

class OrderBook:
    def __init__(self):
        # Bids: price → SortedDict (price DESC, so negate for ascending ZSET)
        # Asks: price → SortedDict (price ASC)
        self.bids = SortedDict()   # {-price: {order_id: Order}}
        self.asks = SortedDict()   # {price: {order_id: Order}}
        
        # Fast lookup: order_id → (side, price) for cancellations
        self.order_index = {}      # {order_id: {'side': 'bid'|'ask', 'price': Decimal}}
        
        # Sequence number tracking
        self.last_seq = 0

    def apply_snapshot(self, bids_list, asks_list, seq_number):
        """Apply a full book snapshot. Called at startup or after gap."""
        self.bids.clear()
        self.asks.clear()
        self.order_index.clear()
        
        for order in bids_list:
            price_key = -order['price']  # negate for descending sort
            if price_key not in self.bids:
                self.bids[price_key] = {}
            self.bids[price_key][order['order_id']] = order
            self.order_index[order['order_id']] = {'side': 'bid', 'price': order['price']}
        
        for order in asks_list:
            if order['price'] not in self.asks:
                self.asks[order['price']] = {}
            self.asks[order['price']][order['order_id']] = order
            self.order_index[order['order_id']] = {'side': 'ask', 'price': order['price']}
        
        self.last_seq = seq_number

    def apply_update(self, update, seq_number):
        """Apply incremental update. Must arrive in order (seq_number == last_seq + 1)."""
        if seq_number != self.last_seq + 1:
            # Sequence gap detected! Request new snapshot.
            raise SequenceGapError(f"Expected {self.last_seq + 1}, got {seq_number}")
        
        self.last_seq = seq_number
        
        if update['type'] == 'ADD':
            self._add_order(update)
        elif update['type'] == 'CANCEL':
            self._cancel_order(update['order_id'])
        elif update['type'] == 'MODIFY':
            self._cancel_order(update['order_id'])
            self._add_order(update)  # re-add at new price/quantity
    
    def _add_order(self, order):
        if order['side'] == 'bid':
            price_key = -order['price']
            if price_key not in self.bids:
                self.bids[price_key] = {}
            self.bids[price_key][order['order_id']] = order
            self.order_index[order['order_id']] = {'side': 'bid', 'price': order['price']}
        else:  # ask
            if order['price'] not in self.asks:
                self.asks[order['price']] = {}
            self.asks[order['price']][order['order_id']] = order
            self.order_index[order['order_id']] = {'side': 'ask', 'price': order['price']}
    
    def _cancel_order(self, order_id):
        info = self.order_index.pop(order_id, None)
        if info is None:
            return  # Already removed (idempotent)
        
        if info['side'] == 'bid':
            price_key = -info['price']
            price_level = self.bids.get(price_key, {})
            price_level.pop(order_id, None)
            if not price_level:
                self.bids.pop(price_key, None)  # Remove empty price level
        else:
            price_level = self.asks.get(info['price'], {})
            price_level.pop(order_id, None)
            if not price_level:
                self.asks.pop(info['price'], None)
    
    def best_bid(self):
        if not self.bids:
            return None
        price_key, orders = self.bids.peekitem(0)  # smallest key = most negative = highest bid
        return -price_key, orders
    
    def best_ask(self):
        if not self.asks:
            return None
        price, orders = self.asks.peekitem(0)  # smallest price = best ask
        return price, orders

# Sequence gap handling:
# If a gap is detected (seq_number skipped), the order book state is inconsistent.
# The feed handler must request a new full snapshot from the exchange.
# During re-snapshot: buffer all incoming updates (do not apply them yet).
# After snapshot is applied: replay buffered updates from snapshot_seq + 1 onward.
```

---

### Exercise 7: WebSocket Price Throttle with Dirty Flag

**Problem:** AAPL price updates at 100 ticks/second. You have 50,000 subscribers for AAPL. Design the throttle so each subscriber receives at most 1 update/second, without creating 50,000 timers.

**Solution:**

```python
import asyncio
from collections import defaultdict

class PriceThrottler:
    def __init__(self, push_interval_sec=1.0):
        # dirty[symbol][user_id] = latest_price (overwritten on each tick)
        self.dirty = defaultdict(dict)  # {symbol: {user_id: latest_price}}
        self.push_interval = push_interval_sec
        
        # Start the single flush task (replaces 50,000 individual timers)
        asyncio.create_task(self._flush_loop())
    
    def on_tick(self, symbol: str, price: float):
        """Called 100 times/sec for AAPL. Just marks dirty — no I/O."""
        for user_id in self.get_subscribers(symbol):
            self.dirty[symbol][user_id] = price
        # O(subscribers) mark — but no network I/O here
    
    async def _flush_loop(self):
        """Single coroutine that wakes up every 1 second and pushes all dirty prices."""
        while True:
            await asyncio.sleep(self.push_interval)
            await self._flush_all()
    
    async def _flush_all(self):
        """Push latest price to all subscribers with dirty prices. O(total_dirty)."""
        to_push = {}  # {symbol: {user_id: price}}
        
        # Atomic snapshot: swap dirty with empty dict
        for symbol in list(self.dirty.keys()):
            if self.dirty[symbol]:
                to_push[symbol] = self.dirty.pop(symbol)
        
        # Push via WebSocket (gather = parallel)
        push_tasks = []
        for symbol, user_prices in to_push.items():
            for user_id, price in user_prices.items():
                ws = self.get_websocket(user_id)
                if ws and ws.open:
                    push_tasks.append(ws.send(f'{{"symbol":"{symbol}","price":{price}}}'))
        
        if push_tasks:
            await asyncio.gather(*push_tasks, return_exceptions=True)
    
    # Performance analysis:
    # AAPL at 100 ticks/sec, 50K subscribers:
    #   on_tick(): 50K dict writes/tick × 100 ticks/sec = 5M dict writes/sec (CPU-bound, fast)
    #   _flush_all(): 50K WebSocket sends/sec (once per second)
    # 
    # vs. naive approach (push on every tick):
    #   50K sends × 100 ticks/sec = 5M WebSocket sends/sec → impossible
    #
    # vs. 50K individual 1-second timers:
    #   50K asyncio timers = 50K coroutines sleeping simultaneously → high memory overhead
    #   One flush coroutine: 1 timer, O(total_dirty) work → much more efficient

    def get_subscribers(self, symbol):
        # Returns set of user_ids subscribed to this symbol
        # Stored in Redis: SMEMBERS subscriptions:{symbol}
        return self.subscription_cache.get(symbol, set())
    
    def get_websocket(self, user_id):
        # Returns WebSocket connection for user (or None if disconnected)
        return self.ws_connections.get(user_id)
```

---

### Exercise 8: Portfolio Reconciliation at End of Day

**Problem:** At 4:00 PM ET (market close), reconcile your internal records against the broker's official end-of-day position report. The broker sends a file with each user's holdings. Design the reconciliation to detect discrepancies and flag them for manual review.

**Solution:**

```python
def reconcile_eod_positions(broker_report_path):
    """
    Run at 4:15 PM ET (15 minutes after market close).
    broker_report_path: path to broker's CSV file {account_id, symbol, shares, avg_cost}
    """
    discrepancies = []
    
    # Step 1: Parse broker's official report
    broker_positions = {}
    with open(broker_report_path) as f:
        for row in csv.DictReader(f):
            key = (row['account_id'], row['symbol'])
            broker_positions[key] = {
                'shares': Decimal(row['shares']),
                'avg_cost': Decimal(row['avg_cost'])
            }
    
    # Step 2: Load our internal records
    our_positions = db.query("""
        SELECT account_id, symbol, 
               SUM(shares_delta) as total_shares,
               AVG(fill_price) as avg_cost
        FROM position_changes
        WHERE trade_date = CURRENT_DATE
           OR settled = false
        GROUP BY account_id, symbol
        HAVING SUM(shares_delta) != 0
    """)
    
    # Step 3: Compare
    for pos in our_positions:
        key = (pos['account_id'], pos['symbol'])
        broker_pos = broker_positions.get(key)
        
        if broker_pos is None:
            discrepancies.append({
                'type': 'MISSING_AT_BROKER',
                'account': pos['account_id'],
                'symbol': pos['symbol'],
                'our_shares': pos['total_shares']
            })
            continue
        
        share_diff = pos['total_shares'] - broker_pos['shares']
        if abs(share_diff) > Decimal('0.001'):  # 0.001 share tolerance for fractional shares
            discrepancies.append({
                'type': 'SHARE_MISMATCH',
                'account': pos['account_id'],
                'symbol': pos['symbol'],
                'our_shares': pos['total_shares'],
                'broker_shares': broker_pos['shares'],
                'difference': share_diff
            })
    
    # Step 4: Check broker has positions we don't have (missed fills)
    our_keys = {(pos['account_id'], pos['symbol']) for pos in our_positions}
    for key, broker_pos in broker_positions.items():
        if key not in our_keys and broker_pos['shares'] != 0:
            discrepancies.append({
                'type': 'MISSING_IN_OUR_RECORDS',
                'account': key[0],
                'symbol': key[1],
                'broker_shares': broker_pos['shares']
            })
    
    # Step 5: Report
    if not discrepancies:
        log.info("EOD reconciliation: all positions match broker report")
        return
    
    log.error(f"EOD reconciliation: {len(discrepancies)} discrepancies found")
    for d in discrepancies:
        alert_ops(f"RECONCILIATION FAIL: {d}")
        db.insert("reconciliation_errors", {**d, "detected_at": NOW(), "resolved": False})
    
    # Auto-resolve small rounding discrepancies (< 0.01 shares, likely floating point)
    for d in discrepancies:
        if d['type'] == 'SHARE_MISMATCH' and abs(d['difference']) < Decimal('0.01'):
            db.update("holdings", {"shares": d['broker_shares']},
                     {"account_id": d['account'], "symbol": d['symbol']})
            log.info(f"Auto-resolved rounding discrepancy for {d['account']}/{d['symbol']}")
```

---

## Key Interview Signals — What L5 Looks Like In the Room

**Signal 1: You immediately ask "exchange, broker, or retail app?" before designing.**
A trading feed interview can mean three completely different systems. L5 candidates clarify scope in their first sentence, before drawing a single box. Not asking is a signal that you don't know these are different systems — a significant gap for any financial services company.

**Signal 2: You explain throttling with the dirty-flag pattern, not individual timers.**
"We push prices to users once per second" is a requirement. The implementation matters: 50,000 per-user timers is O(N) memory and a scheduling nightmare. The dirty-flag + single flush loop is O(1) infrastructure regardless of subscriber count. L5 candidates give the implementation when asked about throttling, not just the policy.

**Signal 3: You give the atomic cash debit pattern without needing a hint.**
When describing order placement, the L5 answer includes: "the funds hold and the order submission must be atomic at the application layer — we use `UPDATE accounts SET available_cash = available_cash - cost WHERE available_cash >= cost` and check rows_affected, not a separate check-then-debit." Candidates who skip this are leaving the interviewer to probe for it.

**Signal 4: You distinguish the three delivery semantics and state which each component uses.**
At-most-once (UDP price multicast from exchange), at-least-once (FIX fill notifications — may replay on reconnect, requires ExecID dedup), exactly-once (order submissions — use client_order_id). Different parts of the system have different delivery needs, and knowing which component gets which treatment shows you understand that "reliability" is not a binary property.

**Signal 5: You bring up regulatory constraints without being asked.**
At any company with financial products, ignoring regulations is not "out of scope" — it's a red flag. PDT rule, Reg NMS best execution, SEC record retention, PCI-DSS for card data — mentioning at least one or two of these unprompted signals that you understand financial systems are regulated systems, and that your design must accommodate those constraints. It's a strong L5 signal because most candidates treat regulations as "someone else's problem."

---

## Related Topics to Review After This Chapter

- **Ch58 (Payment Flow):** The order settlement layer — how cash moves from user account to brokerage and how trades settle T+2 (two business days after execution). The ticketing saga pattern (hold → charge → confirm) maps directly to the trading equivalent (funds hold → order submission → fill confirmation).
- **Ch60 (Real-Time Chat / WebSocket at Scale):** The WebSocket fan-out architecture for price delivery is identical to real-time chat delivery. If you understand price throttling (dirty flag + flush loop), you understand message delivery batching.
- **Ch61f (Leaderboard — Redis ZSET):** The stop-loss monitor ZSET (`ZADD stops:AAPL stop_price order_id` + `ZRANGEBYSCORE` on price cross) is the same Redis ZSET pattern used in leaderboards. Different domain, same data structure.
- **Ch33 (Caching at Scale):** Redis as a price cache (HSET prices:AAPL bid ask last) and portfolio cache (HSET holdings:{user_id}) follows the same cache-aside pattern covered in the caching chapter. Review TTL strategy, cache-warm-up, and cache-invalidation patterns there.
- **FIX Protocol primer (external reading):** Search "FIX protocol tutorial for developers." Understanding message types 35=D (NewOrderSingle), 35=8 (ExecutionReport), and 35=H (OrderStatusRequest) at a conceptual level is expected knowledge for interviews at trading firms. You don't need to memorize field numbers, but you should know what information flows in each direction and why the protocol uses sequence numbers.
