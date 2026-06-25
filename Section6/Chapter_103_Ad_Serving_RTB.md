# Chapter 89: Ad Serving & Real-Time Bidding

## Google / Meta / Amazon — The $175B Millisecond Auction

---

> **Why this chapter matters for L6 interviews:** Ad serving is one of the most technically demanding distributed systems problems in existence. You have 50 milliseconds — the blink of an eye — to run a global auction involving hundreds of companies, score millions of candidate ads with machine learning models, apply fraud filters, check budget caps, and serve a pixel-perfect image to a user who has no idea any of this is happening. Every microsecond of latency costs money. Every engineering decision touches privacy law, fraud economics, and ML theory simultaneously. Google made $224B in 2023. About 77% of that came from ads. Understanding this system is not optional for senior engineers at Google, Meta, Amazon, or any company that touches digital advertising.

---

## Part 1: The Ad Ecosystem — Who Are All These Players?

### The Cast of Characters

When you load the New York Times website and an ad for Nike running shoes appears, you might think: "Nike paid the New York Times to show me this ad." That intuition is mostly wrong. In reality, a complex ecosystem of at least five different companies — and often more — participated in a real-time auction that decided which ad you saw. Let's meet everyone.

**The Publisher** is the website or app that has space to show ads. The New York Times is a publisher. YouTube is a publisher. The weather app on your phone is a publisher. Publishers have something valuable: attention. Millions of people read the New York Times every day, and the space on those pages — called **ad inventory** — can be sold to advertisers. The publisher wants to make as much money as possible from that inventory. But here's the problem: the New York Times is not in the business of running auctions and negotiating with thousands of advertisers simultaneously. They need help.

**The Supply-Side Platform (SSP)** is the technology company that represents publishers. Think of the SSP as the New York Times's sales agent. When someone loads a NYT page and an ad slot becomes available, the SSP takes that information and broadcasts it to the marketplace: "We have an ad slot! Here's what we know about the user. Who wants to bid?" Major SSPs include Google Ad Manager (formerly DoubleClick for Publishers), Rubicon Project, and Index Exchange. The SSP is incentivized to maximize the price publishers receive.

**The Ad Exchange** is the marketplace itself — the neutral ground where buyers and sellers meet. The exchange runs the auction. When Google says "Google Ads," they're often referring to their exchange. The exchange receives bid requests from SSPs, distributes them to DSPs (see below), collects bids, runs the auction, declares a winner, and notifies everyone. The exchange makes money by taking a percentage cut — usually 10-20% — of every transaction.

**The Demand-Side Platform (DSP)** is the technology company that represents advertisers. If the SSP is the NYT's sales agent, the DSP is Nike's buying agent. Nike doesn't want to individually negotiate with thousands of publishers. Instead, Nike tells their DSP: "We want to show ads to adults aged 25-45 who have visited running websites in the past 30 days. We'll pay up to $5 per thousand impressions." The DSP then uses automation to bid on every eligible ad slot across thousands of publishers simultaneously. Major DSPs include The Trade Desk, Google's DV360 (Display & Video 360), and Amazon DSP.

**The Advertiser** is the company that actually wants to show ads. Nike wants to sell shoes. Geico wants to sell car insurance. Amazon wants to sell, well, everything. Advertisers set budgets, define their target audiences, create the actual ad creative (the image, video, or text), and tell their DSP how much they're willing to pay for different types of impressions.

**The Data Management Platform (DMP)** is an optional but important player: a company that aggregates and sells audience data. Acxiom, Nielsen, and Oracle Data Cloud (formerly BlueKai) are examples. A DMP might know that a particular browser cookie belongs to someone who is in-market for a new car — information they derived from tracking that user's behavior across hundreds of websites. DSPs buy this data to improve their targeting.

### The Full Flow: From Page Load to Ad Shown

Let's trace exactly what happens in those 50 milliseconds between when you load a webpage and when an ad appears.

```
TIME 0ms: YOU CLICK A LINK TO NYT.COM
|
v
TIME 1ms: YOUR BROWSER BEGINS LOADING THE PAGE
          NYT's servers start sending HTML
|
v
TIME 5ms: BROWSER EXECUTES JAVASCRIPT AD TAG
          A small piece of JS code on the page says:
          "Hey, there's an ad slot here.
           Here's what I know about this user."
          This triggers a "bid request"
|
v
TIME 6ms: SSP (Google Ad Manager) RECEIVES BID REQUEST
          SSP packages the information:
          - Ad slot dimensions (728x90 banner)
          - Page URL (nytimes.com/sports/running)
          - User's anonymized ID (cookie: abc123)
          - Timestamp
          - Floor price (minimum acceptable bid: $1.00 CPM)
|
v
TIME 7ms: SSP BROADCASTS TO AD EXCHANGE
          Exchange sends bid request to 200+ DSPs simultaneously
|
v
TIME 7-42ms: ALL DSPs PROCESS AND BID
             Each DSP independently:
             (a) Looks up user profile from their database
             (b) Determines if they have relevant ads
             (c) Runs ML model to predict click probability
             (d) Calculates maximum bid
             (e) Returns bid response
|
v
TIME 42ms: EXCHANGE CLOSES AUCTION
           Collects all bids
           Runs second-price auction
           Declares winner
|
v
TIME 43ms: WINNING DSP NOTIFIED
           Loser DSPs receive loss notifications
|
v
TIME 44ms: AD CREATIVE FETCHED
           Winning DSP's ad server returns the actual image/HTML
|
v
TIME 50ms: AD RENDERED IN YOUR BROWSER
           You see the Nike shoe ad

TOTAL: 50 MILLISECONDS
```

The entire auction, user lookup, ML inference, and creative delivery happens in less time than it takes you to blink.

### Why This System Exists and Why It Makes $175B/Year

Before programmatic advertising (which began around 2009-2010), buying digital ads was manual and inefficient. An advertiser would call a publisher's sales team, negotiate a rate, and sign a contract. This worked fine for premium placements — the front page of the New York Times. But most ad inventory — the 500th article in the sports section, a page in a niche blog — was nearly impossible to sell manually. Publishers were "burning" this inventory, showing house ads or nothing at all.

Real-time bidding solved this by creating a liquid market. Every ad impression — no matter how obscure the publisher — gets auctioned to every advertiser simultaneously. The key insight is that different advertisers value the same impression differently. Nike doesn't care about the NYT sports page per se; they care about reaching a specific person who is likely to buy running shoes. If that person happens to be reading a fishing blog, Nike still wants to reach them. RTB matches the right advertiser to the right impression regardless of where that impression occurs.

This dramatically increased efficiency on both sides:
- Publishers got more revenue from previously unsellable inventory
- Advertisers could precisely target their desired audience at scale

The result: digital advertising grew from ~$20B in 2009 to $600B+ globally today. Google alone captured $224B in 2023. This is the plumbing that runs the modern internet.

### Intern to Staff Progression: Understanding the Ecosystem

**Intern:** Knows that publishers show ads and advertisers pay for them. Understands CPM (cost per thousand impressions) as the basic pricing unit.

**Junior (L3):** Understands the publisher/advertiser/exchange triangle. Can explain why a middleman exchange adds value (aggregation, standardization, trust). Knows that DSPs and SSPs both claim to "optimize" but from different sides.

**Mid-level (L4):** Understands header bidding — the technique where publishers run auctions with multiple exchanges simultaneously (instead of waterfall, where exchanges are tried sequentially). Understands why header bidding increased publisher revenue by 20-30% but also increased page load times.

**Senior (L5):** Understands the full technology stack: ad servers, bid caches, creative delivery CDNs, impression tracking pixels, click tracking redirects, viewability measurement. Can reason about why Google's vertical integration (Chrome + Google Ads + DoubleClick) creates both efficiency and antitrust concerns.

**Staff (L6):** Understands that the ecosystem is a game-theoretic system where every player is optimizing for themselves, often at the expense of others. Publishers want high floors, advertisers want low clearing prices, exchanges want high volume, DMPs want data proliferation. The interesting engineering work is designing systems that balance these incentives while remaining technically sound and legally compliant.

### Brainstorming Q&A

**Q: Why do advertisers use DSPs instead of directly integrating with each exchange?**

A DSP's core value proposition is aggregation and abstraction. There are dozens of major ad exchanges and hundreds of SSPs, each with different APIs, bid formats, timeout requirements, and reporting formats. An advertiser wanting to reach their audience everywhere would need to integrate with all of these separately — a massive engineering investment. A DSP does that integration once and lets advertisers access all inventory through a single interface. Beyond the integration work, DSPs also provide campaign management tools, reporting dashboards, and crucially, their own ML models for bid optimization. A DSP that is better at predicting which impressions will result in a purchase can outperform competitors even at the same price point.

More subtly, DSPs provide something called cross-publisher frequency capping — ensuring that a user doesn't see the same Nike ad 50 times per day across different websites. Without a DSP, each exchange would only know about ads served through their own system, so the same user could see the same ad at full frequency on every exchange separately. The DSP, sitting above all exchanges, maintains a unified view of per-user ad exposure. This requires the DSP to maintain a massive key-value store indexed by user identity — one of the hardest scaling problems in the system.

**Q: How does Google's dual role as both an exchange AND the dominant SSP create conflict of interest?**

Google operates Google Ad Manager (the SSP used by most large publishers), Google Ads (the largest advertiser-facing platform/DSP), AND runs the Google Ad Exchange (the exchange in the middle). This means Google is simultaneously the seller's agent, the buyer's agent, and the marketplace operator. In any financial market, having the same entity operate all three roles is considered deeply problematic — analogous to a stock exchange that also runs the largest brokerage on both sides.

The Department of Justice sued Google in 2023 over exactly this concern, alleging that Google used its control over the exchange to advantage its own DSP products. For example, there were allegations that Google Ad Exchange (AdX) was given access to publisher floor prices before the auction (a practice called "Last Look") which allowed Google's own buyers to win auctions they otherwise would have lost. From a technical perspective, this is an interesting system design question: how do you build an exchange that is genuinely neutral when the exchange operator is financially incentivized to favor their own products? The answer, apparently, is that you don't — which is why regulators eventually had to intervene.

---

## Part 2: Real-Time Bidding — The 50ms Auction

### The Fundamental Constraint

Fifty milliseconds. That is the entire time budget for the RTB auction. Why 50ms? Because the webpage is loading, and if the ad takes longer than ~100ms to appear, users will see the page "jump" as content loads and then the ad slot suddenly fills in. User experience research shows this is annoying enough to cause people to install ad blockers. Publishers impose strict timeouts — typically 50ms, sometimes 100ms for larger budgets — on the auction. Any bid that arrives after the timeout is simply ignored, even if it's the highest bid. From an engineering perspective, this creates an unusual requirement: you'd rather return a slightly wrong but fast answer than a perfectly correct slow one.

### The Bid Request — What Gets Sent to Every DSP

When the SSP decides to run an auction, it constructs a **bid request** using the OpenRTB protocol (an industry standard maintained by the IAB). The bid request is typically 1-5KB of JSON or Protocol Buffer data sent to every eligible DSP simultaneously.

Here's an annotated bid request:

```json
{
  "id": "auction-abc-123",
  "imp": [{
    "id": "1",
    "banner": {
      "w": 728,
      "h": 90,
      "pos": 1
    },
    "bidfloor": 1.00,
    "bidfloorcur": "USD"
  }],
  "site": {
    "page": "https://nytimes.com/sports/running/best-shoes-2024",
    "cat": ["IAB17-44"],
    "publisher": {
      "id": "pub-nyt-001",
      "name": "The New York Times"
    }
  },
  "user": {
    "id": "user-hashed-abc123",
    "buyeruid": "dsp-specific-id-xyz"
  },
  "device": {
    "ua": "Mozilla/5.0...",
    "ip": "73.x.x.x",
    "devicetype": 2,
    "geo": {
      "country": "USA",
      "metro": "501"
    }
  },
  "at": 2,
  "tmax": 50
}
```

Every DSP receives this same packet. Each DSP has 50ms to respond.

### The Bid Response — What Each DSP Sends Back

A DSP that wants to bid responds with:

```json
{
  "id": "auction-abc-123",
  "seatbid": [{
    "bid": [{
      "id": "dsp-bid-789",
      "impid": "1",
      "price": 3.50,
      "adid": "nike-shoes-creative-456",
      "nurl": "https://dsp.example.com/win?price=${AUCTION_PRICE}",
      "lurl": "https://dsp.example.com/loss?reason=${AUCTION_LOSS_REASON}",
      "adm": "<img src='https://cdn.example.com/nike-ad.png'...>",
      "crid": "creative-nike-shoes-summer",
      "cat": ["IAB17-44"],
      "w": 728,
      "h": 90
    }]
  }]
}
```

DSPs that choose not to bid simply return an empty response or a "no bid" response. They might choose not to bid because: the user doesn't match any active campaign targeting criteria, the DSP has already spent all campaign budgets for the day, or the floor price is too high.

### The Second-Price Auction — Why This Matters

The auction type `"at": 2` in the bid request means **second-price auction**, also called a **Vickrey auction**. This is different from a first-price auction in a fundamental way.

In a **first-price auction**: you bid $5, if you win, you pay $5.
In a **second-price auction**: you bid $5, if you win, you pay whatever the second-highest bid was, plus one cent.

Example:
- DSP_A bids $5.00
- DSP_B bids $3.50
- DSP_C bids $2.00
- Floor price: $1.00

Winner: DSP_A. Clearing price: $3.51 (second highest bid + $0.01)

Why does this matter? In a second-price auction, the **dominant strategy is to bid your true value**. There's no gaming benefit to shading your bid below your true willingness to pay. This is provably true using game theory: if you bid your true value and someone else outbids you, you wouldn't have wanted to win anyway. If you bid below your true value and lose to someone between your true value and your shaded bid, you left a profitable opportunity on the table.

Second-price auctions were the industry standard until around 2017-2019, when most exchanges switched to first-price auctions. The switch happened because sophisticated buyers (DSPs) were using bid shading algorithms anyway — submitting bids below their true values to pay less. The game theoretically "clean" property of second-price auctions had eroded because the auction mechanics had become more complex than the simple Vickrey model (floor prices, header bidding across multiple exchanges, etc.). First-price auctions are more transparent: you know exactly what you're paying.

### Win and Loss Notifications

After the auction closes, the exchange sends notifications:

**Win notification (nurl):** Sent to the winning DSP with the actual clearing price filled in via macro substitution. The DSP uses this to record: "We won impression X, paid $Y, charged campaign Z."

**Loss notification (lurl):** Sent to losing DSPs with a reason code:
- 0: Unknown
- 1: Internal error
- 102: Bid was below auction floor
- 200: Lost to higher bid
- 203: Blocked by publisher (wrong ad category)
- 205: Frequency cap hit (user has seen this ad too recently)

Loss notifications are valuable for DSP ML model training. Knowing that a particular bid of $2.00 lost while a bid of $3.50 won tells the DSP something about the competitive landscape — useful for calibrating future bids.

### The Full RTB Latency Budget Breakdown

```
FULL RTB LATENCY BUDGET: 50ms total

+---------------------------------------------------------+
|  TIME    |  COMPONENT               |  BUDGET           |
+---------------------------------------------------------+
|  0-2ms   |  Network: Browser->SSP   |  2ms              |
|  2-4ms   |  SSP processing          |  2ms              |
|          |  (parse, validate,        |                   |
|          |   build bid request)      |                   |
|  4-6ms   |  Network: SSP->Exchange  |  2ms              |
|  6-8ms   |  Exchange fanout to DSPs  |  2ms              |
|  8-42ms  |  DSP processing          |  34ms             |
|          |  +- Cookie sync lookup   |  2ms              |
|          |  +- User profile lookup  |  5ms              |
|          |  +- Targeting evaluation |  5ms              |
|          |  +- Feature computation  |  10ms             |
|          |  +- ML model inference   |  5ms              |
|          |  +- Bid calculation      |  2ms              |
|          |  +- Network back to exch |  5ms              |
|  42-43ms |  Exchange: collect bids  |  1ms              |
|          |  run auction             |                   |
|  43-44ms |  Win notification        |  1ms              |
|  44-50ms |  Ad creative delivery    |  6ms              |
|          |  (from CDN)              |                   |
+---------------------------------------------------------+

KEY CONSTRAINT: DSPs have ~34ms of their own compute budget.
Every ms saved in DSP processing is a ms that can be used for
more sophisticated ML scoring or reaching more auctions.
```

### Brainstorming Q&A

**Q: What happens when network latency between the exchange and a DSP exceeds the timeout?**

This is a real operational problem. Ad exchanges are typically co-located in specific data centers (Ashburn, VA in the US; Amsterdam in Europe; Tokyo and Singapore in Asia). DSPs that want to participate must either locate their bid servers in the same data centers or accept that they'll time out frequently on cross-region traffic. A DSP server on the US East Coast might be 5ms from an Ashburn exchange, while a server in California might be 70ms away — exceeding the entire auction budget just on network round-trip time. This is why large DSPs run geographically distributed bid servers, with each regional cluster serving exchanges in nearby data centers.

The engineering trade-off is interesting: you could reduce latency by pre-caching all user profiles and campaign data at every regional cluster (reducing lookup time but requiring global data synchronization) or you could use a single global database with regional read replicas (faster sync but potentially higher latency for profile lookups). Most large DSPs use a hybrid approach: campaign budgets and targeting rules are cached locally at each regional cluster and pushed via CDC (change data capture), while user profile lookups go to regional replicas of a globally consistent key-value store.

**Q: If second-price auctions are game-theoretically optimal, why did the industry switch to first-price?**

The textbook Vickrey auction result requires several conditions that the real RTB ecosystem violated. First, the auction must have a single round — but header bidding created situations where the same impression was effectively auctioned multiple times simultaneously through different exchanges, and sophisticated buyers could use information from losing in one auction to shade bids in another. Second, the floor prices in second-price auctions were sometimes manipulated dynamically based on incoming bids (a practice called "soft floors" or dynamic floors), which broke the equilibrium property — bidding your true value was no longer dominant if the floor could jump up to meet your bid.

First-price auctions have different problems — buyers must actively shade their bids using algorithms (bid shading), which requires sophisticated ML models — but at least the mechanism is transparent. You pay what you bid. No hidden floors, no Last Look advantages, no soft floors. The DSP bid shading problem is interesting: you want to win at the lowest price you can while still outbidding competitors. This requires estimating the distribution of competing bids — essentially predicting what other DSPs will bid — and submitting a bid that just clears the expected winning bid by a small margin. This is a regression problem that DSPs train on historical clearing price data.

---

## Part 3: User Targeting — Finding the Right Person

### Why Targeting Is Worth Billions of Dollars

An untargeted ad impression on a random webpage might be worth $0.10 CPM. The same ad impression, targeted to a user who has been actively researching running shoes for the past week, might be worth $10.00 CPM — 100x more. This difference in value is why user targeting is central to the entire ad ecosystem. Better targeting = higher eCPMs for publishers, better ROI for advertisers, and more profit for intermediaries who facilitate the match.

### Types of Targeting

**Demographic Targeting** is the oldest and simplest form. You target by age, gender, income, education, or geography. This information comes from users self-reporting (filling out profiles on Facebook) or from probabilistic inference (machine learning models that predict demographics from browser behavior). Demographic targeting is blunt — all 25-34-year-old males are not the same — but it's a useful filter.

**Behavioral Targeting** groups users based on what they've been doing online. An "in-market" audience for running shoes might include anyone who visited running shoe websites, searched for shoe reviews, or looked at marathon training plans in the past 30 days. Interest categories are maintained by both the DSPs/DMPs themselves (based on cookie tracking) and by large platforms like Google and Facebook (based on logged-in activity). Behavioral targeting is much more predictive than demographic targeting but raises significant privacy concerns.

**Contextual Targeting** shows ads based on the content of the page being viewed, not the identity of the user. A running shoe ad shown on an article about marathon training is contextual targeting. You don't need to know anything about the user — you just need to know what they're reading right now. Post-iOS 14.5 and with growing cookie deprecation, contextual targeting has seen a major resurgence because it doesn't require any user identity tracking.

**Retargeting (Remarketing)** shows ads to users who have previously visited your website. If you visited Nike.com and looked at a specific pair of shoes but didn't buy them, you might start seeing ads for those exact shoes everywhere you go online. This works via a **tracking pixel**: a 1x1 invisible image on the Nike.com product page that, when loaded, fires a request to Nike's ad server, recording your browser cookie and the product you viewed. When you later visit other websites, Nike's DSP recognizes your cookie and bids aggressively to show you that specific product.

**Lookalike Audiences** use machine learning to find users who are similar to your existing customers. If Nike's best customers share certain behavioral patterns (e.g., they visit fitness websites, they follow sports accounts, they buy premium products), the ML model can identify other users with similar patterns who haven't yet purchased from Nike. Facebook's lookalike audience tool is legendary for its precision — and notorious for its privacy implications.

### The User Profile Lookup — 10ms Budget

When a DSP receives a bid request, one of the first things it does is look up what it knows about the user. The bid request contains a user ID (typically an anonymized cookie or mobile advertising ID). The DSP's user profile store maps this ID to a rich set of attributes.

```
USER PROFILE LOOKUP FLOW

Bid Request arrives with:
  user.id = "user-hashed-abc123"
       |
       v
Cookie Sync Table lookup:
  "user-hashed-abc123" -> "dsp-internal-id-XYZ789"
       |
       v
User Profile Store (Redis / Bigtable):
  "dsp-internal-id-XYZ789" -> {
    "interests": ["running", "fitness", "premium_shoes"],
    "in_market_signals": ["shoe_purchase_intent:0.87"],
    "demographics": {"age_bucket": "25-34", "gender": "M"},
    "recency_signals": {
      "last_visit_nytimes": "2024-01-15T10:30:00Z",
      "last_click_shoe_ad": "2024-01-10T15:20:00Z"
    },
    "frequency_data": {
      "nike_campaign_123": 3,
      "geico_campaign_456": 0
    },
    "suppression_list": false
  }

Budget: 5-10ms total for this lookup
Solution: Redis cluster with consistent hashing,
          ~100B keys, in-memory storage
```

