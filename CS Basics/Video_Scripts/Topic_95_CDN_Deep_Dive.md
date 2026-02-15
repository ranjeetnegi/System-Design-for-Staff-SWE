# CDN: How It Works and When to Use It

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A book publisher in New York. Readers worldwide. A reader in Tokyo orders a book. It ships from New York. Two weeks. Terrible. The publisher opens warehouses in Tokyo, London, Mumbai. Same books. Reader in Tokyo gets the book from the Tokyo warehouse. Two days. CDN is the same idea—warehouses around the world for your website's content. Users get data from the nearest warehouse.

---

## The Story

A book publisher. Headquarters in New York. Books printed and stored there. A reader in Tokyo wants a book. Order placed. Ship from New York to Tokyo. Two weeks. High shipping cost. Reader waits. Bad experience.

The publisher rethinks. Opens warehouses. Tokyo. London. Mumbai. São Paulo. Same books. Copies in each. Reader in Tokyo orders. Ship from Tokyo warehouse. Two days. Low cost. Happy reader.

CDN does this for the web. Your website lives on an "origin" server—maybe in one data center. Users worldwide. Instead of everyone fetching from that one place, copies of your content sit in "edge" servers. Close to users. Tokyo user? Served from Tokyo edge. London user? London edge. Fast. Low latency. Your origin server breathes.

---

## Another Way to See It

A chain of restaurants. One central kitchen. Deliveries to 50 branches. Every order cooked in the center. Long delivery times. Then: each branch gets a prep kitchen. Popular dishes pre-made. Orders fulfilled locally. Faster. Central kitchen only restocks branches. CDN = prep kitchens at the edge. Origin = central kitchen.

---

## Connecting to Software

**CDN** = Content Delivery Network. A distributed system of edge servers that cache and serve content close to users.

**What it stores:** Static content. Images. CSS. JavaScript. Videos. Fonts. Anything that doesn't change per user.

**Request flow:**
1. User requests `yoursite.com/image.jpg`
2. DNS routes to nearest CDN edge (e.g., Cloudflare, Akamai)
3. Edge has the file? Cache HIT. Serve. Done.
4. Edge doesn't have it? Cache MISS. Fetch from origin. Store. Serve.
5. Next request for same file? Cache HIT. No origin hit.

**Push vs. Pull CDN:**
- **Push:** You upload content to the CDN proactively. Good for known assets. Blog images. Product photos.
- **Pull:** CDN fetches from origin on first request. Caches. Serves subsequent requests. Good for dynamic-ish content. Easier to set up.

**Cache-Control headers** tell the CDN how long to cache. You control this from your origin server. Send `Cache-Control: public, max-age=3600` and the CDN will cache for one hour. Send `Cache-Control: no-cache` and it will revalidate with origin on every request. Your caching strategy lives in these headers. Get them right. `Cache-Control: max-age=3600` = 1 hour. After that, edge revalidates with origin.

---

## Let's Walk Through the Diagram

```
CDN Request Flow:

  User (Tokyo)                    CDN Edge (Tokyo)              Origin (US)
       │                                │                            │
       │  GET /image.jpg                │                            │
       │──────────────────────────────►│                            │
       │                                │  Cache MISS                 │
       │                                │───────────────────────────►│
       │                                │  Fetch, store, serve       │
       │                                │◄───────────────────────────│
       │  Response (fast!)              │                            │
       │◄──────────────────────────────│                            │
       │                                │                            │
  Next user in Tokyo: Cache HIT. No origin call. Served from edge.
```

---

## Real-World Examples

**1. Netflix**  
Videos on CDN. Millions of users. Each video cached at edges worldwide. You hit play. Content comes from the nearest edge. Buffering minimal. Origin only serves when edge doesn't have the content. CDN carries most of the traffic.

**2. E-commerce product images**  
Thousands of product images. Same for all users. Perfect for CDN. Upload to CDN or pull on first request. Users globally get images from nearby edges. Page load fast. Origin handles orders and dynamic data, not images.

**3. News site**  
Article images. CSS. JS. Static assets. CDN. Breaking news? Same images, millions of views. CDN absorbs the spike. Origin stays stable.

---

## Let's Think Together

Your website has 10,000 daily users. All in one city. Do you need a CDN?

Pause. Think.

Probably not. If users are geographically close and your origin is in the same region, latency is already low. CDN adds complexity. Edge caching. Cache invalidation. Maybe overkill. Use CDN when: (1) users are global, (2) traffic is high, (3) static assets are heavy (images, video), (4) origin is getting hammered. For 10K users in one city? A good origin server might be enough. Start simple. Add CDN when you need it.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup. Launched a sale. Homepage with a banner. Banner cached on CDN. TTL: 24 hours. Sale ended early. Banner should say "Sale ended." They updated origin. CDN still served old banner. Users saw "50% off!" Added to cart. Sale already over. Anger. Support overloaded. The fix: purge CDN cache when content changes. Or use short TTL for time-sensitive content. CDN is powerful. Invalidation matters.

---

## Surprising Truth / Fun Fact

Cloudflare serves over 50 million HTTP requests per second across their CDN. That's more than Google, Amazon, and Twitter combined. The scale of CDN traffic is enormous. When you use a CDN, you're riding on infrastructure that handles a significant portion of the internet.

---

## Quick Recap (5 bullets)

- CDN = edge servers worldwide caching your static content; users get it from the nearest edge.
- Push CDN: you upload. Pull CDN: edge fetches on first request. Pull is easier to start with.
- Use CDN for: static assets, media, global users, high traffic. Not for: dynamic personalized content, real-time data.
- Cache-Control headers control how long CDN caches. Purge when content changes.
- For small, single-region traffic, CDN may be overkill. Start simple. Add CDN when latency becomes a problem, when you go global, or when your origin cannot handle the load. CDN is a tool. Use it when the problem fits. Static assets. Media. Global users. High traffic. If your traffic is local and low, a good origin server might be all you need. Measure first. Optimize when data tells you to. Tools like WebPageTest or Lighthouse can show you where your latency comes from. If most of it is from your origin and your users are global, CDN will help. If your bottleneck is database queries or API logic, CDN won't fix that. Fix the right problem. CDN is for static content delivery. Use it when that's your bottleneck.

---

## One-Liner to Remember

*CDN = warehouses of your content at the edge—users get it from nearby, your origin gets a break.*

---

## Next Video

Next: APIs from the ground up. What is an endpoint? REST basics. Topic 96: What Is an API Endpoint?
