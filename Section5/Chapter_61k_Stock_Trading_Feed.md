# Chapter 61k: Stock / Trading Feed — Market Data at Low Latency

> The New York Stock Exchange processes 8 billion messages per day.
> A stock price update that arrives 1 millisecond late can cost a trading
> firm millions of dollars. This is the system design problem where
> latency is measured in microseconds, not milliseconds.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

Stock and trading system design is asked at financial technology companies
(Bloomberg, Jane Street, Citadel, Robinhood, Coinbase, Two Sigma), fintech
startups, and increasingly at big tech companies with financial products
(Google Pay, Apple Pay, Stripe, PayPal). It teaches low-latency architecture,
order book design, and real-time fan-out at extreme throughput — all of which
transfer to other low-latency pub/sub systems.

---

## Planned Content

### Part 1: Requirements and Scale
- Users see real-time stock prices; can place buy/sell orders; view order history
- Functional: real-time price feed, order placement, order book view, trade execution, portfolio view
- Non-functional: price updates < 100ms to end users, order matching < 1ms, 99.99% uptime
- Scale: 10,000 stocks, 1M price updates/sec (during peak), 100K orders/sec
- Scope for L5: retail trading app (Robinhood-style) — not HFT (high-frequency trading)
- Not in scope: HFT infrastructure, exchange-side matching engine, regulatory reporting

### Part 2: The Order Book — Core Data Structure
- Order book: all pending buy and sell orders for one stock, sorted by price
- Bid side: buy orders, sorted by price descending (highest bid at top)
- Ask side: sell orders, sorted by price ascending (lowest ask at top)
- Spread: difference between highest bid and lowest ask
- Match: when bid price ≥ ask price → trade executes at ask price
- Price-time priority: at same price, earlier order executes first
- Data structure: two sorted lists (one per side) — Red-Black Tree or skip list
  - O(log N) insert/cancel, O(1) peek at best bid/ask

### Part 3: Market Data Feed — Real-Time Price Updates
- Exchange sends price updates via UDP multicast (not TCP — too slow for 1M/sec)
- Feed handler: subscribes to exchange multicast feed → parses binary FIX/FAST protocol → normalizes to internal format
- L5 scope: exchange feed is external; your job is to consume it and distribute to users
- Internal distribution: Kafka topic per stock (10,000 topics) or single topic with stock_id key
- Consumer: price update service reads from Kafka → updates Redis (key = stock_id, value = latest price)
- User feed: WebSocket connection per user → server pushes price updates for subscribed stocks

### Part 4: Order Placement and Execution
- User places order → order service validates (sufficient funds, valid symbol, valid quantity)
- Order types: market order (execute now at best price), limit order (execute only at price ≤ X)
- Debit funds immediately on order placement (prevent insufficient funds mid-execution)
- Route to exchange: submit order via FIX protocol to exchange's order gateway
- Exchange response: order ID, status (ACCEPTED/REJECTED), fill price if executed immediately
- Async fills: limit orders may not fill immediately → exchange sends fill notifications asynchronously
  → order service processes fills → update portfolio, credit/debit cash balance

### Part 5: User Portfolio and Real-Time P&L
- Portfolio: per user, holdings (stock_id → shares_held), cash balance
- Real-time P&L: portfolio value = Σ (shares_held × current_price) for each holding
- Current price: fetched from Redis (updated in Part 3)
- On WebSocket: push updated P&L to user every time any held stock's price changes
- Throttling: if user holds 50 stocks, they'd get 50 simultaneous updates — batch into one update per second
- Historical P&L: stored in time-series DB (InfluxDB or Cassandra) for chart display

### Part 6: Low-Latency Architecture Choices
- No ORM: direct SQL queries (or skip SQL entirely, use Redis + Cassandra)
- Binary protocols: FIX/FAST for exchange communication, MessagePack or Protobuf internally
- Avoid garbage collection pauses: Java GC pauses kill latency — use off-heap memory, or Go/C++
- Kernel bypass networking: DPDK or RDMA for sub-microsecond latency (HFT only — not needed at L5)
- Co-location: place your servers in the same datacenter as the exchange (L6 / HFT topic)
- Connection pooling: pre-warm all exchange connections before market open

### Part 7: System Architecture
- Feed handler: receives exchange market data → parses → publishes to Kafka
- Price service: consumes Kafka → writes to Redis → pushes via WebSocket to subscribed users
- Order service: receives user orders → validates → routes to exchange → processes fills
- Portfolio service: tracks holdings and cash balance → computes real-time P&L
- Notification service: sends order confirmation and fill notifications via email/push

### Part 8: Interview Framework
- Clarify: retail trading app (Robinhood-style) vs. exchange matching engine vs. HFT — very different problems
- At L5, focus on the market data fan-out (exchange feed → many users) and order placement flow
- Explain the order book concept briefly even if you're not designing the matching engine
- Key trade-off to discuss: strong consistency for order execution vs. eventual consistency for price display
- L5 bar: market data pipeline (exchange feed → Kafka → Redis → WebSocket), order placement, portfolio P&L
- L6 bar: exchange-side order matching engine (the order book data structure and matching algorithm),
  HFT co-location, regulatory trade reporting (MiFID II, SEC Rule 605)

---

## The One-Sentence Summary

> "Stock trading feed = exchange market data (UDP multicast → feed handler → Kafka → Redis) fan-out to users via WebSocket + order placement (validate → debit funds → route to exchange via FIX → process async fills) + real-time P&L (portfolio value = holdings × Redis prices) — the key trade-off is strong consistency for order execution (you cannot oversell shares) vs. eventual consistency for price display (100ms stale is fine for retail)."

---

*Full chapter: ~2,500 lines. Section 5 — L5 / Senior SWE. Primarily for fintech roles.*
