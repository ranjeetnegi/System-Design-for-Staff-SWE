# What is a CDN? — Content Delivery in Plain English

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You live in Mumbai. Your favorite bookstore's warehouse? New York. You order a book. It ships across the ocean. Two weeks. You wait. Frustrating. Now imagine the bookstore opens a small warehouse in Mumbai. Same books. When you order, the book comes from Mumbai. Two days. Same product. Different location. Ten times faster. A CDN does exactly that for the web — it puts copies of your content in warehouses around the world.

---

## The Story

An online bookstore. One warehouse. In New York. You're in Mumbai. You love their books. You order one. The package ships from New York. Flies over the Atlantic. Crosses continents. Two weeks later, it arrives. You're happy you have the book. But the wait? Brutal.

The bookstore gets smart. They open small warehouses. Mumbai. London. Tokyo. São Paulo. Same books. Multiple locations. You order again. This time the book ships from Mumbai. Two days. Not two weeks. Same book. Different starting point. That's the idea.

A CDN — Content Delivery Network — does this for websites. Your site lives on one server. The origin. Maybe in Virginia. A user in India visits. Without a CDN, every image, every CSS file, every video travels from Virginia to India. Hundreds of milliseconds. Maybe more. Each round trip adds latency. A typical webpage has 50, 100, 200 resources. That's 200 round trips across the ocean. With a CDN? Copies of that content live on edge servers in Mumbai, Delhi, Bangalore. The user gets it from the nearest edge. Twenty milliseconds. Ten times faster. Here's the crazy part — the user never knows. They just notice the site feels fast. And your origin server? It gets a fraction of the requests. The CDN absorbs the load.

---

## Another Way to See It

A chain of coffee shops. One roastery in Seattle. Every store used to get beans shipped from Seattle. Long delivery. Now each city has a local depot. Beans go from Seattle to depots once. Then each store gets beans from its depot. Fast. Fresh. Same coffee. Shorter distance for the last mile. CDN is the depot system for web content.

---

## Connecting to Software

Your origin server holds the master copy. The CDN has edge servers in hundreds of cities. When a user requests an image, the CDN checks: Do I have it at the nearest edge? If yes, serve it. If no, fetch from origin, cache it at the edge, then serve. Next user in that region? Served from cache. No round-trip to origin. Latency drops. Origin load drops. Everyone wins.

---

## Let's Walk Through the Diagram

```
                    ORIGIN SERVER (Virginia)
                           |
                    Initial fetch / cache miss
                           |
         +-----------------+------------------+
         |                 |                  |
         v                 v                  v
    [Mumbai Edge]    [London Edge]     [Tokyo Edge]
         |                 |                  |
         v                 v                  v
    User in India    User in UK        User in Japan
    (20ms)           (15ms)            (25ms)
    
    Without CDN: All users hit Virginia → 150-300ms
    With CDN: Users hit nearest edge → 15-30ms
```

**First request:** User in Mumbai asks for image.jpg. Edge doesn't have it. Fetches from origin. Caches at Mumbai edge. Serves to user. Slow that one time.

**Second request:** Same image, same user or another user in Mumbai. Edge has it. Serves from cache. Fast. No origin hit.

**What gets cached vs what doesn't:** Static content — images, CSS, JavaScript, fonts, videos — is perfect for CDN. It doesn't change per user. Your bank balance? That's dynamic. Different for every user. You can't cache it at the edge and serve it to everyone. CDNs excel at static. For dynamic content, you often bypass the CDN or use very short cache times.

---

## Real-World Examples (2-3)

**1. Netflix:** Streams 4K video to 200+ million users. One server? Impossible. Netflix puts video files on CDN edges globally. You stream from a server in your city.

**2. Cloudflare:** Operates a huge CDN. Images, CSS, JS — cached at the edge. Most sites use it or something like it. It also provides DDoS protection and SSL — the CDN edge handles encryption so your origin doesn't have to.

**3. E-commerce product images:** Amazon, Flipkart — product photos load from nearby CDN edges. Fast thumbnails. Fast pages.

---

## Let's Think Together

**Question:** Netflix streams 4K video to 200 million users. Can ONE server handle that? How does a CDN help?

**Pause. Think about it...**

**Answer:** No. One server would melt. A CDN spreads the load. Video files are replicated to edges worldwide. When you hit play, you're not pulling from Netflix HQ. You're pulling from a server maybe 50 miles away. Thousands of users in your region share that local server. The origin only deals with uploads and cache misses. The edges handle the massive streaming load. Without a CDN, Netflix wouldn't exist at its scale.

---

## What Could Go Wrong? (Mini Disaster Story)

You update your website. New logo. New homepage. You deploy. You're proud. You tell your friend to check it out. They see the old site. The old logo. "Did you really update?" Yes. But they're getting a cached copy from the CDN. You forgot to invalidate the cache. The CDN is still serving the old files. Could be hours. Could be a day. Depends on TTL. You fix the origin. But the world sees the old version until the cache expires or you purge it. Cache invalidation — never forget it.

---

## Surprising Truth / Fun Fact

Cloudflare's CDN operates in over 300 cities worldwide. When you visit most major websites, you're often talking to a server in YOUR city — not the company's headquarters. The website feels local because, in a sense, it is. The content was copied to a server near you before you asked for it.

---

## Quick Recap (5 bullets)

- A CDN caches copies of your content (images, CSS, JS, video) on edge servers around the world.
- Users get content from the nearest edge — lower latency, faster loads.
- Static content is cached. Dynamic content (e.g., bank balance) usually is not.
- Popular CDNs: Cloudflare, AWS CloudFront, Akamai, Fastly.
- Cache invalidation matters — when you update, purge the cache or users see stale content.

---

## One-Liner to Remember

> **A CDN puts your content in warehouses around the world. Users get it from the one next door.**

---

## Next Video

Content travels fast. But HOW does it travel? Reliable, like a registered letter? Or fast and loose, like shouting across a playground? The choice of protocol changes everything. Next: TCP vs UDP.