**Cookie Syncing** is worth explaining because it's a major piece of infrastructure. The user ID in a bid request is set by the SSP (or exchange) — it reflects the SSP's cookie for this user. But the DSP has its own separate cookie for the same user. To match these up, DSPs and SSPs engage in **cookie syncing**: when a user visits a page, the SSP redirects to the DSP's URL, passing its own user ID. The DSP records the mapping: "SSP user ID X = DSP user ID Y." This mapping table is essential — without it, the DSP can't look up its profile for the user identified in the bid request.

### Post-iOS 14.5: The Death of Mobile Tracking

In April 2021, Apple released iOS 14.5 with a feature called App Tracking Transparency (ATT). Before showing any app the user's IDFA (the identifier used to track them across apps), iOS now asks permission. The result: 75-80% of users said no. For Facebook and other mobile advertisers, this was catastrophic. Retargeting became nearly impossible on iOS. Attribution — knowing which ad led to a purchase — became unreliable.

The industry has been scrambling ever since with alternatives:
- **SKAdNetwork (SKAN):** Apple's privacy-preserving attribution framework. Apps can measure if ads led to installs without revealing which specific user clicked. Data is delayed and aggregated.
- **Probabilistic attribution:** Uses device signals (IP address, device type, screen resolution, time of click) to probabilistically match clicks to installs without individual identifiers.
- **Contextual signals:** Leaning harder on what the user is doing right now (reading about running shoes) rather than their historical identity.
- **First-party data:** Advertisers pushing users to log in so they have a first-party relationship. Nike asking you to create an account gives them logged-in user data they own.
- **Privacy Enhancing Technologies (PETs):** Techniques like federated learning and differential privacy that allow ML models to learn from data without centralizing it.

### Brainstorming Q&A

**Q: How does retargeting work across devices when cookies don't follow you from phone to laptop?**

Cookies are browser-specific. A cookie set on your laptop's Chrome browser is invisible to your phone's Safari browser. Yet advertisers clearly do reach you across devices — you browse shoes on your phone, and then see shoe ads on your laptop. This happens through **device graphs** or **identity graphs** — massive databases that probabilistically or deterministically link device IDs together.

Deterministic matching is straightforward: if you're logged into Facebook on both your phone and your laptop, Facebook knows these are the same person. They map your phone's advertising ID to your laptop's cookie to your Facebook user ID — creating a unified identity record. This is why Facebook's cross-device attribution was so accurate for years. Google does the same through Google account logins. Advertisers using these platforms get cross-device reach as a built-in feature.

Probabilistic matching is used when deterministic signals aren't available. Companies like LiveRamp observe that a phone at IP address 73.x.x.x at 8pm and a laptop at IP address 73.x.x.x at 8pm are probably the same household, and the behavioral patterns might further confirm they're the same person. These linkages are never 100% accurate — household members share IPs, and behavioral similarities can be coincidental — but at scale they're statistically useful. Privacy laws (GDPR in Europe, CCPA in California) have made probabilistic device graph matching significantly more legally fraught, as it constitutes processing personal data without explicit consent.

**Q: What are interest categories and how do companies decide which categories a user belongs to?**

Interest category classification is essentially a multi-label text and behavior classification problem. The IAB (Interactive Advertising Bureau) publishes a standard taxonomy with hundreds of categories: "Running & Jogging," "Investment Products," "Family Pets," etc. A company like Google wants to classify every Chrome user into relevant categories from this taxonomy, because advertisers target using these categories.

The signals used include: URLs of websites visited, search queries typed (for Google specifically), content of pages viewed (through keywords), videos watched on YouTube, apps installed, and physical location (through Google Maps). An ML model (typically a sequence model trained on these behavioral signals) outputs a probability for each IAB category. Users with probability above a threshold for "Running & Jogging" get assigned to that category. This assignment is stored in the user profile and used for targeting.

The threshold matters a lot: set it too high, and you miss users who would respond well to running shoe ads; set it too low, and you're calling everyone a runner, which reduces campaign precision and wastes advertiser budget. Google internally tuned these thresholds using downstream ad performance — if setting a lower threshold for "Running & Jogging" leads to better CTR on running shoe ads, lower it. This creates a feedback loop between the classification model and the auction, which is powerful but also creates risks of bias amplification.

---

## Part 4: Ad Ranking & Auction Mechanics

### Ad Rank: Why the Highest Bidder Doesn't Always Win

Here's a counterintuitive fact: in Google's search advertising auction, the advertiser who bids the most doesn't necessarily win. Google uses a concept called **Ad Rank** to determine which ad shows:

```
Ad Rank = Bid Price x Quality Score

Quality Score = Expected CTR x Ad Relevance x Landing Page Quality
```

Why does this make sense? Consider two advertisers:
- Advertiser A: Bids $10, Quality Score 1 -> Ad Rank = 10
- Advertiser B: Bids $5, Quality Score 3 -> Ad Rank = 15

Advertiser B wins despite having a lower bid, because their ad is three times more likely to be clicked. This is rational from Google's perspective: Google only gets paid when someone clicks (in CPC auctions). A highly relevant ad that gets clicked 3x more generates more revenue than an irrelevant ad even at 2x the price.

Quality Score has three components:

**Expected CTR (click-through rate):** Given that the ad is shown, what's the probability the user clicks? This is predicted by a machine learning model trained on historical ad performance data. A new ad gets a baseline CTR based on similar ads; over time, actual performance updates the estimate.

**Ad Relevance:** How well does the ad copy match the user's search query or the page content? An ad for Nike running shoes on a page about marathon training scores high; the same ad on a page about cooking scores low. This is measured through keyword matching and semantic similarity models.

**Landing Page Quality:** When users click the ad, what do they find? Google evaluates landing pages for relevance (does the page actually sell running shoes?), page load speed, mobile-friendliness, and absence of deceptive content. Poor landing page quality lowers the quality score even if the ad itself is relevant.

### The Actual Clearing Price

Given Ad Ranks, the clearing price (what the winner actually pays) is:

```
Clearing Price = (Second-place Ad Rank / Winner's Quality Score) + $0.01

Example:
Advertiser A: Bid $10, QS=1 -> Ad Rank=10
Advertiser B: Bid $5, QS=3 -> Ad Rank=15

B wins.
B's clearing price = (10 / 3) + $0.01 = $3.34

B bid $5 but only pays $3.34!
B's high quality score saves them money.
```

This formula has a beautiful property: it incentivizes advertisers to improve ad quality, not just bid more money. Google calls this "the auction serving users and advertisers." It genuinely aligns incentives — bad ads are penalized, good ads are rewarded with lower clearing prices.

### Programmatic Guaranteed and Private Marketplaces

Not all display advertising goes through the open auction. Two important variants:

**Programmatic Guaranteed (PG):** A publisher and advertiser negotiate a deal in advance: "Nike will buy 1 million impressions per month on NYT's homepage at $50 CPM." The deal is executed programmatically (automated delivery, no manual insertion orders), but the price and volume are guaranteed. The advertiser knows they'll get premium inventory; the publisher gets guaranteed revenue. These deals bypass the open auction — the agreed impression goes directly to Nike without being bid on by others.

**Private Marketplace (PMP):** An auction, but restricted to invited buyers. NYT might run a private auction for their Sports section with only five invited DSPs — all premium brands approved by NYT. The floor price is higher than the open auction, but the quality of the inventory is guaranteed (brand-safe, premium context). Buyers in a PMP get access to inventory that's not available on the open exchange.

### Dynamic Floor Price Optimization

Publishers want to maximize revenue. If their floor price is too low, they leave money on the table (winning bids are much higher than floor). If too high, they get no fill (auctions fail because all bids are below floor). The optimal floor price strategy is to set the floor just below the second-highest expected bid — capturing maximum revenue without blocking too many auctions.

Modern SSPs use ML models to set dynamic floor prices per auction. Inputs to the model include: historical clearing prices for similar impressions, time of day, day of week, user segment, competition level (how many active DSPs are bidding). The model outputs a recommended floor price that maximizes expected revenue.

This creates an interesting adversarial dynamic. DSPs try to predict floor prices to shade their bids appropriately. SSPs try to predict DSP behavior to set floors optimally. Both are running ML models trying to outguess the other. In game theory, this is called an imperfect information game, and the optimal strategies involve mixed strategies (randomization) rather than deterministic policies.

### Intern to Staff Progression: Auction Mechanics

**Intern:** Understands CPM and that higher bids win. Knows what CTR means.

**Junior (L3):** Understands Ad Rank and why quality score matters. Can explain why Google benefits from higher-quality ads even at lower bids.

**Mid-level (L4):** Understands the GSP (Generalized Second Price) auction — the multi-slot version of the Vickrey auction used in search advertising where there are multiple ad positions (slot 1, 2, 3) each with different CTR multipliers. Can reason about truthful bidding in multi-slot settings.

**Senior (L5):** Understands the strategic implications of dynamic floors and bid shading. Can reason about how floor price transparency (or opacity) affects buyer bidding strategies. Understands that the switch from second-price to first-price auctions requires DSPs to develop sophisticated bid shading models.

**Staff (L6):** Can reason about mechanism design: what auction format maximizes revenue for the exchange? What format is most efficient (maximizes total surplus, i.e., value to both advertisers and publishers)? Understands that theoretical auction optimality breaks down in practice due to budget constraints, campaign objectives (CPC vs CPM vs ROAS targets), and the multi-period nature of advertising campaigns.

### Brainstorming Q&A

**Q: What happens when an advertiser's quality score changes drastically overnight?**

Quality score changes can have massive financial implications. In 2011, Google made a major change to their quality score algorithm that caused some advertisers' CPCs (cost per click) to increase by 5x overnight — their minimum bids to appear at all jumped significantly. Small advertisers with poor landing pages or low-relevance ads suddenly couldn't afford to compete. This caused significant controversy and highlighted the enormous power Google has as the operator of the dominant search advertising auction.

From a system design perspective, quality score changes need to be carefully managed. You can't update quality scores for all ads simultaneously in a single batch — the load would be enormous, and the sudden change in auction dynamics would cause chaos. Google's approach (as described in public engineering blog posts) involves computing quality scores incrementally and rolling out changes gradually. New quality score values are A/B tested on a small percentage of traffic before being applied broadly. Even so, quality score computation is one of Google's most computationally expensive operations — evaluating CTR predictions for hundreds of billions of ad-keyword combinations requires massive infrastructure.

**Q: Why do reserve prices (floor prices) sometimes hurt publishers even though they seem to protect them?**

Reserve prices protect publishers from selling inventory too cheaply when competition is low. But they can hurt publishers in subtle ways. Consider: a publisher sets a floor of $5 CPM. A DSP has a true value of $6 CPM but through bid shading (in a first-price auction) submits $5.10 — just above the floor. The publisher gets $5.10. But if the publisher had set a floor of $3, that same DSP would bid $3.50 (shading less aggressively because the floor is lower and the DSP values the impression at $6). So with a lower floor, the publisher might actually earn more because the DSP's bid shading behavior changes.

This is counterintuitive — a lower floor leading to a higher clearing price — but it emerges from the game-theoretic interaction between floor setting and bid shading. The optimal floor price for a publisher is not obvious and depends on the distribution of buyers' true values and their shading algorithms. This is why SSPs use ML to dynamically set floors rather than using fixed values. The best floors are those that, across many auctions, maximize total revenue — and this requires modeling how buyers will respond to different floor levels.

---

## Part 5: ML Scoring Pipeline — Predicting What You'll Click

### The Core Prediction Problem

Every time an ad is being considered for display, the ad system needs to answer: "If we show this ad to this user in this context, what is the probability the user will click (or convert, or watch, etc.)?" This probability is called the **predicted CTR (pCTR)** for click-through rate, or **pCVR** for conversion rate. It drives the Ad Rank calculation, the bid optimization in DSPs, and the quality score.

The challenge: this prediction needs to happen in 5 milliseconds, for millions of auctions per second, for billions of user-ad-context combinations that mostly haven't been seen before.

### The Feature Space

Modern CTR models use 100-1,000 features. Categories include:

**User features:** Age bucket, gender (if known), geographic location, time since last click, number of times seen this creative, interests (from behavioral data), device type (mobile vs desktop vs tablet).

**Ad features:** Ad category, creative type (image vs video vs text), advertiser, historical CTR for this creative (on similar users in similar contexts), landing page quality score.

**Context features:** Publisher/website category, time of day, day of week, position of the ad slot (above-the-fold is more valuable), page load speed.

**Cross features:** Feature interactions. "User interested in running + Ad for running shoes" is much more predictive than either feature alone. Cross features capture these interactions. With 1000 raw features, there are 500,000 potential pairwise cross features — too many to enumerate, so learned embeddings are used instead.

### The Model Architecture

Early CTR models used logistic regression with hand-crafted features. Modern systems use gradient boosted trees (GBT, like XGBoost or LightGBM) or deep neural networks (DNNs), often combined:

```
CTR PREDICTION PIPELINE

Raw bid request + user profile
       |
       v
FEATURE COMPUTATION (10ms budget)
  +- Look up user features from Redis
  +- Look up ad features from feature store
  +- Compute cross features
  +- Apply feature normalization
  +- Assemble feature vector (100-1000 dimensions)
       |
       v
MODEL INFERENCE (5ms budget)
  Option A: XGBoost/LightGBM (GBT)
    - Ensemble of 1000+ decision trees
    - Fast inference: ~1ms for 1000 trees
    - Good with sparse categorical features

  Option B: Deep Neural Network
    - Embedding layers for categorical features
    - Dense layers for interaction
    - Slower (~5ms) but captures more complex patterns

  Option C: Two-stage (common at Google/Meta)
    - Stage 1: Fast GBT for candidate selection (top 100 from 10000)
    - Stage 2: DNN for final ranking (top 1 from 100)
       |
       v
CTR SCORE (float between 0 and 1)
  e.g., 0.023 = 2.3% predicted click rate
       |
       v
USED IN:
  +- Ad Rank = Bid x (CTR x other signals)
  +- DSP bid optimization: Bid = Target_CPA x pCVR x bid_multiplier
  +- Reject/approve/challenge threshold gates
```

### The Feature Store Architecture

The feature store is the infrastructure that makes real-time ML inference possible. It has two layers:

**Online feature store (Redis/Bigtable):** Pre-computed features that need to be served at low latency. User interest vectors, historical CTR by creative, recent behavioral signals. Updated in near-real-time (seconds to minutes lag). Must handle 1M+ reads per second with P99 latency under 2ms.

**Offline feature store (Spark/BigQuery):** Historically computed features, training data, large aggregates. Used for model training, not real-time inference. Can handle query latencies of seconds to minutes. Holds petabytes of data.

The training pipeline reads from the offline store. The serving pipeline reads from the online store. These need to be kept consistent — training/serving skew is a major ML engineering problem. If the feature computation logic in Spark (for training) differs from the Redis lookup logic (for serving), the model performs worse in production than in offline evaluation. This is the **training/serving skew** problem and it's one of the most common sources of ML system bugs.

### Threshold Gates: Approve, Challenge, Block

Not every ad needs full ML scoring. For efficiency, ad systems use threshold gates:

**Block:** Immediately reject ads with clear disqualifiers — wrong category for this publisher, budget exhausted, targeting criteria clearly not met (e.g., a US-only campaign getting an impression from France). No ML needed.

**Approve:** For high-frequency, well-understood ad-user combinations where historical data makes the prediction obvious, use a lookup table instead of full ML inference.

**Challenge:** For uncertain cases, run the full ML pipeline. These are the marginal impressions where the ML model's output will actually change the decision.

This tiered approach means 90%+ of decisions don't require full ML inference, dramatically reducing compute load.

### Intern to Staff Progression: ML Scoring

**Intern:** Understands CTR as a concept. Knows logistic regression. Might know XGBoost exists.

**Junior (L3):** Can implement a basic CTR prediction pipeline. Understands feature engineering, training/test split, AUC-ROC as an evaluation metric for click prediction.

**Mid-level (L4):** Understands training/serving skew and why it's dangerous. Knows how to use calibration curves to ensure predicted CTR is numerically accurate (not just rank-ordered correctly). Understands why AUC is insufficient for business decisions — you need calibrated probabilities to multiply by bid prices.

**Senior (L5):** Understands the two-tower model architecture (user embedding tower + item embedding tower) used for large-scale retrieval. Can reason about embedding dimensionality trade-offs. Understands delayed feedback (conversions don't happen immediately, so training data is biased toward recency) and techniques to handle it.

**Staff (L6):** Designs the full ML platform: training pipelines, model serving infrastructure, A/B testing frameworks for ML models, feedback loops, continuous training strategies, and how to safely deploy model changes that affect $100M/day in ad spend.

### Brainstorming Q&A

**Q: How do you handle the cold start problem for new ads that have no historical CTR data?**

New ad creatives have no historical performance data, so the CTR model can't use historical CTR as a feature. This is the cold start problem in ad systems. The naive approach is to assign a default CTR based on the ad's category and format — a display banner from an apparel advertiser gets a default CTR of 0.05% based on the category average. This works reasonably well as a prior but causes new ads to be systematically under-served during their "warmup" period.

More sophisticated approaches use content-based similarity: extract the semantic content of the new ad (visual features from the image, text features from the copy) and find similar creatives in the training set. The CTR of similar creatives, weighted by similarity score, becomes the predicted CTR for the new creative. This transfers learning from known creatives to unknown ones. Google has published research on using image embedding models to compare visual similarity between ad creatives for exactly this purpose.

A third approach, used by platforms with enough scale, is to deliberately explore new creatives by serving them more frequently than their predicted CTR would warrant — treating the initial serving period as exploration in a multi-armed bandit. The platform accepts lower revenue during exploration in exchange for faster convergence to a good CTR estimate. This exploration is carefully budgeted and usually limited to a small fraction of total auction volume.

---

## Part 6: Frequency Capping — Don't Annoy Your Customers

### The Problem: Nobody Wants to See the Same Ad 50 Times

Imagine visiting a pair of shoes on Amazon and then seeing that exact pair of shoes advertised to you on every single website you visit for the next month, fifty times a day. This is not a hypothetical — without frequency capping, this would happen. A single advertiser might have campaigns running on every exchange, winning auctions on every publisher, repeatedly targeting the same user.

**Frequency capping** is the technical system that limits how many times a given user sees a given ad (or ad campaign, or advertiser) within a time window. Common caps:
- Show this ad no more than 3 times per user per day
- Show this advertiser's ads no more than 10 times per user per week
- Never show this creative to the same user more than 20 times ever

Frequency capping improves user experience (fewer annoying repeated ads), advertiser ROI (showing the same ad to the same person 50x is wasteful), and publisher quality (publishers with better user experience retain users longer).

### The Scale Problem

Here's why this is hard. Consider:

```
FREQUENCY CAPPING SCALE PROBLEM

Active users:          10,000,000 (10M)
Active campaigns:      10,000
Cap granularities:     daily, weekly, lifetime

Naive key-value store:
  Key format: user_id:campaign_id:time_window
  Keys needed: 10M users x 10K campaigns x 3 windows = 300 BILLION keys

At 100 bytes per key: 30 terabytes of key storage alone
At 8 bytes per counter: 2.4 terabytes of counter data

And this needs to be:
  - Read at < 2ms latency (during bid evaluation)
  - Written atomically (every win needs to increment the counter)
  - Consistent enough to actually cap (can't be wildly wrong)

SCALE: 1M+ auctions/second -> 1M+ counter reads/second
                           -> 100K+ counter increments/second
```

This is a genuinely hard distributed systems problem. A naive Redis cluster can't hold 300 billion keys in memory economically. A database is too slow. Even approximate counting is expensive at this scale.

### Count-Min Sketch: Approximate Frequency Counting

The solution most large-scale systems use is a probabilistic data structure called a **Count-Min Sketch**. Instead of maintaining an exact counter for every (user, campaign, window) combination, Count-Min Sketch maintains a small, fixed-size array of counters and uses multiple hash functions to update and query.

```
COUNT-MIN SKETCH STRUCTURE

d = 5 hash functions
w = 10,000 counter buckets per function

Memory: d x w x 4 bytes = 200,000 bytes = ~200KB
(vs. 2.4 terabytes for exact counting!)

UPDATE(user_123, campaign_456, daily_window):
  For each hash function h_i:
    bucket = h_i("user_123:campaign_456:daily") % 10000
    counters[i][bucket] += 1

QUERY(user_123, campaign_456, daily_window):
  For each hash function h_i:
    bucket = h_i("user_123:campaign_456:daily") % 10000
    values.append(counters[i][bucket])
  return min(values)  // The minimum is the best estimate

PROPERTIES:
  - Never undercounts (the minimum can only be inflated by collisions)
  - May overcount (false positives possible, false negatives impossible)
  - Memory: O(d x w) instead of O(users x campaigns)
  - Speed: O(d) per update/query -- faster than hash table lookup

IMPLICATION FOR AD SYSTEMS:
  Overcounting means we might cap too aggressively
  (show fewer ads than intended).
  This is acceptable -- it errs on the side of user experience.
  Undercounting would be the dangerous error (show too many ads).
```

Count-Min Sketch gives us frequency capping that is "good enough" — we might occasionally cap a user before they've technically hit the limit (because of hash collisions inflating the count), but we never let users see significantly more ads than the cap.

### Cross-Device Frequency Capping

Frequency caps per device are easy — just use device-specific cookies or advertising IDs. Cross-device frequency capping (ensuring a user doesn't see the same ad too many times across their phone, laptop, and tablet combined) is much harder because it requires a unified user identity graph.

At Facebook/Meta, users are typically logged in across devices, so cross-device identity is available for logged-in users. Facebook's frequency caps can work at the person level, not the device level, for logged-in users. For non-Facebook inventory (via their Audience Network), logged-out or anonymous users fall back to probabilistic device graphs.

### Real Incident: Meta Frequency Cap Bug (2021)

In October 2021, Meta (then Facebook) experienced a significant ad delivery bug where frequency caps for certain campaigns stopped working correctly. Advertisers reported that individual users were seeing the same ads dozens of times per day — far beyond the configured caps.

The root cause (as reported by industry observers) was a data consistency issue in Meta's distributed counter system. During a high-traffic period, the frequency counter writes were getting batched and delayed for performance reasons, but the reads were happening before the batches were flushed. This created a window where the system "forgot" recent impressions and allowed ads to serve beyond the cap.

The impact was significant: advertisers were charged for impressions that violated their agreed-upon frequency caps. Meta had to issue credits to affected advertisers. More importantly, users who saw the same ads dozens of times experienced degraded quality.

The engineering lesson: frequency cap systems must be designed with write-before-read guarantees. If you increment a counter after serving an ad, there's a race condition where the next auction happens before the counter update is visible. The safer design is to use distributed transactions or to accept slight over-capping (by using a higher-than-desired threshold to account for consistency lag) rather than risk under-capping.

### Brainstorming Q&A

**Q: How does cross-campaign frequency capping work, and why is it important for brand safety?**

Cross-campaign frequency capping operates at the advertiser level rather than the campaign level. An advertiser like Nike might run 20 simultaneous campaigns — summer shoes, winter boots, athletic wear, kids' shoes — each with their own frequency cap per campaign. Without cross-advertiser capping, a user might hit the maximum for each campaign separately, resulting in seeing Nike ads 60 times a day. Cross-campaign capping sets an overall limit: "No user sees Nike ads more than X times per day, across all campaigns combined."

This requires the frequency counter system to maintain hierarchical counters: campaign-level counters (which are cheaper but sufficient for most decisions) and advertiser-level rollup counters. When evaluating a bid, the system checks both. Campaign counter below campaign_cap AND advertiser counter below advertiser_cap is required to serve. The advertiser counter is harder to scale because it aggregates across all campaigns, but it's typically updated less frequently (campaigns don't all serve to the same user simultaneously), so the write rate is manageable.

Brand safety connects to frequency capping because repeated ad exposure on inappropriate content is particularly damaging. Seeing a competitor's ad once on a news article about controversy might be tolerable; seeing that same ad twenty times on the same story signals a targeting failure. Some advertisers set stricter frequency caps for specific contexts (news, political content) as a form of brand safety policy.

**Q: What happens to frequency caps when a user clears their browser cookies?**

Cookie clearing is a nightmare for frequency capping. When a user clears cookies, they get a new cookie ID — as far as the ad system is concerned, they're a new user. All their frequency caps reset to zero. This creates several problems: the user might see the same "you haven't heard our pitch yet" introductory ad campaign over and over, which is both annoying and wasteful. Advertisers who relied on frequency caps to manage lifetime exposure find those caps meaningless for cookie-clearing users.

Some industry estimates suggest 20-30% of browser cookies are cleared or expire within 30 days, which means a significant fraction of frequency cap data is regularly lost. The industry's response has been to move toward more durable identity signals: logged-in user IDs (which persist across cookie clears), email-based identity matching (hashed emails as a stable identifier), and privacy-preserving identifiers like Unified ID 2.0. These allow frequency data to be anchored to a stable person-level identity rather than an ephemeral cookie, but they require users to have accounts and be logged in — a meaningful limitation for anonymous browsing contexts.

---

## Part 7: Measurement & Attribution — Did the Ad Work?

### The Attribution Problem

An advertiser spends $1M on digital advertising in a month and makes $5M in sales. Did the advertising cause the sales? This seems like a simple question but it's one of the hardest problems in marketing. The **attribution problem** is: given that a customer made a purchase, which of the (potentially dozens) of ad exposures along their journey contributed to that purchase, and how much?

Consider a user's journey before buying a pair of Nike running shoes:
1. Saw a Nike display ad on a news website (Monday)
2. Searched "best running shoes 2024" and saw a Nike search ad (Wednesday)
3. Saw a YouTube ad for Nike shoes (Thursday)
4. Clicked a Nike Instagram ad (Saturday)
5. Went directly to Nike.com and purchased (Saturday, 20 minutes later)

Which touchpoint gets credit for the sale?

### Attribution Models

**Last-Click Attribution:** 100% of credit to the last touchpoint before conversion. The Instagram ad gets full credit. Simple to implement, but ignores everything that came before. Tends to overvalue bottom-of-funnel, direct-response channels and undervalue brand building.

**First-Click Attribution:** 100% of credit to the first touchpoint. The Monday display ad gets full credit. Tends to overvalue discovery channels.

**Linear Attribution:** Equal credit to all touchpoints. Each of the four exposures gets 25% credit. Somewhat fair but doesn't capture that some touchpoints matter more than others.

**Time-Decay Attribution:** More recent touchpoints get more credit. The Instagram click-through gets the most, the Monday display gets the least. Assumes recency equals importance.

**Data-Driven Attribution (Algorithmic):** Use machine learning to estimate the true causal contribution of each touchpoint. Google Analytics 4 and Meta's Conversion API both offer this. The model compares conversion rates across users who saw different combinations of touchpoints to estimate marginal contribution. This is the most accurate but requires a lot of data.

### View-Through Attribution

One of the most contested attribution questions: should an ad get credit for a conversion even if the user never clicked it, just viewed it?

**View-through attribution (VTA)** gives credit to ad exposures where the user saw the ad but didn't click. If you saw a Nike display ad on Monday (without clicking) and then bought Nike shoes on Saturday through Google search, VTA would give the display ad some credit for the purchase.

VTA is important for brand advertising — display and video ads often influence decisions without generating direct clicks. But it's also deeply controversial because it's easily gamed: an ad server could claim attribution credit for every impression served, whether the ad actually influenced the user or not. Advertisers are skeptical of vendor-reported view-through attribution because vendors have financial incentive to inflate their contribution.

### Incrementality Testing: The Gold Standard

The only way to truly measure whether advertising causes sales (rather than just correlating with them) is incrementality testing — a controlled experiment:

```
INCREMENTALITY TEST DESIGN

Population: 1,000,000 users who would normally receive ads

Randomly split:
  Treatment (90%): 900,000 users -> Receive ads normally
  Control (10%): 100,000 users -> Ads are suppressed (or replaced by PSAs)

Run for 4 weeks, then measure:
  Treatment conversion rate: 2.3%
  Control conversion rate: 2.0%

Incremental lift: (2.3% - 2.0%) / 2.0% = 15%

This means 15% of conversions in the treatment group were CAUSED by ads.
The other 85% would have happened anyway (organic demand).

Incremental ROAS = Revenue lifted / Ad spend
               = (0.003 x 900,000 users x $100 avg order) / $1M spend
               = $270,000 / $1,000,000
               = 0.27x ROAS (subprofitable if this is the true causal ROAS)
```

Incrementality testing is the gold standard because it isolates the causal effect of advertising. But it requires running experiments at scale, suppressing ads to a holdout group (which costs revenue in the short term), and running tests long enough to get statistical significance. Most advertisers don't run incrementality tests consistently, relying instead on potentially misleading click-based attribution.

### Privacy-Safe Measurement

Post-iOS 14.5 and with GDPR/CCPA constraints, traditional measurement methods (individual-level tracking, cross-site cookies) are increasingly restricted. The industry has developed several privacy-preserving alternatives:

**Google Privacy Sandbox / Attribution Reporting API:** Reports conversion data at the aggregate level, with differential privacy noise added. Individual-level attribution reports are delayed by days to prevent real-time tracking. Currently in origin trial testing in Chrome.

**Apple SKAdNetwork (SKAN):** Apple's framework for measuring app install campaigns. The ad network (Facebook, Google) receives a cryptographically signed notification when an ad leads to an install. The notification includes only the advertiser's app, the ad campaign identifier, and a "conversion value" (6-bit number the advertiser sets to encode purchase amount or event type). Reports are delayed 24-48 hours and aggregated.

**Meta's Conversion API (CAPI):** Allows advertisers to send conversion events directly from their server to Meta, bypassing browser-side tracking. When a user purchases on Nike.com, Nike's server sends a hashed user email to Meta's API, which Meta matches to their user ID to credit the appropriate ad campaign. This maintains measurement capability without relying on browser cookies.

### Brainstorming Q&A

**Q: How does multi-touch attribution work at scale when you have billions of user journeys?**

Multi-touch attribution (MTA) at the scale of Google or Meta requires processing billions of user journeys to build an ML model that can estimate the marginal contribution of each touchpoint type. The typical approach is a logistic regression or neural network trained on conversion/no-conversion outcomes with the sequence of ad exposures as features. The model outputs a Shapley value or marginal contribution estimate for each position in the funnel.

The data pipeline is massive. You need to join ad exposure logs (petabytes of impression data) with conversion logs (purchases, sign-ups, etc.) by user identity. This requires a joined identity graph that links impressions to conversions across different devices and sessions. The join must be done at privacy-safe aggregation levels to comply with regulations — you can't build a model on individual user data if that data crosses GDPR consent boundaries.

The output of the MTA model is a set of fractional credit assignments: "Events of type X at position Y in the funnel receive Z% credit on average." This is then applied to specific campaigns to compute their attributed conversions. The model is retrained periodically (weekly or monthly) as user behavior patterns and the advertising mix change. A key challenge is that the model is trained on observational data — you didn't randomly assign exposures — so it captures correlation, not causation. Advertisers that want true causal estimates must combine MTA with incrementality tests.

---

## Part 8: Ad Fraud Detection — The $68 Billion Problem

### What Is Ad Fraud?

Ad fraud is any activity that causes advertisers to pay for ad impressions or clicks that have no chance of influencing a real human consumer. The key word is "real." Fraud involves fake traffic — bots, scripts, and automated programs generating fake impressions and clicks that look like real users but aren't.

The World Federation of Advertisers estimated that ad fraud cost advertisers $68 billion globally in 2022. Google and Meta spend enormous resources on fraud detection because their business model depends on trust — if advertisers can't trust that they're reaching real humans, they stop spending.

### Types of Fraud

**Click Fraud:** Automated clicking on advertiser ads to drain their budgets. A competitor might pay click farms to click on a rival's Google search ads, burning their daily budget before real customers can see the ad. An ad network might generate fake clicks on their own ads to inflate revenue.

**Impression Fraud:** Generating fake ad impressions. A fraudulent website might automatically load pages (via bots or headless browsers) to create the appearance of having traffic, then sell that fake traffic as real ad impressions.

**Domain Spoofing:** A fraudulent publisher claims to be a premium publisher. When a user loads a legitimate website, an injected iframe secretly loads a different page from the fraudulent publisher. The ad request reports the premium domain name but the ad actually shows on the fraudulent domain (which might not even be visible to the user).

**Ad Stacking:** Multiple ads loaded in the same slot, stacked on top of each other. The top ad is visible; all underlying ads are technically "served" but invisible. Advertisers pay for all of them but only the top ad has any chance of being seen.

**Pixel Stuffing:** An entire advertisement is loaded in a 1x1 pixel — technically served but completely invisible. The publisher collects payment for a "served" impression.

### The Methbot Incident (2016-2017)

Methbot, discovered by White Ops (now HUMAN Security) in December 2016, was the most sophisticated ad fraud operation ever uncovered at that time. A Russian fraud ring called AFT13 operated a network of 500,000-900,000 bots running in data center servers.

The operation:
- Registered 6,000 fake domains that spoofed premium publishers (ESPN, Vogue, Fox News)
- Bots visited these fake pages, which requested ads from legitimate ad exchanges
- Bid requests were sent claiming to be premium publisher inventory
- The bots had realistic simulated mouse movements, fake social media logins, and geography targeting to appear human
- Advertisers paid for premium-looking inventory; ads were seen by nobody

Scale: $3-5 million per day in fraudulent revenue. Over the operation's lifetime, estimated $1 billion in stolen ad spend.

Detection was eventual because:
1. The bots' IP addresses were from data centers (legitimate users come from residential ISPs)
2. Cookie signatures didn't match claimed user histories (these "users" had no browsing history)
3. Traffic patterns were too uniform — real user traffic has natural variation; bot traffic doesn't
4. Video completion rates were impossibly high — real users skip video ads, bots don't

### Detection Signals

Modern fraud detection uses hundreds of signals:

```
FRAUD DETECTION SIGNAL CATEGORIES

NETWORK SIGNALS
+- IP address type (datacenter vs. residential vs. mobile)
+- IP address reputation (known bot IPs blacklisted)
+- ASN (autonomous system number) analysis
+- VPN/proxy detection
+- Geolocation consistency (IP geo vs. device GPS)

BEHAVIORAL SIGNALS
+- Click velocity (rate of clicks per IP/device)
+- Mouse movement patterns (bots move too uniformly)
+- Scroll behavior (bots don't scroll, or scroll too perfectly)
+- Time-on-page distribution (bots leave instantly or stay too long)
+- Click-through rate anomalies (>10% CTR is suspicious)
+- Session length distribution

DEVICE SIGNALS
+- User agent string consistency
+- Browser fingerprint authenticity
+- JavaScript execution environment detection
+- Canvas fingerprint uniqueness
+- WebGL renderer detection (identifies virtual machines)

CONTEXTUAL SIGNALS
+- Publisher reputation score
+- Domain registration recency
+- Traffic source (organic vs. bot-likely sources)
+- Viewability measurement (ad actually in viewport)
+- Video completion patterns
```

### Invalid Traffic (IVT) Categories

The industry standards body (MRC) classifies invalid traffic:

**General IVT (GIVT):** Known bots — search engine crawlers, monitoring services, known bot user agents. Easy to filter. Typically 2-5% of impressions.

**Sophisticated IVT (SIVT):** Bots designed to evade detection — like Methbot. Harder to filter. Typically 5-15% of impressions on the open web, higher on less-vetted inventory.

### Impact on Billing

Ad fraud doesn't just waste money; it corrupts measurement systems. When fraud inflates click counts and impression totals, advertisers get false signals about which campaigns are working. A campaign might appear to have excellent CTR and low CPC — because bots are clicking — while its actual return on investment (sales generated) is terrible. This leads to bad budget allocation decisions.

Most major platforms have policies to credit back advertisers for detected invalid traffic. Google automatically filters IVT from billing and provides reports. But this creates an adversarial dynamic: fraud detection must stay ahead of increasingly sophisticated fraud techniques, and the platforms have financial incentive to catch fraud (they get blacklisted by advertisers if they don't) but also to not look too hard (detected fraud means issuing credits that hurt revenue).

### Brainstorming Q&A

**Q: How do you detect fraud at auction time (before serving the ad) versus post-auction?**

Pre-auction fraud filtering happens in the SSP/exchange before the bid request is even broadcast to DSPs. The SSP evaluates the incoming traffic request (the signal from the publisher saying "a user has arrived") for obvious fraud indicators: datacenter IP addresses, known malicious user agents, impossible geolocation (Canadian IP but claiming to be in Tokyo). If the traffic is clearly fraudulent, the auction is simply not run. This is the cheapest form of fraud filtering — no ad is served, no DSP is bothered, no money is exchanged.

Post-auction fraud filtering happens after an ad is served. The advertiser's impression tracking pixel fires when the ad loads, and that data flows into fraud detection models. Because the ad is already served and billed, post-auction filtering results in credits or chargebacks rather than prevention. The detection signals available post-auction are richer — you can observe full user behavior on the page, mouse movements, scroll patterns, video completion rates — but the damage (fraudulent spend) has already occurred.

The most sophisticated fraud detection combines both: pre-auction filtering for obvious cases, real-time scoring during the auction (a fraud probability score that influences whether DSPs want to bid and at what price), and post-auction analysis for credit reconciliation and model updates. The real-time fraud score is essentially another ML model inference happening alongside the CTR prediction model — both need to complete within the 5-10ms ML budget.

---

## Part 9: Budget Pacing — Spending Money at the Right Rate

### Why Budget Pacing Matters

An advertiser gives their campaign a $10,000 daily budget. They want that budget spent evenly throughout the day so they reach users all day long, not just in the first two hours. But the ad system doesn't know in advance how many auctions will be available or how competitive those auctions will be. If the system bids too aggressively, the budget is exhausted at 9am and the advertiser gets no coverage for the rest of the day. If it bids too conservatively, the budget isn't fully spent and the advertiser gets less reach than they paid for.

**Budget pacing** is the system that throttles bid behavior to match spend rate to the desired curve — usually uniform over the day, sometimes dayparted (more spend during peak hours).

### Smooth Pacing vs. ASAP Pacing

**ASAP (As Soon As Possible) Pacing:** Bid at maximum rates until budget is exhausted. Simple to implement: don't throttle at all, just stop when budget hits zero. Some advertisers explicitly want ASAP pacing — e.g., a flash sale for 3 hours wants all budget spent immediately.

Downsides of ASAP: Budget burns in early morning when traffic is lowest, missing peak-value hours (evenings, lunch). Highly competitive inventory fights at dawn to spend first. Uneven reach over the day.

**Smooth Pacing (Throttle-Based):** The system estimates how much budget should have been spent by each hour and throttles bidding to match. If budget is slightly ahead of pace, the system reduces bid aggressiveness. If behind pace, it increases aggressiveness (bids more, participates in more auctions).

```
SMOOTH PACING ALGORITHM

Setup:
  daily_budget = $10,000
  day_start = 0:00 UTC
  day_end = 24:00 UTC

At any time T:
  elapsed_fraction = (T - day_start) / 24 hours
  target_spent = daily_budget x elapsed_fraction

  If actual_spent > target_spent:
    -> Over-pacing: reduce throttle rate (bid less aggressively)
    -> Skip some auctions entirely (bid probability < 1.0)

  If actual_spent < target_spent:
    -> Under-pacing: increase throttle rate
    -> Participate in more auctions / bid higher

  Throttle rate = target_spend_rate / current_spend_rate
```

### ML-Predicted Pacing

Simple time-based pacing ignores that not all hours have equal value. Traffic volume varies dramatically: almost no traffic at 3am, peaks during commute hours and evening prime time. CPMs also vary by time (competition drives prices up during high-traffic periods, sometimes down during low-traffic periods because supply overwhelms demand).

Modern pacing systems use ML to predict:
1. How much traffic will be available in each upcoming time bucket (hour-level granularity)
2. What CPMs will clear in those buckets
3. What the target audience quality will be

Then budget is allocated to time buckets proportionally to expected value. Spend more in the evening when your target demographic is actively browsing; spend less at 3am when only insomniacs and bots are online.

```
ML PACING BUDGET ALLOCATION

Input features:
  - Time of day / day of week
  - Historical impression volume (same slot, last 4 weeks)
  - Historical CPMs (same slot, last 4 weeks)
  - Current competition level
  - Campaign audience targeting (does this audience peak at specific times?)
  - Cross-timezone audience distribution

Output:
  Hourly budget allocation:
  0am-1am:  $50   (low traffic, low value)
  ...
  6am-7am:  $200  (morning commute starts)
  7am-8am:  $350  (commute peak)
  ...
  8pm-9pm:  $700  (evening prime)
  9pm-10pm: $600
  ...
  TOTAL = $10,000
```

### Cross-Timezone Budget Challenges

A global campaign targeting users in all timezones faces a pacing puzzle. "Evening prime time" is 8pm in New York and 8pm in Los Angeles simultaneously — but these cities are 3 hours apart. A US-targeted campaign might see two evening spikes 3 hours apart. A global campaign has overlapping evening spikes 24 hours a day (it's always prime time somewhere).

The solution: manage budgets at the campaign level across all timezones, not per-timezone. The ML pacing model learns that global campaigns have a smoother traffic curve than regional campaigns and allocates budgets accordingly.

### Underspend vs. Overspend Consequences

**Underspend:** The campaign doesn't exhaust its daily budget. The advertiser paid for $10,000 of reach but only got $8,000 worth. This is a failure of the ad platform — the advertiser gets less than they expected, and the platform earns less revenue than possible.

**Overspend:** The campaign spends more than its budget, potentially charging the advertiser more than they authorized. This is a financial and legal problem. Most platforms guarantee that campaigns won't exceed their daily budget by more than 2x (industry standard), and they credit advertisers for overspend. Preventing overspend requires accurate real-time spend tracking across distributed systems — which is harder than it sounds when you're processing 1M auctions per second across 50 datacenters.

```
BUDGET PACING SYSTEM OVERVIEW

+-------------------------------------------------------------+
|                    BUDGET PACING SYSTEM                      |
|                                                             |
|  +-----------+    +--------------+    +-----------------+  |
|  | ML Budget |    |  Real-Time   |    |  Spend Tracker  |  |
|  | Allocator |-->>|  Throttle    |<<--|  (Redis/Spanner)|  |
|  | (hourly)  |    |  Controller  |    |                 |  |
|  +-----------+    +------+-------+    +--------+--------+  |
|                          |                      |           |
|                          v                      |           |
|                   +--------------+              |           |
|                   | Bid Request  |              |           |
|                   | Processing   |--------------+           |
|                   |              |   (increment counter     |
|                   | Should we    |    on every win)         |
|                   | bid? At      |                          |
|                   | what price?  |                          |
|                   +--------------+                          |
|                                                             |
|  Controls:                                                  |
|  +- Bid probability (skip X% of auctions)                  |
|  +- Max bid multiplier (scale bid up/down)                  |
|  +- Budget pause (hard stop when budget exhausted)         |
+-------------------------------------------------------------+
```

### Brainstorming Q&A

**Q: How do you handle budget pacing when a campaign goes viral and demand spikes unexpectedly?**

Unexpected traffic spikes are a nightmare for budget pacing. Imagine a news event causes millions of people to suddenly visit news websites simultaneously. Advertisers targeting news readers might exhaust their daily budgets in minutes rather than hours. The pacing system needs to detect the spike quickly and throttle aggressively — but there's inherent latency between when spend increases and when the throttle system responds.

Most systems use a combination of reactive and proactive throttling. Reactive throttling measures actual spend rate in 30-second windows and adjusts the throttle multiplier accordingly. If spend in the last 30 seconds was 10x the target rate, reduce the bid probability to 10% immediately. Proactive throttling uses forecasting models that detect early signals of traffic spikes (a sudden 5x increase in bid requests from news publishers) and pre-emptively throttle before budgets are hit.

Some platforms use a budget reserve mechanism: at any given time, 20% of the remaining budget is "locked" and only released during non-spike periods. This provides a buffer against overshooting. The downside is systematic underspend — campaigns routinely spend only 95-98% of their budget because the reserve is never fully deployed. Advertisers and platform revenue teams complain about this, but it's a reasonable trade-off versus the alternative of regularly overspending and having to issue credits.

---

## Part 10: The 45-Minute Interview Framework

### How to Structure Your Answer

When asked "Design an ad serving system" in an L5/L6 interview, candidates often make the mistake of jumping directly into implementation details — sharding Redis, picking Kafka, drawing boxes. The interviewer doesn't need you to list technologies. They need to see you understand the problem space and can make principled trade-offs.

Here is a framework for the first 5 minutes:

**Step 1: Clarify scope (2 minutes)**
"Before I dive in, let me make sure I understand what we're optimizing for. Are we designing the full RTB stack — including the exchange — or are we designing just the DSP's bidding system? Are we optimizing for latency (winning more auctions), for ROI (better CTR prediction), or for operational simplicity? What scale are we targeting — is this a startup entering RTB, or are we building at Google scale?"

**Step 2: State the core constraints (1 minute)**
"The key constraints I see are: 50ms end-to-end latency for auctions, petabyte-scale user profile data, 1M+ auctions per second at peak, and strict budget accuracy requirements. These three are somewhat in tension — faster lookup means more caching which can mean stale data which hurts budget accuracy."

**Step 3: Decompose into 3-4 subsystems (2 minutes)**
- The auction/bidding engine (correctness, latency)
- The targeting/scoring pipeline (ML, user profiles)
- The budget/pacing system (financial correctness)
- The measurement/attribution system (post-auction)

"I'll focus on the bidding engine and targeting pipeline first since they're most latency-sensitive, then talk about how budget tracking and fraud detection plug in."

### The 50ms Budget Breakdown in Interviews

A specific skill that signals L6 thinking: being able to reason about latency budgets from first principles.

```
SHOW THIS BREAKDOWN EXPLICITLY:

"Let me allocate the 50ms budget:
 - Network round-trips: 2-3 hops x ~2ms = 6ms network overhead
 - SSP/Exchange processing: 4ms
 - DSP processing budget: 40ms remaining
   +- User profile lookup (Redis): 3ms
   +- Targeting evaluation: 5ms
   +- Feature computation: 8ms
   +- ML inference: 5ms (first-stage fast model)
   +- Secondary ML (if needed): 5ms
   +- Bid calculation + response serialization: 3ms
   +- Buffer for tail latency: 11ms

 The 11ms buffer is for P99 variance. We target 40ms
 in P50 so that P99 stays under 50ms."
```

Interviewers will follow up on each component. Have answers ready for:
- "How do you handle user profile lookup when Redis is saturated?" (Cache warming, read replicas, probabilistic early termination)
- "What happens when the ML model is too slow?" (Two-stage: fast model for candidate selection, slow model for final ranking)
- "How do you prevent budget overspend?" (Distributed counters with soft limits, pre-compute token budgets, shard by campaign)

### L5 vs L6 Calibration Table

```
+-----------------------------------------------------------------+
|              L5 vs L6 CALIBRATION: AD SERVING DESIGN           |
+--------------------+--------------------+------------------------+
|  DIMENSION         |  L5 SIGNAL         |  L6 SIGNAL             |
+--------------------+--------------------+------------------------+
| Latency reasoning  | "Use Redis for     | Explicit budget alloc. |
|                    | low latency"       | 50ms broken into       |
|                    |                    | components with ratios |
+--------------------+--------------------+------------------------+
| Scale reasoning    | "Shard by user_id" | "10B users x 10K       |
|                    |                    | campaigns = Count-Min  |
|                    |                    | Sketch, here's why"    |
+--------------------+--------------------+------------------------+
| ML integration     | Mentions CTR       | Discusses two-stage    |
|                    | prediction model   | ranking, feature store,|
|                    |                    | training/serving skew  |
+--------------------+--------------------+------------------------+
| Fraud awareness    | "Add fraud         | Distinguishes pre-bid  |
|                    | detection module"  | vs. post-auction       |
|                    |                    | filtering, discusses   |
|                    |                    | IVT categories         |
+--------------------+--------------------+------------------------+
| Budget/pacing      | "Track spend in    | Reasons about ML-based |
|                    | a counter"         | hourly allocation,     |
|                    |                    | overspend risk, cross- |
|                    |                    | timezone complexity    |
+--------------------+--------------------+------------------------+
| Privacy            | Mentions cookies   | Discusses post-iOS     |
|                    |                    | 14.5 world, SKAN,      |
|                    |                    | differential privacy   |
+--------------------+--------------------+------------------------+
| Trade-offs         | Gives one approach | Explicitly considers   |
|                    |                    | multiple approaches,   |
|                    |                    | states which they'd    |
|                    |                    | pick and WHY           |
+--------------------+--------------------+------------------------+
| Auction mechanics  | "Second-price      | Explains GSP, dynamic  |
|                    | auction"           | floors, first-price    |
|                    |                    | switch motivation,     |
|                    |                    | bid shading            |
+--------------------+--------------------+------------------------+
```

### Separating the Three Big Sub-Problems

The most common interview mistake is conflating three distinct sub-problems. Make sure you can discuss each separately:

**Sub-problem 1: The Auction (Latency-Critical)**
- 50ms hard deadline
- Fanout to many DSPs simultaneously
- Auction mechanics (first vs second price, floors)
- Win/loss notifications
- Key metric: P99 latency, bid win rate

**Sub-problem 2: The Scoring/Targeting (ML-Critical)**
- CTR/CVR prediction models
- Feature stores
- User profile lookups
- Quality score computation
- Key metric: AUC of CTR model, calibration accuracy

**Sub-problem 3: The Financial System (Correctness-Critical)**
- Budget pacing and throttling
- Fraud detection and IVT filtering
- Attribution and measurement
- Billing reconciliation
- Key metric: Budget accuracy (target: under 2% overspend), fraud rate detected

### Common Interview Mistakes

**Mistake 1: Skipping latency reasoning.**
Candidates describe what components exist but never reason about how fast each component needs to be. The interviewer is silently hoping you'll say "50ms total, here's how I allocate it." If you don't, they have to ask, and you've already lost points.

**Mistake 2: Proposing a single global database for user profiles.**
"We'll store user profiles in a globally replicated Spanner database." The latency of a cross-regional Spanner read can be 30-50ms alone — consuming the entire auction budget on database overhead. User profiles need to be served from in-memory caches in the same data center as the auction, with asynchronous background updates.

**Mistake 3: Ignoring the advertiser money problem.**
Design discussions often focus on the happy path (winning an auction, showing an ad) and ignore the financial correctness requirements. How do you guarantee that a campaign with a $10,000 daily budget doesn't spend $50,000? How do you ensure spend is tracked accurately when you're making 1M decisions per second across 50 servers? Budget enforcement in a distributed system is a consensus problem — candidates who have studied Raft but not applied it to financial systems miss this connection.

**Mistake 4: Treating fraud detection as an afterthought.**
"And then we'd add some fraud detection." Fraud detection needs to be integrated into the pre-auction pipeline (pre-filtering), the scoring pipeline (fraud probability as a feature), and the post-auction pipeline (IVT filtering and credits). It's not a module you add at the end — it's a cross-cutting concern that touches every component.

**Mistake 5: Not knowing the difference between a DSP and an SSP.**
Some candidates use these terms interchangeably or don't know what they stand for. This is a red flag in an ad serving interview. Know the ecosystem players cold before the interview.

**Mistake 6: Missing the privacy dimension.**
A 2024 or later ad serving design that doesn't mention GDPR consent requirements, cookie deprecation, or post-iOS 14.5 mobile targeting constraints is out of date. Privacy is not a legal add-on; it constrains what data can be collected, how user IDs work, how attribution can be measured, and what ML features are available.

### Brainstorming Q&A

**Q: In a 45-minute interview, how do you decide which part of the ad stack to go deep on when the interviewer says "design an ad serving system"?**

The right answer is to spend the first three to five minutes not designing anything at all — instead, asking scoped clarifying questions. The ad stack is enormous and no interview can cover all of it. Ask the interviewer: "Are we designing the exchange, the DSP, the SSP, or the full end-to-end? Are we optimizing for a publisher-side or advertiser-side problem?" Most interviewers have a specific subsystem in mind. If they say "go broad," you should sketch the full ecosystem in two minutes (a five-box diagram: Advertiser → DSP → Exchange → SSP → Publisher) and then explicitly say: "Given our time budget, I propose we go deep on the DSP bid evaluation pipeline — is that aligned with what you care about?" This scoping move itself signals seniority. Junior candidates start designing immediately and run out of time before reaching the interesting parts.

The second reason scoping matters is that the interesting engineering questions are different in each subsystem. Publisher-side (SSP) care about floor price optimization, header bidding waterfall management, and fill rate maximization. Advertiser-side (DSP) problems center on bid optimization, user profile lookups under latency constraints, and cross-publisher frequency capping. Exchange problems focus on auction fairness, fraud detection, and running the 50ms auction at 10M QPS. If you try to design all three, you'll describe each at "intern-level depth" — just naming components without reasoning about trade-offs — rather than at "staff-level depth" on one.

**Q: What is the most common thing candidates miss when asked to "design budget pacing" in an ad serving interview?**

The most common gap is treating budget pacing as a simple rate-limiting problem — "just check a counter before bidding" — without reasoning about the consistency requirements of that counter in a distributed system. Budget enforcement is a financial contract: if an advertiser's daily budget is $10,000, overspending by $50,000 means you owe them a credit. At Google scale, a DSP might have 50 bid servers each making 200K bid decisions per second. A global consistent counter for budget tracking would require cross-region consensus — adding 30-50ms of latency to every bid decision, which blows the entire 50ms budget. So you need approximate distributed counters, but then you must reason explicitly about the overspend risk. The correct answer involves: (1) each server maintains a local budget shard, (2) shards are aggregated every 1-5 seconds, (3) the system accepts bounded overspend risk of approximately (shard_size × shard_count) in the worst case, (4) this overspend risk is reflected in SLAs and covered by financial reconciliation at the end of day.

The second thing candidates miss is the *underspend* problem, which is just as bad. An advertiser who paid for $10,000 of reach but only got $7,000 worth because the pacing algorithm was too conservative will not renew their campaign. Smooth pacing requires the system to model the day's expected inventory curve — there are more impressions at 8pm than at 3am — and adjust throttling continuously to track the ideal spend curve. This requires a reference forecast (historical traffic model), a feedback control loop, and anomaly handling (what if traffic today is 40% higher than forecast because of breaking news?). Candidates who answer "just divide the budget by 24 hours and check every hour" are describing ASAP pacing with hourly resets, not smooth pacing.

---

## Part 11: Real Incidents and Operational Lessons

### Incident 1: Google Quality Score Algorithm Change (2011)

In 2011, Google made a significant update to its quality score algorithm for AdWords (now Google Ads). The change increased the weight given to landing page quality and relevance. Advertisers with high bids but poor landing pages (slow loading, irrelevant content, high bounce rates) saw their minimum bid requirements jump dramatically overnight — in some cases 10x or more.

The financial impact was severe for some advertisers. Small businesses that had been running profitable campaigns suddenly found their ads were no longer competitive at prices they could afford. Some businesses reported that their ads simply stopped appearing entirely because the new minimum bid exceeded their budget.

Operational lessons:
1. Algorithm changes in auction systems have immediate, significant financial consequences for participants. Changes should be tested in shadow mode (compute new rankings but don't apply them) before going live.
2. Rollouts should be gradual — apply to 1% of traffic, monitor advertiser impact metrics, ramp slowly.
3. Clear communication to affected advertisers is essential. The 2011 change was criticized not just for the impact but for the lack of warning.
4. Build monitoring that can detect sudden shifts in advertiser spend, bid competitiveness, and campaign delivery immediately after a system change.

### Incident 2: Facebook Ad Delivery During the 2020 US Election

During the 2020 US presidential election, Facebook imposed restrictions on political ad targeting. This created unexpected collateral damage: many non-political advertisers saw their CPMs spike dramatically because political advertising budgets were flooding the auction while targeted political ads were restricted.

Election season typically sees CPM increases of 20-30%. In 2020, some advertisers reported CPM increases of 200-300% during the final weeks of the campaign. Campaigns that had set fixed daily budgets were spending their entire budget in a fraction of the normal time, massively reducing reach.

Operational lessons:
1. External events (elections, holidays, news events) can dramatically change the competitive landscape of ad auctions. Pacing systems must be robust to sudden CPM spikes.
2. Advertisers benefit from CPM caps — maximum prices they're willing to pay per impression — which protect against runaway spend during competitive periods.
3. Budget pacing systems should treat "CPM spike" as a distinct state requiring specific throttling responses, not just adjust based on spend rate alone.

### Incident 3: The Meta Frequency Cap Bug (2021, Detail)

As mentioned in Part 6, Meta experienced a frequency capping failure in 2021. The deeper technical story is worth examining.

Meta's frequency cap system relied on distributed counters maintained in a custom key-value store. During a high-traffic period, the write path for counter updates became the bottleneck. Engineers had implemented a write-coalescing optimization: instead of writing each impression counter increment immediately, the system batched updates and wrote them every 500ms. This reduced write load by 50x at the cost of 500ms of eventual consistency.

The bug: the read path for frequency cap evaluation was not aware of the batching delay. When a bid request came in, the system read the counter (which might be 500ms stale), compared it to the cap threshold, and served the ad — only for the counter update to be written 500ms later. At high traffic volumes, the batching delay meant counters were systematically undercounted at read time, allowing ads to serve beyond their caps.

The fix required making the write-coalescing delay visible to the read path. The system was changed to either:
(a) Read counters with a "pending writes" adjustment (add the known batched-but-unwritten increments to the counter value before comparison), or
(b) Reduce the write batching window from 500ms to 50ms during high-frequency campaigns.

Operational lessons:
1. Eventual consistency in financial systems (including ad caps, which affect advertiser billing) requires careful engineering. The lag between write and read visibility must be quantified and either accounted for or eliminated.
2. Write-coalescing optimizations that are safe in low-throughput scenarios can become dangerous in high-throughput scenarios where the coalescing window is a significant fraction of the measurement period.
3. Monitoring for frequency cap violations should be a first-class metric, checked continuously, with automatic alerts when cap breach rates exceed thresholds.

### Incident 4: Ad Serving During AWS Outages

The ad ecosystem is heavily AWS-dependent. When AWS us-east-1 experienced a major outage in December 2021, it took down significant portions of the RTB ecosystem. SSPs and DSPs that ran on AWS lost connectivity, resulting in dramatically reduced auction participation. Publishers that relied on AWS-hosted ad servers saw fill rates drop to near zero.

Publishers with header bidding setups where multiple exchanges compete were more resilient — even if one exchange's infrastructure was down, others continued. Publishers relying on a single exchange waterfall were fully impacted.

Operational lessons:
1. Multi-region deployments are essential for any component in the critical path of ad serving. A single-region outage should reduce capacity, not eliminate it.
2. Header bidding's complexity adds value beyond revenue optimization: it provides genuine redundancy.
3. Publishers should treat their ad server as a mission-critical component deserving the same HA design as their web server.
4. Circuit breakers are essential: if a DSP's bid server is unreachable, the exchange should quickly detect this and stop sending bid requests (saving both the exchange's time and the DSP's timeout budget).

### Incident 5: Criteo's GDPR Compliance Crisis

When GDPR went into effect in May 2018, retargeting companies like Criteo faced an existential crisis. Criteo's entire business model depended on tracking users across websites via third-party cookies. Under GDPR, this tracking required explicit user consent — which most users, when asked, declined to provide.

Criteo's stock dropped 40% in the week after GDPR took effect as advertisers questioned whether their retargeting campaigns could continue. The IAB developed the Transparency and Consent Framework (TCF) as an industry-standard way to gather and communicate GDPR consent across the ad tech stack. But implementation was messy — publishers adopted it inconsistently, and consent strings were complex to parse.

Operational lessons:
1. Privacy regulations can fundamentally break business models. Ad tech systems need to be designed with data minimization and user consent as first-class requirements, not afterthoughts.
2. Consent management requires a new layer of infrastructure: consent strings must be passed with every bid request, respected by every DSP, and stored for audit purposes.
3. Technical solutions to privacy requirements (like Privacy Sandbox) take years to develop and deploy. Ad tech companies that wait for regulations to be finalized before engineering solutions will be caught flat-footed.

### Brainstorming Q&A

**Q: When an AWS region goes down and takes out half the bidders in an RTB auction, how should the exchange behave — keep the auction running with fewer bidders, delay until bidders reconnect, or cancel the impression?**

The exchange must keep running. Pausing an auction to wait for a downed bidder is equivalent to blocking a hospital's triage because one doctor is unavailable — the patient (the publisher's page load) cannot wait. The correct behavior is: maintain a list of "healthy" DSP endpoints using a circuit breaker pattern, and route bid requests only to endpoints that have responded within timeout in recent history. When an AWS region goes down, the exchange's health monitoring should detect the degraded endpoints within 2-3 missed timeouts (roughly 100-150ms at typical 50ms timeouts) and remove them from the active bidder pool. This is standard circuit breaker behavior: fail fast, fail early, and stop sending requests to endpoints that are clearly unavailable. The publisher gets slightly lower revenue (fewer competing bids) but the page loads on time with an ad.

The more interesting question is what happens to the winning DSP's win notification when their bid server went down. If DSP_A's bid server was in us-east-1 and crashed mid-auction, the exchange might have received a bid from DSP_A (sent just before the crash) but DSP_A's server won't be alive to receive the win notification. The exchange should still serve the ad (DSP_A's creative was submitted in the bid response), but DSP_A will not know they won — their spend counter won't update. This creates a reconciliation problem: DSP_A's analytics will show a gap in spend for the outage window. The correct engineering practice is to ensure win notifications are durably queued (not just fire-and-forget UDP) and replayed once the DSP endpoint recovers. Most production exchanges do this via a durable message queue with retry logic.

**Q: The Criteo GDPR example shows that privacy regulations can break business models. What is the equivalent existential risk for a DSP designed today?**

The equivalent existential risk for a DSP designed today is the deprecation of third-party cookies in Chrome. Safari has already blocked third-party cookies since 2017 (via Intelligent Tracking Prevention). Firefox followed. Chrome, which has 65% of global browser market share, announced deprecation multiple times (originally 2022, then 2024, then 2025) and finally began a phased rollout. Third-party cookies are the mechanism by which DSPs build cross-site user profiles — they are how "user abc123 visited running websites" gets connected to "user abc123 is now reading the New York Times." Without cookies, a DSP cannot recognize the same user across different publisher domains. The entire behavioral targeting value proposition — the reason a DSP can claim "we'll show your ad to people likely to buy running shoes" — depends on this cross-site identity graph.

The technical response paths are: (1) invest heavily in probabilistic identity resolution using fingerprinting (device characteristics, IP, behavioral patterns) — legally risky under GDPR and Apple's ATT framework; (2) adopt Google's Privacy Sandbox APIs (Topics API for interest-based targeting, FLEDGE/Protected Audience for retargeting) — which move the auction computation into the browser itself, limiting DSP visibility; (3) pivot to first-party data partnerships with publishers and retailers who have logged-in user bases — essentially becoming a "clean room" data provider; or (4) pivot to contextual targeting, which requires no user identity at all. DSPs that built their competitive advantage entirely on cookie-based behavioral targeting face genuine existential risk. Those that have invested in first-party data relationships, contextual ML models, and Privacy Sandbox integration are better positioned. This is a live architectural challenge in 2024-2026 and a natural interview follow-up question if you mention cookies.

---

## ASCII Diagrams Summary

### Diagram 1: The Full Ad Ecosystem

```
                        THE AD ECOSYSTEM

+--------------------------------------------------------------+
|                                                              |
|   ADVERTISER                             PUBLISHER           |
|   (Nike)                                 (New York Times)    |
|      |                                          |            |
|      v                                          v            |
|   +------+                               +----------+        |
|   | DSP  |                               |   SSP    |        |
|   |      |<<-----------------------------+          |        |
|   | Demand|     Bid Requests             |  Supply  |        |
|   | Side  |                              |  Side    |        |
|   |Platform|     Bid Responses ------->>|  Platform |        |
|   +--+---+                               +----+-----+        |
|      |                                        |              |
|      |           +----------+                 |              |
|      +-------->>|    AD    |<<----------------+              |
|                  | EXCHANGE |                                 |
|                  |          |                                 |
|                  | Auctions |                                 |
|                  | Win/Loss |                                 |
|                  +----------+                                 |
|                       |                                      |
|              +----------v------------------+                  |
|              |   DATA PROVIDERS            |                  |
|              | (DMPs, ID Graphs,           |                  |
|              |  Audience Segments)         |                  |
|              +-----------------------------+                  |
|                                                              |
|  Money flow: Advertiser -> DSP -> Exchange -> SSP -> Publisher |
|  Data flow:  Publisher inventory -> SSP -> Exchange -> DSP   |
|  Creative flow: DSP -> Exchange -> SSP -> User browser       |
+--------------------------------------------------------------+
```

### Diagram 2: RTB Full Flow with Latency

```
RTB AUCTION FULL FLOW

User loads NYT page                              TIME
        |                                         |
        v                                         v
[BROWSER] runs JS ad tag                         0ms
        |
        | HTTP request with user cookie
        v
[NYT SSP (Google Ad Manager)]                    2ms
        | Package bid request (OpenRTB JSON)
        | Include: slot size, page URL, user ID, floor price
        v
[AD EXCHANGE]                                    5ms
        | Fanout bid request to 200+ DSPs SIMULTANEOUSLY
        v ------------------------------------------->>
[DSP #1]        [DSP #2]       [DSP #3]  ...    7ms
  |                |               |
  | Lookup user    |               |
  | profile        |               |
  | Run ML model   |               |
  | Calculate bid  |               |
  v                v               v
[DSP responses arrive back at exchange]         42ms
        | (Bids: $5.00, $3.50, $2.00, no-bid...)
        v
[AD EXCHANGE runs second-price auction]         43ms
  Winner: DSP #1 with $5.00 bid
  Clearing price: $3.51 (second-place + $0.01)
        |
        +-->> Win notification to DSP #1          43ms
        |    (includes clearing price)
        |
        +-->> Loss notifications to all others    43ms
        |
        v
[DSP #1 ad creative server]                     44ms
        | Return ad HTML/image URL
        v
[BROWSER renders ad]                            50ms

DONE. User sees Nike shoe ad. 50ms elapsed.
```

### Diagram 3: Targeting Pipeline

```
TARGETING & SCORING PIPELINE

BID REQUEST arrives at DSP
        |
        v
STEP 1: IDENTITY RESOLUTION (2ms)
  Cookie Sync Table:
  "exchange-user-abc123" -> "dsp-internal-XYZ789"
        |
        v
STEP 2: USER PROFILE LOOKUP (3ms)
  Redis cluster (in-memory):
  "XYZ789" -> {
    interests: [running, fitness],
    in_market: shoe_purchase_intent=0.87,
    demographics: {age: 25-34, gender: M},
    frequency: {nike_camp: 3 impressions today}
  }
        |
        v
STEP 3: TARGETING EVALUATION (5ms)
  For each active campaign, check:
  +- Geographic match? (user in USA: YES)
  +- Demographic match? (25-34 male: YES)
  +- Interest match? (running: YES)
  +- Frequency cap? (3 < 5 cap: OK)
  +- Budget remaining? ($2000 left: YES)
  +- Publisher whitelist? (NYT: YES)

  -> Candidate campaigns: [nike_summer, geico_auto]
        |
        v
STEP 4: FEATURE COMPUTATION (8ms)
  Assemble 500-feature vector:
  +- User features (from profile lookup)
  +- Ad features (creative CTR history)
  +- Context features (NYT sports, above fold, desktop)
  +- Cross features (user x ad interactions)
        |
        v
STEP 5: ML SCORING (5ms)
  Stage 1 - XGBoost: Rank 2 candidates quickly
  Stage 2 - DNN: Precise CTR for top candidate

  nike_summer:  pCTR = 0.031 (3.1%)
  geico_auto:   pCTR = 0.008 (0.8%)
        |
        v
STEP 6: BID CALCULATION (2ms)
  nike_summer wins candidate selection
  Bid = target_CPA x pCVR x bid_multiplier
      = $50 x 0.02 x 0.8 = $0.80 per click
      = $0.80 / 0.031 CTR x 1000 = $25.81 CPM bid
        |
        v
BID RESPONSE: {price: $25.81, creative: nike-summer-ad}
```

### Diagram 4: Budget Pacing System

```
BUDGET PACING SYSTEM

Campaign: Nike Summer Shoes
Daily budget: $10,000
Time: 2pm (50% of day elapsed)
Target spend by now: $5,000
Actual spend: $4,200 (under-pacing by $800)

PACING CALCULATION:
  pace_ratio = actual_spend / target_spend = 4200/5000 = 0.84
  -> Under-pacing: increase aggressiveness

  throttle_rate = 1.0 / 0.84 = 1.19x
  -> Increase bid prices by 19%
  -> Participate in 100% of eligible auctions (no skipping)

AUCTION DECISION FLOW:
  Bid request arrives
        |
        v
  [BUDGET CHECK]
  Remaining: $5,800
  Pace ratio: 0.84
        |
        v
  [THROTTLE DECISION]
  Under-pacing -> bid 1.19x normal bid
  Would have bid $3.00 -> now bid $3.57
        |
        v
  [FREQUENCY CHECK]
  User XYZ789 has seen nike ad 3x today
  Cap is 5x per day -> OK to serve
        |
        v
  [ML SCORING]
  pCTR = 0.031
  Bid = $25.81 CPM (x1.19 throttle = $30.71)
        |
        v
  [SUBMIT BID: $30.71 CPM]
        |
        v (if win)
  [UPDATE SPEND COUNTER]
  actual_spend += clearing_price (e.g., $18.50 CPM)
  -> Write to distributed counter
  -> Re-evaluate pace ratio every 30 seconds
```

---

## Exercises

1. **Bid request parsing:** Given an OpenRTB 2.5 bid request JSON, write a function that extracts: user ID, floor price, ad slot dimensions, and page URL. Validate that required fields are present.

2. **Second-price auction:** Implement a function `run_auction(bids: List[Bid], floor_price: float) -> Optional[AuctionResult]` where `AuctionResult` contains the winning bid, winning DSP, and clearing price. Handle edge cases: all bids below floor, single bid, tied bids.

3. **Count-Min Sketch:** Implement a basic Count-Min Sketch with d=5 hash functions and w=10,000 buckets. Implement `increment(key)` and `estimate(key)` methods. Test with 1 million increments on 100,000 unique keys and measure memory usage vs. an exact counter dict.

4. **Frequency cap checker:** Design a frequency cap check function that uses Count-Min Sketch for approximate counting. Parameters: user_id, campaign_id, time_window, cap_limit. The function should return True (can serve) or False (capped). Handle daily vs. weekly windows.

5. **Budget pacing simulator:** Simulate a 24-hour campaign with $10,000 daily budget, 1000 auctions per minute, and variable CPMs (low at night, high at 8am and 8pm). Implement both ASAP and smooth pacing. Plot remaining budget over time for each pacing strategy.

6. **CTR model calibration:** Given a CTR prediction model that outputs scores between 0 and 1, and a test dataset with actual click/no-click labels, compute the calibration curve (reliability diagram). Identify whether the model is well-calibrated, overconfident, or underconfident.

7. **Fraud signal classifier:** Given a dataset of ad requests with features (IP type, click velocity, user agent consistency, geographic consistency, mouse movement variance), train a binary classifier to distinguish legitimate vs. fraudulent traffic. Evaluate with precision, recall, and F1 score.

8. **Latency budget allocator:** Given a total latency budget of 50ms and the following components: network (variable, 2-15ms depending on geographic distance), user lookup (3-8ms), feature computation (5-12ms), ML inference (3-10ms), build an algorithm that dynamically adjusts which ML models to run (fast vs. slow) based on remaining time budget after the user lookup completes.

---

## Homework

1. **Read the OpenRTB 2.5 specification** (available free from IAB): Focus on the `BidRequest`, `BidResponse`, `Impression`, and `User` objects. Understand which fields are required vs. optional and why. Think about: what information is missing from the spec that you'd want as a DSP? What information is included that raises privacy concerns?

2. **Study the IAB Content Taxonomy v2.2**: Understand how the 700+ content categories are organized hierarchically. Think about: how would you build a classifier that categorizes web pages into IAB categories using the page's text content? What ML approach would you use?

3. **Trace an ad on a real website**: Install a browser extension like "The Ad Server" or examine network requests in Chrome DevTools while loading a major publisher (CNN, NYT, etc.). Identify the bid requests going out and the ad creative coming back. Count how many ad tech companies are involved in a single page load. (Spoiler: it's often 30-50.)

4. **Research Google's Privacy Sandbox**: Read about the Topics API (Google's replacement for interest-based targeting without third-party cookies) and the Attribution Reporting API (privacy-preserving attribution). Write a one-page analysis: does Privacy Sandbox actually protect user privacy, or does it primarily serve Google's business interests? Support your argument with technical evidence.

5. **Design exercise**: Design a system that allows cross-device frequency capping for 100M users across 10,000 active campaigns without relying on user login. You can only use browser fingerprinting, IP matching, and probabilistic signals. What is the accuracy of your frequency cap? What percentage of cap violations (seeing the same ad more than allowed) would you expect? How would you measure and monitor this?

---

## Common Interview Mistakes Checklist

- [ ] Failed to ask for scope clarification before designing (which part of the ad stack?)
- [ ] Didn't articulate the 50ms latency budget explicitly
- [ ] Proposed a single database for user profiles without addressing cross-region latency
- [ ] Ignored budget pacing and financial correctness requirements
- [ ] Mentioned fraud detection without explaining pre-bid vs. post-auction distinction
- [ ] Didn't know the difference between DSP, SSP, and Ad Exchange
- [ ] Didn't mention privacy constraints (GDPR, iOS 14.5) — these affect the design
- [ ] Skipped the auction mechanics (second price, quality score) entirely
- [ ] Treated the ML scoring model as a black box without discussing the feature store or training/serving skew
- [ ] Didn't reason about the Count-Min Sketch solution for frequency cap scale

---

## KEY TAKEAWAYS

```
+-------------------------------------------------------------------+
|                         KEY TAKEAWAYS                             |
|                Chapter 89: Ad Serving & RTB                       |
+-------------------------------------------------------------------+
|                                                                   |
|  1. THE 50ms RULE                                                 |
|     The auction runs in 50ms. This is non-negotiable. Every      |
|     engineering decision must be evaluated against this clock.    |
|     In-memory lookup > database query. Fast ML > perfect ML.     |
|                                                                   |
|  2. THE ECOSYSTEM IS LAYERED                                      |
|     Publisher -> SSP -> Exchange -> DSP -> Advertiser.            |
|     Each layer adds value but also takes a cut. Know what         |
|     each layer does before your interview.                        |
|                                                                   |
|  3. AD RANK IS NOT BID                                            |
|     Ad Rank = Bid x Quality Score. The highest bidder doesn't    |
|     always win. This aligns incentives toward relevant ads.       |
|                                                                   |
|  4. FREQUENCY CAPPING IS APPROXIMATE                              |
|     Count-Min Sketch solves the 100B-key problem. It can          |
|     overcount (serves as a safety net) but never undercounts.     |
|     Approximate is fine. Perfect is impossible at this scale.     |
|                                                                   |
|  5. ML HAS THREE JOBS                                             |
|     CTR prediction (who will click), bid shading (what to bid    |
|     in first-price auctions), and budget pacing (when to bid).    |
|     All three must complete in under 15ms combined.               |
|                                                                   |
|  6. FRAUD IS SYSTEMIC, NOT INCIDENTAL                             |
|     $68B/year in fraud. Methbot alone stole ~$1B. Detection      |
|     must be integrated at every layer: pre-bid, at-bid, and      |
|     post-bid. No single filter catches everything.                |
|                                                                   |
|  7. PRIVACY CHANGES EVERYTHING                                    |
|     iOS 14.5 broke mobile attribution. Cookie deprecation         |
|     threatens behavioral targeting. GDPR changed data             |
|     collection. Modern ad systems must be privacy-first.          |
|                                                                   |
|  8. BUDGET PACING IS A FINANCIAL CONTRACT                         |
|     If you overspend, you issue credits. If you underspend,       |
|     you're failing the advertiser. Distributed spend tracking     |
|     with strong consistency is non-negotiable.                    |
|                                                                   |
|  9. THE SYSTEM IS ADVERSARIAL                                     |
|     Publishers want high floors. Advertisers want low prices.     |
|     Fraudsters want to steal money. Regulators want privacy.      |
|     All four forces act simultaneously on the same system.        |
|                                                                   |
|  10. SECOND PRICE IS ALMOST GONE                                  |
|      The industry moved to first-price auctions 2017-2019.        |
|      DSPs now need bid shading algorithms. Know why the switch    |
|      happened and what bid shading requires.                      |
|                                                                   |
|  ------------------------------------------------------------------  |
|  THE L6 SIGNAL: You can hold all three sub-problems               |
|  (auction, targeting, measurement) in your head at once,          |
|  reason about their interactions, and make principled             |
|  trade-offs under the 50ms clock without hand-waving.             |
+-------------------------------------------------------------------+
```

---

---

## Part 12: The Full 50ms Auction Deep Dive

### Tracing a Single Ad Request Millisecond by Millisecond

The RTB auction is often described at a high level — "a bid request goes out, bids come back, winner is selected." That abstraction hides a remarkable amount of engineering. Let's trace one real ad request through a real DSP, millisecond by millisecond, with full detail on what can go wrong at each stage.

**Setup:** A user on a laptop in New York City loads CNN.com. The page has a 300x250 banner slot. CNN's SSP (Google Ad Manager) has determined the floor price is $2.00 CPM. The SSP sends a bid request simultaneously to 200 eligible DSPs. This is the story of one DSP's 50ms race.

---

### 0-5ms: Bid Request Received and Parsed

The bid request arrives as a raw TCP stream at the DSP's bid server in Ashburn, VA (co-located with the exchange's servers to minimize network latency). The 50ms clock starts the moment the first byte arrives — not when the full packet is received.

The bid server is running a custom high-performance HTTP/2 server, not a general-purpose framework like nginx or gunicorn. General-purpose web servers add 2-5ms of overhead. At 50ms budget, that's unacceptable. The server is single-threaded per CPU core with an event loop (similar to how Node.js works but in C++), processing thousands of bid requests concurrently without context-switch overhead.

Parsing: The bid request is encoded as either JSON (~3KB) or Protocol Buffers (~800 bytes). Protocol Buffers are preferred because protobuf deserialization is 5-10x faster than JSON parsing. The server extracts the key fields:
- `user.id` — the user's anonymized identifier (cookie hash or device ID)
- `imp[0].bidfloor` — floor price ($2.00)
- `site.page` — page URL ("cnn.com/technology/...")
- `imp[0].banner.{w,h}` — creative dimensions (300x250)
- `tmax` — timeout (50ms)
- `device.geo.metro` — geographic market (New York DMA 501)

Validation takes ~0.5ms: check required fields, verify bid floor is parseable as a float, check the `tmax` is nonzero. If any required field is malformed, the server sends a "no-bid" response immediately rather than wasting time.

**What can go wrong:** A malformed bid request (missing required fields, invalid JSON, oversized payload >10KB) triggers an immediate no-bid. The exchange is notified. If malformed requests come from a specific exchange endpoint frequently, the DSP's circuit breaker flags that endpoint for investigation.

**Clock checkpoint: 5ms elapsed. 45ms remaining.**

---

### 5-15ms: User Profile Lookup

The user's anonymized ID (`user-hashed-abc123`) is the key to unlocking the targeting goldmine. The DSP's profile store contains behavioral data on hundreds of millions of users: what product categories they've browsed, what campaigns they've seen, how many times they've clicked on ads, which demographic segments they're inferred to belong to.

This data lives in a distributed key-value store — either Redis Cluster (for sub-millisecond lookups), Bigtable (for structured column-family data), or a custom in-memory store (like Aerospike, purpose-built for ad tech). The lookup is a single key read: `GET user:abc123`.

The profile returned might look like:

```
{
  "segments": ["running:high-intent", "male:25-34", "nyc-metro"],
  "recent_events": [
    {"event": "visited nike.com", "ts": 1700000001, "age_hours": 2},
    {"event": "searched running shoes", "ts": 1700000000, "age_hours": 3}
  ],
  "frequency": {
    "nike-summer-campaign": {"count": 1, "last_seen": 1699990000}
  },
  "predicted_ltv_bucket": "high"
}
```

The lookup goes to the nearest Bigtable/Redis replica in the same data center. Cross-region calls are forbidden — the 30ms round-trip to California would consume the entire remaining budget. If the local replica doesn't have the user (cache miss), the system falls back to a default "anonymous user" profile. It does NOT wait for a cross-region fetch.

**Cookie sync problem:** The user's ID in the bid request is the exchange's identifier for this user. The DSP uses its own internal user ID. Matching these IDs requires a lookup in a cookie sync table: `exchange_user_abc123 → dsp_internal_user_xyz789`. This table is maintained by a background cookie sync process that runs 24/7, matching user IDs between the DSP's cookie (set when the user previously visited a DSP-affiliated publisher) and exchange identifiers via redirect chains. If the sync table has no entry for this user, the DSP treats them as unknown.

**What can go wrong:** If the Bigtable read exceeds 10ms (99th percentile SLA), the bid server uses a timeout and falls back to anonymous profile. This degrades targeting quality (can't apply behavioral segments) but keeps the auction timeline intact. A slow user profile lookup is one of the most common causes of DSP timeout violations.

**Clock checkpoint: 15ms elapsed. 35ms remaining.**

---

### 15-30ms: Candidate Ad Selection and ML CTR Scoring

Given the user profile, the DSP must find all eligible ads from its campaign catalog and score each one. This is the most computationally intensive step.

**Candidate selection:** The campaign catalog might contain 50,000 active line items (ads). Not all are eligible for this impression. The DSP runs targeting filters:

```
TARGETING FILTER PIPELINE (must complete in ~5ms):

1. Geo filter:      Is user in campaign's target geos?
                    user.metro=501, campaign.geos=[501,502,503] → PASS

2. Dimension filter: Does 300x250 match any creatives in campaign?
                    campaign has [300x250, 728x90] → PASS

3. Domain filter:   Is cnn.com in campaign's allowlist?
                    campaign allowlist = ["*"] (all domains) → PASS

4. Floor filter:    Is campaign's max_bid >= floor ($2.00)?
                    campaign.max_bid = $8.00 → PASS

5. Frequency filter: Has user seen this ad too many times?
                    user.freq[nike-summer] = 1, cap = 10 → PASS

6. Budget filter:   Does campaign have remaining budget?
                    remaining = $4,200 → PASS

Result: 47 eligible line items out of 50,000
```

This filtering runs against an in-memory index — not a database. The campaign catalog is loaded into RAM at startup and updated via a background streaming pipeline (Kafka → local cache) with typical lag of 30 seconds. The index uses bitset operations for maximum throughput: each targeting criterion is a bitmap, and AND-ing bitmaps across dimensions is extremely fast.

**ML CTR Scoring:** For each of the 47 eligible ads, the DSP predicts the probability that this user will click. The CTR prediction model is typically a gradient boosted tree (XGBoost/LightGBM) or a shallow neural network — NOT a deep transformer. Deep models are too slow (>20ms inference). The features include:

- User segment embeddings (running:high-intent maps to a 32-dim vector)
- Page context features (URL category: "technology/gadgets" → IAB category embedding)
- Ad features (300x250 banner, tech category, Nike brand)
- Historical performance (this ad has 2.1% CTR on similar users)
- Time features (Wednesday 8pm → higher CTR than Wednesday 3am)
- Geographic features (NYC DMA)

The top-scoring ad is selected. Let's say it's Nike's running shoes ad with predicted CTR of 3.1% (0.031).

**Clock checkpoint: 30ms elapsed. 20ms remaining.**

---

### 30-40ms: Auction Computation — Ranking, Second-Price / Bid Shading

The bid price is not simply `max_bid_from_campaign`. In a first-price auction (the current standard), the DSP uses bid shading to avoid overpaying.

**Bid shading calculation:**

```
VALUE TO ADVERTISER:
  pCTR = 0.031 (3.1% chance of click)
  CPC_goal = $1.00 per click (advertiser's target)
  Raw value per impression = pCTR × CPC_goal × 1000 = $31.00 CPM

CAMPAIGN MAX BID: $8.00 CPM (campaign hard cap)
→ Raw value ($31.00) exceeds max bid, so cap at $8.00

BID SHADING (first-price adjustment):
  Historical clearing prices for similar impressions:
    p50 = $2.80, p75 = $4.20, p90 = $5.80
  Bid shading model predicts: "bid $3.50 to win 78% of eligible auctions"
  (bidding higher than $3.50 wins only 15% more auctions at much higher cost)

FINAL BID: $3.50 CPM
  (above floor of $2.00, below max of $8.00, shaded from raw value)
```

The bid computation also checks quality score adjustments (if the exchange uses a Google-style Ad Rank), applies any real-time budget pacing adjustments (if the campaign is under-pacing, the throttle multiplier might push the bid to $3.50 × 1.15 = $4.03), and verifies the bid is above the floor.

**Quality Score:** Some exchanges compute a quality score based on ad relevance and historical performance. High-quality ads get an effective discount — they can win with lower bids than poorly-performing ads. The DSP retrieves precomputed quality scores from a local cache. These are updated daily, not in real-time.

**Clock checkpoint: 40ms elapsed. 10ms remaining.**

---

### 40-50ms: Ad Creative Retrieval and Response Encoding

The bid response must include either a creative ID (referencing a pre-cached creative) or the actual creative HTML/markup. Pre-caching is always preferred.

**Creative caching:** When a campaign is created, the DSP's creative processor fetches all associated creative assets (images, HTML5 banners, video URLs), validates them (checking for malware, prohibited content), and stores a pre-rendered `adm` field (ad markup) in the bid server's local memory. At bid time, creative retrieval is just a memory copy — no network I/O needed. This is crucial: if creative retrieval required a network call, you'd spend 5-10ms on it and have nothing left.

**Response encoding:**

```json
{
  "id": "auction-abc-123",
  "seatbid": [{
    "bid": [{
      "id": "dsp-bid-$(uuid)",
      "impid": "1",
      "price": 3.50,
      "adid": "nike-shoes-summer-2024",
      "nurl": "https://dsp.example.com/win?p=${AUCTION_PRICE}&imp=${AUCTION_ID}",
      "lurl": "https://dsp.example.com/loss?r=${AUCTION_LOSS_REASON}",
      "adm": "<div>...[pre-cached Nike HTML creative]...</div>",
      "crid": "nike-shoes-summer-300x250-v3",
      "w": 300,
      "h": 250
    }]
  }],
  "cur": "USD"
}
```

Encoding this protobuf/JSON response takes ~1ms. The bid server sends the response over the existing TCP connection. The exchange must receive it before the 50ms deadline.

**Clock checkpoint: 48ms elapsed. 2ms for network egress.**

---

### ASCII Timing Diagram

```
DSP BID SERVER: SINGLE IMPRESSION TIMELINE
============================================

0ms        10ms       20ms       30ms       40ms       50ms
|----------|----------|----------|----------|----------|
|          |          |          |          |          |
|=RECV/PARSE=|                                         |
  0-5ms: Request received + parsed (protobuf decode)

           |=====USER LOOKUP======|                    |
             5-15ms: Bigtable/Redis read (10ms budget)
             [if >10ms: use anonymous profile fallback]

                      |==CANDIDATES + CTR ML SCORING===|
                        15-30ms: filter 50K→47 ads,
                                 run XGBoost inference

                                  |==AUCTION COMPUTE==|
                                    30-40ms: bid shade,
                                    quality score, pacing

                                            |=ENCODE/SEND=|
                                              40-48ms:
                                              serialize + TCP send

                                                    |--MARGIN--|
                                                      48-50ms:
                                                      2ms safety margin

FAILURE MODES:
  User lookup >10ms  → anonymous fallback, continue
  Creative not found → no-bid (don't serve unknown creative)
  ML inference >15ms → use pre-computed default bid, continue
  Total >48ms        → send no-bid preemptively (don't timeout)
```

---

### Timeout Handling and Fallbacks

The DSP bid server has a internal deadline of **48ms** (2ms less than the exchange timeout). If any internal step looks like it will run over, the bid server takes one of two actions:

1. **Skip and degrade:** Skip the slow step (ML scoring, profile lookup) and use cached defaults. The bid price might be less optimal but still valid.

2. **Send a no-bid:** If the system cannot produce a valid bid in time, it sends an empty response immediately. This is better than timing out — a timeout causes the exchange to log a violation and penalize the DSP's future traffic.

The bid server measures p99 latency for each step. If p99 for user lookups creeps from 8ms to 14ms (over the budget), the on-call engineer gets alerted. The fix might be: replicate Bigtable shards closer, increase cache TTL so fewer requests hit Bigtable, or upgrade the Bigtable nodes.

**Adaptive timeout:** Some advanced DSPs implement adaptive bid deadlines — if the user lookup came back quickly (3ms instead of 10ms), the system can afford a slower, more expensive ML model for CTR scoring. If the user lookup was slow (9ms), the system falls back to a faster model. This "budget-aware" inference selection can improve average bid quality without violating p99 latency.

---

### Intern to Staff Progression: The 50ms Auction

**Intern:** Knows the auction has a 50ms deadline and that the DSP needs to respond with a bid. Can describe the basic steps: receive request, look up user, calculate bid, respond.

**Junior (L3):** Understands the latency budget breakdown — how each step gets a time allocation and that network latency is the dominant constraint on DSP server placement. Knows that user lookups must be in-memory (Redis/Bigtable) and cannot go to a transactional database.

**Mid-level (L4):** Understands the failure modes at each step and the fallback behavior. Can reason about the trade-off between bid quality (full profile + sophisticated ML) and bid timeliness (degraded profile + simple model). Knows about cookie sync and why the DSP might not recognize a user even if they've visited DSP-affiliated sites.

**Senior (L5):** Understands the campaign indexing problem — how to filter 50,000 campaigns to 47 candidates in under 5ms using bitmap indexes. Can design the feature store pipeline from raw event logs to ML-ready features with low skew. Knows what "training-serving skew" means and how to detect it in production.

**Staff (L6):** Can design the full adaptive bid server that dynamically adjusts its internal pipeline based on available time budget. Understands the economic implications of each failure mode — a no-bid loses revenue but protects quality score; a timeout degrades the exchange relationship; a degraded bid (no ML) reduces win rate and ROI. Can reason about the system-level optimization: sometimes deliberately not bidding on expensive impressions improves campaign ROI even though it reduces auction participation. Understands that the 50ms constraint is not just a technical requirement but an economic equilibrium — it's what publishers are willing to tolerate before user experience suffers.

### Brainstorming Q&A

**Q: Why don't DSPs use GPUs for ML inference at bid time, given that GPUs are much faster for matrix operations?**

GPUs excel at batch inference — processing thousands of samples simultaneously through a neural network. They achieve this by loading data into GPU memory, running parallel matrix operations, and returning results in bulk. The overhead of this setup (data transfer to GPU memory, kernel launch) is typically 1-5ms. For a workload where you process thousands of bid requests per second, you could batch them and send them to a GPU together — but this requires waiting for a batch to fill before processing begins, which introduces queuing latency. If the batch window is 5ms (collect 5ms of requests, then GPU-process them all at once), you've added 5ms of latency before processing even begins. In a 50ms budget, 5ms of queue latency is unaffordable.

The practical solution most DSPs use is CPUs with SIMD (Single Instruction Multiple Data) vector operations and highly optimized gradient-boosted tree implementations. XGBoost and LightGBM, compiled with AVX-512 instructions, can evaluate a decision tree model with 1,000 trees and 6 leaves per tree in under 1ms on a modern CPU. This is fast enough for bid-time inference. GPUs are used in the DSP's training pipeline (training new CTR models on terabytes of historical data) but not in the serving path. Some cutting-edge DSPs use specialized inference hardware (Google's TPUs in TPU pods, or custom ASICs like Meta's MTIA) for models that are too large for CPU inference — but these are exceptions, not the norm.

**Q: What happens to the win notification if the DSP's server crashes immediately after sending the bid but before receiving the win notification?**

This creates a ghost win scenario. The exchange received and accepted the bid, served the ad creative (which was embedded in the bid response), and the user saw the ad. But the DSP's server crashed before receiving the win notification. From the DSP's perspective, this impression never happened: no win was recorded, no spend was debited from the campaign budget, and the frequency counter was never incremented for that user.

The consequences are: (1) the advertiser was effectively served an impression for free — the DSP paid the exchange (win notifications trigger billing) but the DSP's internal records show no spend, meaning the DSP absorbed the cost without charging the advertiser; (2) the user's frequency counter undercount means they might see the same ad again sooner than intended; (3) the CTR model doesn't receive a training signal for this impression (no win recorded means no click/no-click label).

Production DSPs handle this through durable win notification replay. The exchange queues win notifications in a persistent system (Kafka, Pub/Sub) rather than sending fire-and-forget UDP. If the DSP endpoint is down, notifications queue up and are delivered when the DSP recovers. The DSP's win notification handler must be idempotent (processing the same win twice should not double-debit the budget). Most implementations use impression ID deduplication: if win notification for `imp_id_xyz` has already been processed, drop the duplicate.

---

## Part 13: Privacy and the Future of Ad Tech

### Why Third-Party Cookies Are Dying

The third-party cookie was invented in 1994 by Netscape. Its original purpose was innocent: allow websites to remember user preferences. But it was quickly repurposed by ad networks. When you visit Site A, Site A can load a 1-pixel image from AdNetwork.com. AdNetwork.com sets a cookie in your browser. When you visit Site B, Site B also loads a pixel from AdNetwork.com. Now AdNetwork.com knows you visited both Site A and Site B — and can build a browsing history across the entire web, without you ever directly interacting with AdNetwork.com.

This cross-site tracking became the foundation of behavioral advertising. It is also, by most definitions, a form of surveillance that users never explicitly agreed to. Regulators noticed. Browsers noticed. Users noticed (the ad for the shoes you looked at once that followed you everywhere for two weeks was deeply creepy). The resulting backlash is destroying the technical foundation that RTB was built on.

**Safari's Intelligent Tracking Prevention (ITP):** Apple began restricting third-party cookies in Safari in 2017. ITP now completely blocks third-party cookies and aggressively limits first-party cookies set via JavaScript (capping their lifetime at 7 days or 24 hours in some contexts). Since Safari has ~35% of mobile browser market share and ~20% of desktop, a large fraction of RTB auctions now have no user behavioral profile available for Safari users.

**Firefox's Enhanced Tracking Protection (ETP):** Mozilla began blocking third-party cookies from known trackers by default in 2019. Firefox's market share (~4%) is smaller but the signal is clear: browsers are increasingly hostile to third-party cookies.

**Chrome's Privacy Sandbox:** Google announced that Chrome would deprecate third-party cookies, with a target of completing the transition by 2024. (This timeline has slipped multiple times — as of mid-2025, phased deprecation is underway for a small percentage of users.) Chrome's 65% market share makes this the existential moment for cookie-based ad targeting. Google's solution, Privacy Sandbox, replaces third-party cookies with a set of privacy-preserving APIs that move computation into the browser.

---

### Google's Topics API

The Topics API is Google's replacement for interest-based targeting. Instead of an ad network tracking your browsing history across sites, the browser itself observes your browsing, classifies the sites you visit into a curated taxonomy of topics (about 300-500 topics like "running shoes," "cooking," "travel"), and stores the top 5 topics for each of the past 3 weeks — entirely locally in the browser.

When you visit an ad-enabled site, the site can call `document.browsingTopics()`. The browser returns up to 3 topics: one from each of the past 3 weeks, randomly selected from the stored top-5. Crucially, the browser adds one fake topic with a small probability (to provide plausible deniability), and the API only returns topics that the requesting site could have independently observed (preventing cross-site leakage).

**What this means for RTB architecture:**
- The DSP no longer maintains a centralized user profile database. Topics are computed locally by the browser.
- The bid request includes the user's topics (sent to the SSP/exchange from the browser).
- DSPs must retrain targeting models on topics (coarser-grained than cookie-based segments) instead of behavioral signals.
- There is no cross-site identity — the DSP cannot connect the same user's sessions on different publishers.
- Frequency capping across sites becomes impossible without a new mechanism (FLEDGE/Protected Audience solves this differently).

The Topics API is significantly less powerful than cookie-based behavioral targeting. A cookie-based DSP might know a user visited Nike.com three times this week, googled "Brooks running shoes" yesterday, and added a shoe to their cart on REI.com. The Topics API tells the DSP only that the user has "running" as a topic. The targeting fidelity is dramatically reduced — which is both a privacy win and a revenue impact.

---

### FLEDGE / Protected Audience API

The Protected Audience API (previously called FLEDGE) is Google's replacement for retargeting — showing ads to users who previously visited an advertiser's site. This is the use case that generates the "the shoe that followed me everywhere" phenomenon.

The key innovation: **the auction runs inside the browser**, not on an ad exchange server.

Here's how it works:
1. When you visit Nike.com, Nike's JavaScript calls `navigator.joinAdInterestGroup()` to add your browser to the "Nike shoe shoppers" interest group. This is stored locally in the browser — no data leaves to Nike's server.
2. When you visit CNN.com, the SSP's JavaScript triggers a Protected Audience auction.
3. The browser fetches bid logic scripts from each DSP that has added you to their interest groups. These scripts run inside a sandboxed JavaScript environment in the browser.
4. Each DSP's bid script receives limited information (your interest group membership, the ad slot details) and returns a bid price. It cannot communicate with the DSP's servers during this computation — no user data leaves the browser.
5. The browser runs the auction, selects the winner, and renders the winning ad.

**Architectural implications:** The DSP's bid server is essentially removed from the per-impression decision loop for retargeting. The DSP pre-uploads bid logic and ML model parameters (as downloadable scripts) that run in the browser. This is a fundamental inversion: instead of user data going to servers for processing, server-prepared logic comes to the user's browser. DSPs must shift from real-time server-side bidding to pre-computed, downloadable bid strategies.

---

### Apple's SKAdNetwork for Mobile Attribution

On mobile, the equivalent of third-party cookies was IDFA (Identifier for Advertisers) — a device-level ID that apps could read and share with ad networks. If App A (a game) shared your IDFA with an ad network, and you later installed App B (another game) after clicking an ad, the ad network could connect your IDFA from both events and attribute the install to the ad. This enabled precise mobile attribution.

iOS 14.5 (April 2021) required apps to ask permission before reading IDFA. The prompt says: "Allow [App] to track your activity across other companies' apps and websites?" Approximately 75-85% of users decline. IDFA became effectively unavailable for most advertising use cases.

Apple's alternative is **SKAdNetwork**: Apple's privacy-preserving attribution framework. When a user clicks an ad and later installs an app, Apple sends a cryptographically signed postback to the ad network confirming: "Campaign X drove an install." The postback:
- Is delayed 24-48 hours (to prevent fingerprinting via timing)
- Includes only coarse data (campaign ID, a "conversion value" limited to 6 bits = 64 possible values)
- Is sent directly from Apple's servers, not from the user's device (Apple acts as a privacy intermediary)
- Does not identify the individual user

SKAdNetwork dramatically reduced the precision of mobile attribution. An advertiser previously might know "User Jane Doe, age 34, clicked this ad, installed the app, spent $47 in-app, came from campaign X, creative Y." With SKAdNetwork, they know "Campaign X drove some installs; the average install value was approximately in bucket 3 (which corresponds to $20-$50)." The granularity reduction makes it much harder to optimize for LTV (lifetime value) and impossible to build lookalike audiences from high-value user characteristics.

---

### First-Party Data Strategy and Retail Media

The death of third-party cookies and IDFA has created a flight to first-party data — behavioral information collected directly from users who have a direct relationship with a brand or publisher. The companies with the most valuable first-party data are turning it into ad revenue.

**Retail Media Networks:** Amazon built a $45B/year ad business largely on first-party purchase data. Walmart Connect, Target's Roundel, Kroger Precision Marketing, and Home Depot's Orange Apron Media are all retail media networks — they let advertisers reach shoppers based on actual purchase history. This data is far more valuable than cookie-based browsing signals because it reflects actual purchase intent backed by real transactions. A DSP that can access Walmart's purchase data knows a user buys specific product categories at specific price points — vastly more predictive than "this user visited a product category page."

**Clean Rooms:** When two companies want to combine their first-party data without sharing raw user records (which might violate privacy regulations), they use clean rooms — secure computation environments where data is joined and aggregated without either party seeing the other's raw data. AWS Clean Rooms, Google Ads Data Hub, and Snowflake Data Clean Rooms allow advertisers to combine their CRM data with publisher data to measure campaign reach against their own customers without the publisher seeing the advertiser's customer list or vice versa.

**Architecture implication:** The DSP of 2024 onward needs to integrate with clean room APIs, first-party data onboarding pipelines (identity resolution services that match CRM email addresses to ad network identifiers), and retail media data providers. The user profile lookup in the bid pipeline evolves from "look up cookie in our tracker database" to "look up hashed email match or probabilistic identity cluster in a federated data graph."

---

### What This Means for RTB Architecture in 2025-2026

```
COOKIE-BASED RTB (2015):                PRIVACY-FIRST RTB (2025+):
========================                ==========================

BID REQUEST includes:                   BID REQUEST includes:
  - User cookie ID → full               - Browser Topics (3-5 coarse topics)
    behavioral profile                  - Contextual signals (page URL, content)
                                        - First-party segments (if publisher
                                          has logged-in user + consent)
                                        - No cross-site identity

DSP PIPELINE:                           DSP PIPELINE:
  1. Look up cookie → 200 signals         1. Evaluate Topics API segments
  2. Match to 50 behavioral segments      2. Run contextual ML (URL → features)
  3. Run CTR model                        3. Run CTR model (coarser features)
  4. Bid based on individual targeting    4. Bid based on contextual + topic

RETARGETING:                            RETARGETING:
  Cookie tracks user across web           Protected Audience: browser runs
  DSP recognizes and bids high            in-browser auction, DSP never
  (user recently visited site)            sees user identity

ATTRIBUTION:                            ATTRIBUTION:
  Click → install: direct match          SKAdNetwork: aggregated, delayed
  User-level reporting                   Campaign-level only, coarse values

REVENUE IMPACT: (baseline)              REVENUE IMPACT: -30% to -50%
                                        (industry estimates for post-cookie)
```

The transition is not just technical — it is economic. Industry analysts estimate that cookie deprecation will reduce programmatic ad revenue by 30-50% for publishers who rely on behavioral targeting, because contextual targeting without user identity is significantly less effective at matching high-value advertisers to high-intent users. Publishers with strong login relationships (The New York Times has 10M+ subscribers; The Wall Street Journal has millions of authenticated users) are more insulated. Anonymous-traffic-heavy publishers face the steepest revenue declines.

---

### Intern to Staff Progression: Privacy and Ad Tech

**Intern:** Knows that cookies track users and that Apple blocked IDFA in iOS 14.5. Knows "privacy" is a concern in ad tech.

**Junior (L3):** Understands the distinction between first-party and third-party cookies. Knows that GDPR requires consent for behavioral tracking in Europe and can explain what a consent string is. Has heard of Privacy Sandbox.

**Mid-level (L4):** Can explain how Topics API works at a technical level (browser-computed, locally stored, 3-week window, fake topic injection). Understands SKAdNetwork's postback mechanism and why 6-bit conversion values limit optimization. Knows what clean rooms are and why they're needed.

**Senior (L5):** Can reason about the performance impact of losing behavioral targeting — which signals are lost, which can be approximated contextually, and which require first-party data partnerships. Can design a DSP's migration plan from cookie-based to privacy-first architecture, including identity resolution, contextual ML model development, and Protected Audience API integration.

**Staff (L6):** Understands the full strategic picture: why Google's Privacy Sandbox simultaneously protects user privacy AND entrenches Google's advantage (because Google has first-party data from Search and YouTube that no third party can match, making cookie deprecation less painful for Google than for independent DSPs). Can reason about the regulatory capture angle — Privacy Sandbox was reviewed by the UK Competition and Markets Authority (CMA) as part of settling a competition complaint. Knows that the "death of cookies" is not a single event but a multi-year transition with different timelines on different browsers and operating systems. Can design an ad system that degrades gracefully as more browsers deprecate cookies, with clear metrics for measuring the revenue impact of each privacy change.

### Brainstorming Q&A

**Q: Google claims Privacy Sandbox protects user privacy while maintaining ad effectiveness. Critics say it primarily entrenches Google's monopoly. Who is right?**

Both are partially correct, and the real answer is that the two goals are not mutually exclusive — which is why Privacy Sandbox is so politically contentious. On the privacy side, Privacy Sandbox genuinely does reduce the surveillance footprint of third-party cookies. Topics API prevents ad networks from building granular cross-site browsing histories. Protected Audience API prevents advertisers from knowing which specific user they're retargeting. These are real privacy improvements compared to the cookie ecosystem. The UK's ICO (Information Commissioner's Office) has reviewed Privacy Sandbox and concluded it does provide meaningful privacy protections.

On the monopoly side, the critics are also correct. Google has first-party data — from Search, Gmail, YouTube, Chrome browsing history (opt-in), Android — that is unaffected by cookie deprecation. An independent DSP that currently relies on third-party cookies to build behavioral profiles will lose most of its targeting signal when cookies die. Google's own advertising products (Google Ads, DV360) retain their advantage through first-party Google data. The Topics API, while privacy-preserving, routes user interest signals through Google's browser, giving Google infrastructure-level visibility that competitors cannot replicate. The CMA required Google to commit to maintaining non-discriminatory API access as a condition of allowing Privacy Sandbox to proceed — suggesting even regulators agreed the monopoly concern was real. The fairest summary: Privacy Sandbox improves privacy AND advantages Google simultaneously. These outcomes are correlated, not coincidental.

**Q: If behavioral targeting disappears, does contextual targeting actually work well enough to sustain the ad-funded internet?**

Contextual targeting — showing ads based on the content of the current page rather than the user's history — is not new. It was the dominant form of digital advertising before behavioral targeting took over in the early 2010s. The question is whether it can scale back to being the primary signal and at what revenue cost. The evidence is mixed. A 2019 academic study found that behavioral targeting increased publisher revenue by approximately 4% (not the 100x+ claimed by the industry) — suggesting contextual advertising alone would be close to as effective. However, more recent studies in GDPR-affected regions found larger revenue impacts — 25-40% declines when users declined cookie consent.

The technology for contextual targeting has improved dramatically since 2010. Modern contextual systems use large language models to understand page content semantically, not just via keyword matching. A page about "Boston Marathon training" can be classified as high-intent running content even without any of the words "running shoes" appearing. Category-level contextual signals combined with time-of-day, device type, and geographic data can create surprisingly effective targeting. Companies like Seedtag, GumGum, and Integral Ad Science have built contextual-only targeting businesses that have grown specifically as cookies deprecate. The honest answer: contextual targeting alone probably sustains 60-75% of current programmatic revenue for most publishers — sufficient to keep the ad-funded internet viable, but insufficient to support the current inflated valuations of behavioral targeting companies.

---

## Part 14: Ad Serving at Scale — Operations

### Handling 10 Million QPS with a 50ms SLA

Ten million queries per second is not a thought experiment — it is approximately what Google's ad exchange processes. At this scale, engineering decisions that would be irrelevant at smaller volumes become load-bearing constraints.

**Capacity planning:** At 10M QPS, even a 1-microsecond (0.001ms) per-request overhead adds 10,000 CPU-seconds per second of load — equivalent to running 10,000 CPUs continuously just to handle that one overhead. This is why ad servers are written in C++ or Go (not Python), use zero-copy network I/O, avoid garbage collection pauses (Go's GC is tuned for low-latency; Python's is disqualifying), and use custom memory allocators that avoid lock contention.

**Horizontal scaling:** The bid server fleet is horizontally scaled: 500-1,000 machines, each handling 10,000-20,000 QPS. The exchange distributes bid requests using consistent hashing (so the same user's requests tend to go to the same bid server, improving local cache hit rates for user profiles). When a server goes down, consistent hashing redistributes its load to neighbors with minimal rehashing. Adding capacity is as simple as adding servers to the fleet and updating the hash ring.

**Stateless bid servers:** Individual bid servers are stateless with respect to user data. All persistent state (user profiles, campaign catalog, frequency counters) lives in external systems (Bigtable, Redis Cluster, Aerospike). This makes horizontal scaling trivial — any server can handle any bid request. The tradeoff is that every bid request incurs a network round-trip to fetch state, which is why those external systems must be co-located and extremely fast.

**Sharding strategy for user profiles:**
```
USER PROFILE SHARDING (10M QPS, 500M users):

Shard key: user_id % 1000 → 1000 Bigtable shards
Each shard: ~500K users

Per-shard read load:
  10M QPS / 1000 shards = 10,000 reads/second per shard
  Bigtable shard capacity: ~100,000 reads/second
  Headroom: 10x (good for traffic spikes)

In-memory cache layer (Redis):
  Cache hit rate target: 90%+
  Cache miss rate: 10% → 1M Bigtable reads/second
  (acceptable for Bigtable cluster of 500 nodes)
```

---

### Graceful Degradation: The Art of Failing Politely

Ad systems must remain functional under partial failures. The two most important failure scenarios are user profile lookup timeouts and ML model serving failures.

**User profile timeout degradation:**

```
DEGRADATION TIERS:

TIER 1 (Normal): Full behavioral profile from Bigtable
  → Use all 50 user segments, run full CTR model
  → Expected bid quality: HIGH

TIER 2 (Cache miss): Profile not in Redis, Bigtable too slow
  → Fall back to demographic proxy:
     use geo (NYC, age 25-34 inferred from device/app)
  → Expected bid quality: MEDIUM (20-30% worse CTR accuracy)

TIER 3 (Total profile failure): Bigtable cluster unreachable
  → Contextual-only targeting (page content + ad relevance)
  → No user segments, no frequency check (risk overcap slightly)
  → Expected bid quality: LOW (50% worse, but still positive ROI)

TIER 4 (Complete failure): Cannot produce any reasonable bid
  → Send no-bid immediately
  → Log for investigation
  → Alert if no-bid rate exceeds 5% threshold
```

The critical requirement is that Tier 2 and Tier 3 bids still clear the floor price. A no-bid (Tier 4) is preferable to a bid that wins the auction with a broken creative or wrong targeting. "When in doubt, don't bid" is the safety principle.

**ML model serving failure:**

If the CTR model serving endpoint returns errors or times out, the system falls back to a rule-based fallback: use the campaign's historical average CTR for the ad category as the predicted CTR. This is much less accurate but computable in microseconds. The bid price degrades in quality but remains valid.

---

### Budget Exhaustion: When the Advertiser Runs Out of Money

Campaign budgets exhaust at unpredictable times. A campaign might have a $10,000 daily budget but a breaking news event that's relevant to their product could drive 100x normal traffic to targeted pages, exhausting the budget by 10am instead of 5pm.

When a campaign's budget counter hits zero, the bid system must:
1. **Stop bidding immediately** for that campaign — no new bids go out for any impression
2. **Honor already-submitted bids** — if the DSP submitted a bid 1ms ago and wins, that impression must be served (reneging on a submitted bid damages exchange relationships and can result in being blacklisted)
3. **Avoid the overspend race condition** — at 10M QPS, between the moment the budget counter reaches zero and the moment all bid servers learn of this, some additional bids will be submitted. This is accepted overspend. The budget enforcement SLA is typically: "do not overspend by more than 10% of daily budget." A well-designed system keeps overspend to 1-2%.

**The budget counter propagation problem:**

Budget is tracked via distributed counters across the DSP's bid server fleet. When Campaign X's budget reaches zero on Server A (which has processed the most of Campaign X's impressions), Servers B through Z still think the campaign has budget remaining. Propagating the "budget exhausted" signal takes 100-500ms (the inter-server update interval).

During this window, all other servers continue bidding. If Campaign X was spending $100/second at peak, and the signal propagation takes 300ms, the system will overspend by $30. For a $10,000 daily budget, this is 0.3% overspend — well within the SLA.

The fix for larger overspend risks (high-CPM campaigns with small budgets): maintain a "budget sentinel" — a single authoritative budget counter that all bid servers must consult before submitting any bid. This eliminates the propagation window but adds ~2ms of latency per bid (network round-trip to the sentinel). Most systems use the sentinel approach only for campaigns with remaining budget < $100 (approaching exhaustion), switching from distributed counters to sentinel mode as the budget runs low.

---

### Real Incident: The $1000 Bidder That Won Everything

**The Bug:** In 2019, a mid-sized DSP had a bidding bug that set the bid price for a misconfigured campaign to the campaign's CPM max bid in dollars instead of in CPM units. The campaign was configured with max_bid = $1000 as a failsafe cap. Due to a unit conversion error in the bid price calculation code, the system submitted bids of $1000 CPM — one thousand dollars per thousand impressions, or $1 per impression — for every eligible auction.

This was approximately 500-1000x the normal clearing price for most ad slots.

**What happened:** The misconfigured campaign won every auction it entered. At 50ms per auction across thousands of concurrent auctions, within 60 seconds the campaign had won tens of thousands of impressions. At $1.00/impression (not CPM), this was burning through budget at approximately $10,000/minute. A campaign with a $50,000 total budget was fully exhausted in 5 minutes.

But it got worse: the exchange's billing system was in second-price mode for this campaign's segment. The winner pays the second-highest bid. The competing bids were typically $3-$8 CPM (not $1000). So the clearing price was $3-$8 CPM, not $1000 CPM. The DSP actually paid $3-$8 CPM per impression despite submitting $1000 CPM bids. This meant the campaign overspent the advertiser's budget much more slowly than if they'd actually paid $1000 CPM — but it also meant the campaign monopolized every auction it entered, crowding out other advertisers and inflating clearing prices for everyone else.

**Detection:** The DSP's monitoring caught the anomaly 3 minutes after the campaign went live. A dashboard metric "max_bid_submitted_last_minute" spiked to $1000 CPM, which triggered a critical alert. The on-call engineer paused the campaign within 90 seconds of the alert firing.

**Root cause:** A configuration API accepted `max_bid` as a floating-point number. The internal bid calculation function expected this value in CPM (cost per mille = per thousand). A code change one week earlier had modified the API to accept bids in CPC (cost per click) format and converted them to CPM by multiplying by 1000. But the configuration for this campaign was loaded before the code change and used the old format. The new code treated the old CPM value as a CPC value and multiplied by 1000, resulting in $1000 CPM.

**Fix:** 
1. Added a hard-coded sanity check: `assert bid_price_cpm < 500`, rejecting any bid above $500 CPM (the highest ever observed legitimate bid in the system's history)
2. Added unit annotation to all bid price variables (`bid_price_cpm`, `bid_price_cpc`) — never plain `bid_price`
3. Added a config migration that re-read all campaign configurations through the new API format
4. Added a monitoring alert: "if any campaign's average CPM exceeds 3x its historical p99, page on-call immediately"

**Lesson:** Financial systems need sanity bounds on every computed value. An assertion that your bid is within a plausible range is not defensive programming — it is mandatory safety for systems that move real money.

---

### On-Call for an Ad System: What Alerts Matter

Running on-call for an ad system is different from most distributed systems. The latency requirements are extreme, the financial impact of bugs is immediate, and the adversarial environment (fraudsters actively probing for exploits) means novel failures appear regularly.

**Tier 1 Alerts — Page Immediately (Wake Up at 3am):**

1. **Bid server p99 latency > 45ms** — The system is close to timing out on the exchange. If p99 exceeds 50ms, bids will time out and the exchange will reduce traffic to this DSP. Revenue impact: immediate and severe.

2. **No-bid rate > 10%** — More than 10% of bid requests are resulting in no-bids. Could indicate user profile lookup failures, ML model serving failures, or budget exhaustion across all major campaigns.

3. **Campaign overspend > 15%** — A budget enforcement failure. Overspending by >15% on a large campaign can mean millions of dollars of credits owed to advertisers.

4. **Max CPM submitted > $500** — The $1000 bidder incident detection. Any bid above historical ceiling triggers immediate investigation.

5. **Win rate drop > 50% in 10 minutes** — Sudden collapse in auction wins suggests the exchange has throttled this DSP's traffic (due to timeout violations or quality issues) or the bid shading model has malfunctioned.

6. **Creative serving error rate > 1%** — Users are seeing blank ads or error placeholders. Publishers will blacklist the DSP if creative errors persist.

**Tier 2 Alerts — Respond Within 30 Minutes:**

1. **CTR model staleness > 6 hours** — The ML model hasn't been retrained on recent data. Performance degrades gradually.

2. **Frequency cap violation rate > 2%** — More users are seeing ads beyond their cap than expected.

3. **Click fraud signal spike** — Automated fraud detection systems reporting higher than normal invalid click rates.

4. **Exchange integration errors > 0.5%** — Malformed bid request parsing failures, indicating the exchange changed their API format.

**Runbook for "Bid server p99 latency > 45ms":**

```
STEP 1: Check which component is slow
  → Look at per-component latency dashboards:
    - user_profile_lookup_p99
    - ml_inference_p99
    - bid_calculation_p99

STEP 2: If user_profile_lookup_p99 > 20ms:
  → Check Bigtable/Redis cluster health
  → If Bigtable node down: traffic reroutes automatically (check)
  → If Redis memory pressure: restart lowest-memory-usage replica
  → Emergency: enable "anonymous mode" flag (skip profile lookup)

STEP 3: If ml_inference_p99 > 15ms:
  → Check model serving cluster health
  → If ML cluster degraded: switch to fast fallback model (flag)
  → Emergency: disable ML, use rule-based bid calculation

STEP 4: If no component is individually slow:
  → GC pressure (Go garbage collection pauses?)
  → Check bid server CPU utilization: if >80%, add servers
  → Check network latency to exchange co-location: routing issue?

STEP 5: If p99 > 48ms:
  → Activate "conservative mode": reduce bid computation to minimum
  → Alert team lead, prepare for exchange traffic reduction
```

---

### Intern to Staff Progression: Ad Operations

**Intern:** Knows that ad systems need to be "fast" and "reliable." Can describe the 50ms constraint. Knows what on-call means.

**Junior (L3):** Understands horizontal scaling and stateless bid servers. Can explain why user profiles live in Redis rather than in bid server memory. Can read a latency histogram and identify p99 vs. p50 differences.

**Mid-level (L4):** Can design the degradation tier system for profile lookup failures. Understands the budget exhaustion race condition and the sentinel approach. Can write runbooks for common failure modes. Knows what circuit breakers are and how to configure them for exchange connections.

**Senior (L5):** Can design the full monitoring system — which metrics matter, what thresholds are appropriate, what the alert response runbook should look like. Can do a blameless post-mortem on the $1000 bidder incident and identify all the systematic fixes needed. Can reason about the financial risk model: how much overspend is acceptable, what's the cost of a creative serving error in publisher relationships, how do you calculate the revenue impact of a 10ms latency regression.

**Staff (L6):** Can design the full operational architecture for a 10M QPS ad system — capacity planning, failure domain isolation (so a Bigtable regional failure doesn't cascade into global bid server failures), chaos engineering strategy, and financial reconciliation processes. Understands that operations at this scale require designing for *self-healing*: the system should detect most failure modes and automatically switch to degraded-but-functional states without human intervention. Manual intervention at 10M QPS takes too long. Only human-on-the-loop decisions (like "should we shut down this entire exchange integration?") require waking the on-call engineer.

### Brainstorming Q&A

**Q: At 10M QPS, even reading a configuration flag from a shared database takes too long. How do configuration changes propagate to bid servers in real time?**

This is the "config push" problem and it is much harder than it looks. At 10M QPS, you have 1,000 bid servers each handling 10,000 requests per second. If each server queries a central configuration service for updates every second, that's 1,000 config queries per second on the config service — trivial. The problem is latency: if a bug is found in a campaign configuration (like the $1000 bidder scenario), you need to push the "pause campaign X" signal to all 1,000 servers within seconds, not minutes. The naive approach — each server polls the config service every 60 seconds — creates a 60-second propagation window during which the buggy campaign continues burning money.

The solution used by Google's ad infrastructure (and documented in papers about their "Zanzibar" and configuration management systems) is push-based fan-out with local caching. A centralized configuration service maintains the authoritative state. When a change is made (campaign paused, budget updated, targeting rule changed), the config service pushes the diff to all bid servers via a persistent connection (gRPC streaming or a custom push protocol). Each bid server applies the diff to its local in-memory cache. Propagation time is typically 100-500ms to reach all servers globally. For emergency pauses (like the $1000 bidder), a "emergency pause" API path bypasses the normal diff system and sends a UDP broadcast to all servers in the same data center, achieving sub-100ms propagation for the highest-priority signals. The trade-off: UDP broadcast is lossy — some servers might not receive the broadcast. The system follows up with a reliable confirmation check, and any server that didn't receive the broadcast picks it up via the normal polling path within 5 seconds.

**Q: The $1000 bidder incident was caught in 3 minutes. What would have happened if monitoring was absent and the bug ran for 24 hours?**

If the bug had run for 24 hours without detection, the consequences would have been multi-dimensional. The direct financial impact: the campaign would have exhausted its budget ($50,000) and stopped bidding on its own due to budget exhaustion. But the DSP's contract with the advertiser likely guaranteed spend pacing — the campaign should have run over 30 days, not one day. The advertiser paid for 30 days of reach and received 1 day of massively compressed reach. The DSP would owe significant credits or a refund, and the advertiser relationship would likely be permanently damaged.

The market impact: a 24-hour $1000 CPM bidder would have systematically crowded out other advertisers in the affected ad categories. The clearing price for everyone else's auctions would have spiked — because second-price mechanics mean other advertisers pay just above the second-highest bid, and the second-highest bid would now be other legitimate advertisers' bids (since the rogue bidder always wins at $1000). This could trigger complaints from other DSPs and advertisers to the exchange, who would investigate the anomalous price spikes and identify the source. The DSP would face potential suspension from the exchange for submitting invalid bids that distorted market pricing — a much worse outcome than catching it in 3 minutes. At scale, the rule is: monitor everything, alert aggressively, investigate fast. The cost of a false positive page is one interrupted dinner. The cost of a missed alert is potentially millions of dollars and permanent relationship damage.

---

---

## Part 15: Ad Tech System Design — Quick Reference

### The 5-Minute Sketch for Any Ad Serving Interview

When you get 5 minutes to whiteboard the entire ad serving system, draw this:

```
FIVE-BOX ARCHITECTURE (draw in this order)

+------------------+      OpenRTB       +------------------+
|   PUBLISHER      |  Bid Request  -->  |   AD EXCHANGE    |
|   (SSP)          |                    |                  |
|                  |  <-- Win Notif     |  - Runs auction  |
|   - Ad tag on    |                    |  - 2nd price     |
|     page         |                    |  - Fraud filter  |
|   - Floor price  |                    |  - 10M QPS       |
+------------------+                    +--------+---------+
                                                 |
                                    Bid requests fanout to all DSPs
                                                 |
                    +----------------------------+------------------+
                    |                            |                  |
          +---------v-------+         +----------v------+  ... x200 DSPs
          |    DSP (THE     |         |    DSP (Acme    |
          |    TRADE DESK)  |         |    Demand)      |
          |                 |         |                 |
          | Bid pipeline:   |         | Same pipeline   |
          | 1. Parse (2ms)  |         | on their        |
          | 2. UserLookup   |         | infrastructure  |
          |    (10ms)       |         |                 |
          | 3. CandSelect   |         +-----------------+
          |    (5ms)        |
          | 4. ML CTR(10ms) |
          | 5. BidCalc(3ms) |
          | 6. Encode (2ms) |
          |    TOTAL: 32ms  |
          +-----------------+
                    |
          +---------v------------------+
          |   ADVERTISER DATA STORES   |
          |                            |
          | - User Profiles (Bigtable) |
          | - Campaign Catalog (RAM)   |
          | - Freq Counters (CMS)      |
          | - Budget Counters (Redis)  |
          | - ML Models (Served)       |
          +----------------------------+
```

Then narrate: "The publisher's SSP runs an auction per impression. It fans out a bid request to 200+ DSPs simultaneously via OpenRTB. Each DSP has 50ms. The DSP pipeline is: receive/parse, user profile lookup, candidate ad selection, ML CTR scoring, bid calculation, response encoding. The winning DSP is notified and charged second price (or first price in modern exchanges). The critical constraints are: 50ms hard deadline, 10M QPS at exchange scale, financial correctness for budgets, user privacy compliance."

That 3-minute sketch plus narration earns you the "understands the system" baseline. Everything after that is demonstrating depth.

---

### Decision Tree: Which Data Store for Which Ad Tech Problem?

```
WHAT ARE YOU STORING?
        |
        +---> USER BEHAVIORAL PROFILES
        |     (500M users, 200 features each)
        |     → Bigtable (wide-column, low-latency reads)
        |       or Aerospike (purpose-built for ad tech)
        |       NOT: Postgres (too slow), DynamoDB (too expensive at scale)
        |
        +---> FREQUENCY COUNTERS
        |     (100B combinations of user × campaign)
        |     → Count-Min Sketch in Redis
        |       NOT: exact counters (too much memory)
        |       NOT: Bigtable (too slow for per-impression writes)
        |
        +---> BUDGET COUNTERS
        |     (10K campaigns, strong consistency needed)
        |     → Redis with Lua atomic scripts
        |       or Spanner (if cross-region consistency needed)
        |       NOT: approximate (financial system needs correctness)
        |
        +---> CAMPAIGN CATALOG
        |     (50K active line items, read 10M times/sec)
        |     → In-memory on bid server (loaded from Kafka)
        |       NOT: any network call (too slow at bid time)
        |
        +---> ML FEATURE STORE
        |     (computed features for training and serving)
        |     → Redis (online features, low-latency serving)
        |       + BigQuery/Hive (offline features, training data)
        |
        +---> AUCTION LOG / IMPRESSION LOG
        |     (10M events/second, append-only)
        |     → Kafka → BigQuery / Hive
        |       NOT: any transactional database
        |
        +---> CLICK / CONVERSION EVENTS
              (sparse, need joins with impression logs)
              → Kafka → Flink (for real-time attribution)
              → BigQuery (for offline attribution + reporting)
```

---

### The Staff-Level Questions You Must Be Able to Answer

These are the questions that separate L5 from L6 in an ad serving interview. Know all of them cold.

**1. How do you frequency cap 500M users across 100K campaigns without a database that can store 50 trillion counters?**
Count-Min Sketch. Use d=7 hash functions, w=100K buckets per sketch, one sketch per time window (daily, weekly). Memory: 7 × 100K × 4 bytes = 2.8MB per window. Can store all users and campaigns. Overcount by at most 1/100K of total increments. Acceptable false positive direction (serves as safety cap, never under-caps).

**2. How do you ensure a $10K daily budget never becomes a $50K daily spend in a distributed system?**
Distributed budget shards + sentinel for low-budget campaigns. Each bid server holds a shard of the total budget (e.g., 50 servers × $200 shard = $10K). When a shard is exhausted, the server stops bidding and requests a new shard. Maximum overspend = shard_size × (number of servers) = bounded by design. For campaigns with < $200 remaining, switch to a single authoritative Redis counter with atomic decrement.

**3. Why is the CTR model a gradient-boosted tree and not a neural network?**
Inference latency. XGBoost on a CPU takes 0.5-2ms for a model with 1,000 trees. A shallow neural network takes 3-10ms. A transformer-based model takes >50ms. At bid time, you have ~10ms for ML inference total (across potentially 50 candidate ads). GBT is fast enough. Neural networks are used for offline training signals (embedding generation, user representation learning) whose outputs become features fed into the fast GBT model at serving time. This two-stage architecture — slow neural network offline, fast GBT online — is standard in production ad systems at Google, Meta, and Amazon.

**4. What is training-serving skew and why is it uniquely dangerous in ad ML?**
Training-serving skew occurs when features available during training are computed differently than during serving. In ad ML, this is especially dangerous because: (a) delayed labels — a click might be attributed to an impression hours later, so the training label isn't available until long after the serving event; (b) feature drift — a user profile feature computed in batch (yesterday's browsing history) might be stale relative to real-time events at serving; (c) feedback loops — if the model serves an ad and the ad gets clicks, the click signal reinforces that model's behavior, creating a self-reinforcing bias toward already-shown ads. The remedy: feature logging at serving time (log exactly the features used for each bid, not recomputed features), time-consistent labels (define attribution windows explicitly and wait for them to close before training), and exploration (deliberately serve some random ads to break feedback loops).

**5. If you're the exchange and you want to switch from second-price to first-price auctions, what engineering work is required?**
The switch requires: (1) updating the auction settlement logic — instead of charging second price, charge the winning bid directly; (2) updating all win notification macros — the `${AUCTION_PRICE}` macro must now return the winning bid, not the clearing price (these were different in second-price); (3) notifying all DSPs so they can activate bid shading algorithms — bidding true value in a first-price auction systematically overpays; (4) updating reporting and billing reconciliation — the revenue split between publisher and exchange changes because clearing prices change; (5) A/B testing — run first-price on 1% of traffic, measure publisher revenue (should increase) and DSP ROI (should improve over time as bid shading algorithms tune), ramp carefully. The industry transition from 2017-2019 was rocky because some DSPs were slow to implement bid shading and significantly overpaid during the transition period.

---

### The Ad Tech Interview in 45 Minutes: Time Allocation

```
RECOMMENDED 45-MINUTE INTERVIEW ALLOCATION:

Minutes 0-5:   CLARIFY AND SCOPE
  - "Which part of the stack? Full system, DSP, SSP, or exchange?"
  - "What scale? Google-level 10M QPS or startup-level 100K QPS?"
  - "What's the primary design challenge? Latency? Fraud? Privacy?"
  - State your assumptions explicitly: "I'll design the DSP bid pipeline
    at 1M QPS, focusing on the 50ms latency constraint."

Minutes 5-15:  HIGH-LEVEL DESIGN
  - Draw the 5-box diagram (Publisher→SSP→Exchange→DSP→Advertiser)
  - Add the DSP internal components: bid server, user profile store,
    campaign catalog, ML scoring engine, budget controller
  - Name the critical path: the 50ms clock

Minutes 15-30: DEEP DIVE ON HARDEST COMPONENT
  - Pick one: user profile lookup latency, frequency capping at scale,
    or budget pacing under distributed conditions
  - Go deep: specific data structures, why Bigtable not Postgres,
    Count-Min Sketch math, shard-based budget enforcement
  - Anticipate and answer: "What if that's slow?" (fallback tiers)

Minutes 30-40: ML AND RANKING
  - CTR model: GBT not neural net, features, training-serving skew
  - Bid calculation: value formula, bid shading in first-price
  - Quality score if exchange context

Minutes 40-45: OPERATIONAL AND EDGE CASES
  - Budget exhaustion: sentinel handoff
  - Graceful degradation tiers
  - One incident example showing operational maturity
  - Privacy mention: GDPR consent string in bid request,
    post-cookie trajectory
```

---

## Part 16: Vocabulary Reference and Cross-Chapter Connections

### Vocabulary Every Ad Tech Engineer Needs Cold

| Term | Definition | Why It Matters in Interviews |
|------|-----------|------------------------------|
| **CPM** | Cost Per Mille — price per 1,000 impressions | The standard unit of programmatic pricing |
| **CPC** | Cost Per Click — advertiser pays only when user clicks | Used in search advertising; converted to CPM via pCTR |
| **CPA** | Cost Per Acquisition/Action — pays per conversion | Goal metric for performance advertisers |
| **pCTR** | Predicted Click-Through Rate | The key ML model output that drives bid calculation |
| **ROAS** | Return On Ad Spend — revenue / ad spend | Advertiser's primary success metric |
| **Fill Rate** | % of ad slots that successfully serve an ad | Publisher health metric; low fill = lost revenue |
| **Win Rate** | % of auctions where DSP wins | DSP efficiency metric |
| **Clearing Price** | Actual price paid in an auction | Second price in VCG; winning bid in first-price |
| **Floor Price** | Minimum acceptable bid set by publisher | Below floor = no bid counts; protects publisher CPM |
| **Header Bidding** | Running multiple SSP auctions simultaneously in browser | Replaced waterfall; higher publisher revenue |
| **Waterfall** | Sequential SSP priority list (try A, then B, then C) | Old model; lower fill rates and revenue |
| **Ad Tag** | JavaScript snippet on publisher page triggering auction | The starting point of every RTB auction |
| **Creative** | The actual ad content (image, HTML5, video) | Must be pre-validated; fetched from CDN at serve time |
| **Line Item** | A specific ad configuration within a campaign | One campaign may have 100 line items targeting different segments |
| **IVT** | Invalid Traffic — fraudulent impressions and clicks | Measured by MRC-accredited vendors (IAS, MOAT, DoubleVerify) |
| **Viewability** | Was the ad actually in-viewport for 1 second? | IAB standard: 50% of pixels visible for 1 second |
| **Cookie Sync** | Matching user IDs across different ad platforms | Required because each DSP/SSP has different user ID spaces |
| **DMP** | Data Management Platform | Aggregates third-party audience data for targeting |
| **Deal ID** | Identifier for a programmatic guaranteed or private marketplace deal | Direct deals outside open auction |
| **PMP** | Private Marketplace | Invitation-only auctions with fewer, preferred buyers |
| **Open Auction** | Open RTB auction available to all bidders | Lower CPMs but high scale |
| **Programmatic Guaranteed** | Pre-negotiated volume at fixed price, automated delivery | Combines guaranteed delivery with programmatic targeting |

---

### Cross-Chapter Connections

**Chapter 89 (Ad Serving) ↔ Chapter 83 (Chubby/Distributed Lock Service)**
Budget enforcement in ad systems requires distributed coordination. When switching from distributed budget shards to a sentinel counter, the sentinel election uses leader election — exactly the problem Chubby solves. The "budget sentinel" is a leader-elected process that holds exclusive authority over the budget counter for a campaign approaching exhaustion. Chubby's lease-based locking maps directly to this pattern.

**Chapter 89 (Ad Serving) ↔ Chapter 48 (Consensus Deep Dive)**
Budget pacing across distributed bid servers is a consensus problem in disguise. You need all bid servers to agree on "this campaign is exhausted" without a global coordinator (which would be too slow). The solution — distributed counters with eventual convergence plus a sentinel for the final dollars — parallels Raft's approach to distributed state machine replication. The shard → sentinel handoff is a leader change triggered by a threshold event.

**Chapter 89 (Ad Serving) ↔ Chapter 85 (Borg/Kubernetes)**
Ad bid servers are stateless containers that need millisecond-level autoscaling during traffic spikes. Borg/Kubernetes bin-packing, pod scheduling, and resource quota management are the operational substrate on which the ad serving fleet runs. The latency sensitivity of ad servers (50ms SLA) makes them poor candidates for preemptable/spot instances — they need guaranteed CPU without noisy neighbor interference.

**Chapter 89 (Ad Serving) ↔ Chapter 86 (Video Streaming)**
Video advertising (pre-roll, mid-roll ads in video streams) combines both systems. The video player runs an RTB auction (VAST/VPAID protocol) before each ad break. The auction's winning creative must be a video file delivered at the right bitrate for the current network connection — exactly the adaptive bitrate (ABR) problem from video streaming. The systems share CDN architecture for creative delivery.

**Chapter 89 (Ad Serving) ↔ Chapter 47 (Kubernetes Internals)**
Creative validation (scanning uploaded ad creatives for malware, policy violations) is a batch job pipeline. Kubernetes job controllers, resource limits, and namespace isolation are exactly the substrate used to run creative validation workers safely. A malicious creative that triggers a memory overflow in the validator should not crash the entire validation cluster — namespace isolation prevents this.

---

### The Hierarchy of Ad Serving Difficulty

Different interview questions about ad serving have very different difficulty ceilings. Here is an honest calibration:

**Easy (L3-L4 expected to answer fully):**
- Explain the difference between DSP, SSP, and Ad Exchange
- What is a second-price auction and why is it theoretically attractive?
- Why can't you store user profiles in a relational database for bid-time lookup?
- What is CPM and how does it relate to CPC and pCTR?

**Medium (L4-L5 expected to answer fully):**
- How do you implement frequency capping at 10B users × 1M campaigns scale?
- Why did the industry switch from second-price to first-price auctions?
- How do you handle budget exhaustion in a distributed bidding system without a global lock?
- What is training-serving skew and how do you detect it?

**Hard (L5 expected to partially address; L6 expected to address fully):**
- Design a bid shading algorithm for a first-price auction. What data does it need? How do you train it? How do you evaluate it?
- How do you build a frequency capping system that works across devices (desktop, mobile, CTV) for the same user without a persistent cross-device ID?
- Design a budget pacing controller that smoothly delivers spend across a day despite traffic volume being 40% higher than forecast due to breaking news.
- How would you redesign a DSP's targeting architecture to work without third-party cookies? What signals remain, what must be rebuilt, and what performance degradation is acceptable?

**Staff-defining (L6 signal):**
- The entire ecosystem is a game-theoretic system. Every player (publishers, advertisers, exchanges, DSPs, fraudsters) is optimizing for themselves, often at the expense of others. Given this, how would you design an exchange whose rules are manipulation-resistant? What game-theoretic properties would you want and what mechanism design principles would you apply?

---

## Part 17: Numbers Every Ad Tech Engineer Should Know

Having these numbers memorized lets you sanity-check designs on the fly and answer "back of the envelope" questions instantly. At an L6 interview, a candidate who says "about 50ms, around 10M QPS, roughly $68B in fraud annually" signals they've done real thinking about this domain. A candidate who says "I'd need to look that up" signals they haven't.

```
MARKET NUMBERS (2023-2024):
  Global digital ad market:    ~$600B/year
  Google ad revenue:           ~$224B/year (77% of total Google revenue)
  Meta ad revenue:             ~$120B/year
  Amazon ad revenue:           ~$47B/year
  Annual IVT (ad fraud):       ~$68-100B/year
  % of digital ads that are   
    never seen by humans:      ~36% (Source: WFA)
  Average CPM (open web):      $2-8 CPM
  Average CPM (premium video): $25-50 CPM
  Average CPM (retail media):  $10-30 CPM

LATENCY NUMBERS:
  Total RTB auction budget:    50ms (hard deadline)
  Network: browser to SSP:     2-5ms
  DSP user profile lookup:     3-10ms (Redis/Bigtable)
  ML CTR inference (GBT):      0.5-2ms per 1,000-tree model
  Campaign filtering (bitmap): <1ms for 50K campaigns
  Protobuf encode/decode:       ~0.2ms per 5KB message
  p99 acceptable for bid svr:  45ms (5ms safety margin)

SCALE NUMBERS:
  Google exchange QPS:         ~10M QPS
  DSP user profiles:           500M - 2B unique users
  Active campaigns (large DSP): 50K - 500K line items
  Bid servers (large DSP fleet): 500 - 2,000 machines
  Bid requests per DSP per day: 1-5 trillion (at scale)
  Win rate (typical DSP):       0.5% - 5% of auctions entered
  Fill rate (healthy publisher): 80-95%

MEMORY NUMBERS (for Count-Min Sketch):
  CMS for 1B users × 10K campaigns:
    d=7 hash functions, w=1M buckets
    Memory: 7 × 1M × 4 bytes = 28MB per sketch
    Error bound: total_count / w = bounded overcount
  Alternative (exact Hash Map, naive):
    10^9 × 10^4 = 10^13 entries
    At 16 bytes per entry = 160TB — impossible

DATA PIPELINE NUMBERS:
  Impression logs per day:     10-100 trillion (at major exchange scale)
  Click rate on display ads:   ~0.1% (1 click per 1,000 impressions)
  Conversion rate (purchase):  ~1-3% of clicks
  Attribution window:          7-30 days post-click
  Model training frequency:    Every 1-24 hours (depending on traffic)
  Feature freshness target:    < 6 hours stale for user profiles

FRAUD NUMBERS:
  % of web display traffic     
    that is IVT:               ~15-25% (varies by channel)
  % of Connected TV (CTV) 
    traffic that is IVT:       ~20-40% (higher fraud rates)
  Methbot (2016 botnet):        $3-5M/day at peak, ~$1B total
  3ve (2018 botnet):            3 billion fake ad requests/day
  Cost to buy 1,000 bot clicks: $2-5 (market rate for click farms)
```

These numbers should appear in your designs naturally. When an interviewer asks "how many servers would the DSP need?" you can say: "At 1M QPS per server (a conservative estimate for a C++ bid server), for 10M QPS total we'd need about 10 servers at median load, but for p99 safety and redundancy, deploy 30-50 servers. A large DSP like The Trade Desk runs hundreds of servers for redundancy and multi-region capacity."

---

### Final Checklist: Before You Leave the Interview

Use this mental checklist in the last 2 minutes of an ad serving design interview. Run through it quickly and flag anything you skipped:

```
AD SERVING INTERVIEW FINAL CHECKLIST:

Architecture:
  [ ] Drew the DSP/SSP/Exchange triangle
  [ ] Named the OpenRTB protocol and bid request/response structure
  [ ] Identified the 50ms hard deadline explicitly

Latency:
  [ ] Specified that user profiles must be in-memory (not database)
  [ ] Said "co-location" — bid servers must be near exchange servers
  [ ] Described at least one graceful degradation tier

Scale:
  [ ] Mentioned 10M QPS (or appropriate scale for problem)
  [ ] Explained Count-Min Sketch for frequency capping
  [ ] Described distributed budget shards + sentinel

ML:
  [ ] Said GBT (not neural network) for bid-time CTR scoring
  [ ] Mentioned training-serving skew as a risk
  [ ] Described bid shading if first-price context

Operations:
  [ ] Named at least two meaningful on-call alerts
  [ ] Described at least one failure mode and its fallback
  [ ] Mentioned budget overspend risk and the financial correctness SLA

Privacy:
  [ ] Mentioned GDPR consent string in bid request
  [ ] Mentioned iOS 14.5 / SKAdNetwork impact on mobile
  [ ] Referenced cookie deprecation trend if time permitted

If you checked 15+/18: Strong L6 signal.
If you checked 10-14/18: Solid L5 performance.
If you checked <10/18: Significant gaps — review the missed sections.
```

---

*Chapter 89 complete. Next: Chapter 90 — Social Graph.*

---

## Interview Simulation — Ad Serving and Real-Time Bidding (Staff / L6)

*45-minute Staff-level system design interview. Phases follow the Section 2 framework.*

---

### Phase 1: Requirements (8 min)

> **Interviewer:** Design a real-time bidding system for display advertising. Where do you start?

**Candidate:** A few questions to scope this. First — are we building the Supply-Side Platform (SSP, the publisher side that runs auctions) or the Demand-Side Platform (DSP, the advertiser side that places bids)? The SSP orchestrates the auction; the DSP responds to bid requests. Second — what's our latency budget? Industry standard is 100 ms total from bid request to ad selection — is that our target? Third — do we need frequency capping, or is that a future concern? Fourth — are we handling first-price or second-price auction mechanics?

> **Interviewer:** Design the SSP — the auction orchestrator. Assume multiple external DSPs. 100 ms budget, second-price auction, frequency capping required, fraud detection in pre-bid.

**Candidate:** Functional requirements: (1) Receive bid request from a publisher page load. (2) Fan out bid request to N DSPs simultaneously, collect responses within 80 ms timeout. (3) Run second-price auction on valid bids. (4) Enforce frequency cap (max M impressions per user per day per advertiser). (5) Return winning ad creative to the publisher within 100 ms total. Non-functional: p99 latency < 100 ms end-to-end, 99.99% availability (revenue stops if we go down), 1 million auctions per second at peak.

> **Interviewer:** Good. Estimation?

---

### Phase 2: Estimation (4 min)

**Candidate:** 1 million auctions/second × 5 DSPs per auction = 5 million outbound bid requests per second. Each bid request is ~5 KB (user targeting segments, page context, ad slot spec) → 25 GB/s outbound to DSPs. Bid responses: average DSP response is ~1 KB, ~70% response rate → 3.5 million responses/s, 3.5 GB/s inbound. Frequency cap lookups: 1 million auctions/s, each requires reading and writing a counter in Redis → 2 million Redis ops/s (one read pre-auction, one write post-win). At 100K ops/s per Redis node, we need ~20 Redis nodes. Storage for frequency caps: 1 billion daily active users × 1,000 advertisers × 8 bytes per counter = 8 TB — too large for RAM. In practice, we cap at top-10,000 advertisers and use probabilistic counting (Count-Min Sketch) for long-tail advertisers, reducing to ~80 GB.

---

### Phase 3: API Design (4 min)

**Candidate:** The external-facing API follows OpenRTB 2.6 standard. `POST /v1/openrtb/auction` receives a BidRequest object (user ID, geo, device, page URL, impression specs, floor price). Returns a BidResponse (seat bids, price, ad markup, win notice URL). Internal APIs: `POST /internal/frequency-cap/check` body `{user_id, advertiser_id}` returns remaining_impressions. `POST /internal/frequency-cap/record` called after win. `POST /internal/fraud/evaluate` body `{bid_request}` returns a fraud_score and allow/block decision. The fraud eval API must return within 5 ms — it sits on the critical path before we fan out to DSPs.

> **Interviewer:** How do you handle the 80ms DSP timeout — what if one DSP is slow?

**Candidate:** Each DSP gets its own async HTTP call with an 80 ms hard timeout. We use hedged requests: if any DSP hasn't responded by 70 ms, we ignore it and proceed to auction with the responses we have. The auction service never waits for the slowest DSP. DSPs that miss the timeout consistently get a lower bid floor in future auctions (penalty mechanism to incentivize compliance). We track per-DSP p99 latency on a 5-minute rolling window.

---

### Phase 4: Data Model (4 min)

**Candidate:** Three key stores. Frequency cap counters: Redis with key `fc:{user_id}:{advertiser_id}:{date}`, value is integer count, TTL = 24 hours. We use INCR which is atomic. For probabilistic counting on long-tail advertisers, we store a Count-Min Sketch per advertiser in a single Redis key. Auction log: every auction result (regardless of win/loss) written to Kafka → Iceberg on S3 for billing reconciliation and ML training. Schema: auction_id, timestamp, user_id (hashed), winning_dsp_id, clearing_price, ad_creative_id, page_url_hash. Targeting segments: user-to-segment mapping in a key-value store (Aerospike) for sub-millisecond lookup. Key: user_id, value: serialized segment list (~100 bytes). Aerospike is preferred over Redis here because it stores data on SSDs, keeping RAM costs manageable at billion-user scale.

---

### Phase 5: HLD + Deep Dive (20 min)

**Candidate:** Here's the auction flow:

```
AUCTION FLOW (100ms budget)
============================

Publisher Page (iframe / tag)
  │  bid request arrives
  ▼
Load Balancer (L4, anycast)
  │
  ▼
Auction Gateway (0-5ms)
  │ parse OpenRTB, validate schema
  │ enrich with user segments (Aerospike, ~1ms)
  │
  ├─► Fraud Pre-bid Check (parallel, 5ms budget)
  │       IVT detection: datacenter IP, device fingerprint
  │       bot pattern matching (User-Agent, click pattern)
  │       → BLOCK (auction ends, no fill) or ALLOW
  │
  ▼
Fan-out to DSPs (0-80ms)
  ├─► DSP-1: POST /bid  ──► response or timeout
  ├─► DSP-2: POST /bid  ──► response or timeout
  ├─► DSP-3: POST /bid  ──► response or timeout
  └─► ... up to N DSPs, all in parallel
  │   wait max 80ms, collect all responses
  │
  ▼
Frequency Cap Filter (80-85ms)
  │ for each DSP bid response:
  │   check Redis fc:{user_id}:{advertiser_id}:{date}
  │   discard bids where cap is reached
  │
  ▼
Second-Price Auction (85-90ms)
  │ sort valid bids by CPM
  │ winner = highest bidder
  │ clearing price = second-highest bid + $0.01 floor
  │ log to Kafka (async, non-blocking)
  │
  ▼
Win Notice + Ad Delivery (90-100ms)
  │ return ad markup (HTML/JS creative) to publisher
  │ async: POST win notice to winning DSP
  │        INCR Redis frequency cap counter
  │        write to auction log Kafka
  └─► Publisher renders ad in iframe

BILLING RECONCILIATION
======================
Kafka → Flink (dedup, validate) → Iceberg (S3)
  → daily billing report per advertiser
  → DSP invoice reconciliation (compare our logs vs DSP logs)
```

**Deep Dive 1: Frequency Capping at Scale.**

The naive approach — one Redis key per user per advertiser per day — requires 2 million Redis ops/s. This works with a 20-node Redis cluster, but becomes expensive at billion-user scale with thousands of advertisers. The staff-level insight: most advertisers don't need exact frequency capping — ±5% error is acceptable. Count-Min Sketch reduces memory by 10–100× with bounded error. We allocate a CMS of width 10,000 and depth 5 per advertiser — that's 50,000 counters × 4 bytes = 200 KB per advertiser for 10,000 advertisers → 2 GB total, versus 8 TB for exact counters. The error guarantee: estimated count ≤ true count + ε×N with probability 1 - δ, where ε and δ are tunable. Premium advertisers (top 100 by spend) get exact Redis counters; everyone else gets CMS.

> **Interviewer:** How do you handle cookie deprecation — third-party cookies going away?

**Candidate:** *(Cross-question: cookieless targeting)* Chrome's Privacy Sandbox introduces the Topics API: the browser locally classifies the user into ~350 IAB topics based on browsing history and exposes them via JavaScript without sending user identity to the ad server. On the server side, we shift from user_id-based frequency capping to cohort-based: instead of "user X has seen this ad 3 times," we track "cohort Y has received N impressions" — privacy-preserving but less precise. For authentication-gated inventory (publisher has first-party login), we establish a hashed email match with advertiser CRM via clean room (AWS Clean Rooms, Google Ads Data Hub) — no raw PII shared. Long-term: contextual targeting (targeting the page content, not the user) gains importance. Our system needs to add a content classification layer at the Auction Gateway.

**Deep Dive 2: Fraud Detection in Pre-Bid.**

We run a two-layer filter. Layer 1 (rule-based, 1 ms): datacenter IP ranges (Spamhaus DROP list), known bad User-Agents, anomalous impression velocity (same user_id generating > 1000 impressions/minute). Layer 2 (ML, 4 ms): XGBoost model with 40 features — IP reputation score, device fingerprint consistency, mouse movement entropy (bots don't move the mouse naturally), session length, geographic consistency (IP in New York, GPS in London). Model inference runs on CPU in ~2 ms. If fraud_score > 0.7, we reject the bid request and return a no-fill to the publisher. We do NOT pass the request to DSPs — this protects DSP budgets from fraudulent spend and keeps our platform reputation high.

> **Interviewer:** What if a legitimate user is incorrectly flagged as fraud?

**Candidate:** *(Cross-question: false positive rate)* We track FP rate via a shadow audit: 1% of blocked requests are served anyway (the ad is shown but marked "audit" in the log). If the downstream engagement signals (click, video completion) are similar to non-blocked traffic, we're over-blocking and need to recalibrate the model threshold. The cost asymmetry: a false negative (serving a fraud impression) costs us $0.001-0.01 in fraudulent revenue + reputation damage with DSPs. A false positive (blocking a legitimate impression) costs us the same $0.001-0.01 in lost revenue. At scale, over-aggressive fraud detection can cost more in lost legitimate revenue than the fraud itself — this is the calibration argument for keeping FP rate < 0.5%.

**Deep Dive 3: ECPM Maximization and Floor Price.**

Second-price auction theory says the optimal strategy for the SSP is to set a floor price at the true value of the impression. Too high → no fill, publisher loses revenue. Too low → winner underpays, publisher loses revenue. We use a dynamic floor pricing model: train a regression model on historical clearing prices for similar impressions (same user segment, same time of day, same publisher). Serve a floor = predicted_clearing_price × 0.8. This floor is per-impression, computed in the Auction Gateway in ~2 ms using a lightweight model (no DSP call yet). Floor prices improve publisher revenue by 5–15% in A/B tests.

---

### Common Cross-Questions and Strong Answers (Staff Level)

**Q: How do you reconcile billing between your SSP logs and DSP logs? They often disagree.**
A: Discrepancy is normal in adtech — industry standard tolerance is ±10%. Causes: clock skew (win notice arrives after DSP's billing window closes), network retries (duplicate win notices), different attribution of view-through vs click-through. We build a reconciliation pipeline in Flink: join our auction log with DSP-reported impression logs on auction_id. Discrepancies > 5% trigger an alert and a dispute resolution workflow. We hold a rolling 24-hour buffer of win notices to enable retroactive reconciliation. Contractually, the DSP's count is used for billing, but we audit it against ours.

**Q: A major DSP is consistently winning 80% of auctions and then not paying. How do you detect and respond?**
A: Payment risk is a business problem with a technical signal. We track per-DSP win rate, clearing price, and payment status in a daily reconciliation table. If a DSP's payment-to-win ratio drops below 90% for two consecutive billing cycles, we automatically add them to a "reduced trust" tier: they still receive bid requests but their bids are subject to a 5× higher floor and their timeout budget drops from 80 ms to 50 ms. If non-payment continues, we remove them from the auction entirely. This requires a real-time DSP trust score fed into the Fan-out layer.

**Q: How do you prevent bid shading — DSPs submitting bids they know will clear at a lower price?**
A: Bid shading is rational DSP behavior in second-price auctions (bid your true value, your cost is lower). In first-price auctions (increasingly common), DSPs shade bids to avoid overpaying. From the SSP perspective, we counter bid shading with dynamic floors (described above) and by offering a "deal ID" mechanism: direct deals between publisher and specific advertiser bypass the open auction at a negotiated CPM. This creates a mixed auction: deal bids are evaluated first at guaranteed CPM, then open auction bids compete for remaining inventory. Publishers prefer this because deal CPMs are typically 20–40% higher than open auction.

---

*Chapter 89 complete. Next: Chapter 90 — Social Graph.*
