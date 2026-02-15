# gRPC vs REST: When to Use Which

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Two ways to order food at a restaurant. First way: you write your order on a paper note in English. Hand it to the waiter. The waiter reads it. Human-readable. Universal. Anyone can understand. Second way: you scan a QR code, select items on a screen, and it shoots directly to the kitchen computer. Binary. Machine-to-machine. Faster. But the kitchen better have the exact same system. That's REST versus gRPC. Which one should you pick?

## The Story

**REST** is the paper note. HTTP/1.1. JSON. Human-readable. You can open a REST API in your browser, curl it, inspect the response. Any language, any client. A frontend dev, a mobile dev, a random script—everyone gets it. Simple. Widely understood.

**gRPC** is the QR-to-kitchen pipeline. HTTP/2. Protocol Buffers—binary format. Not human-readable. You can't just "curl" it and see JSON. But it's *fast*. Smaller payloads. Multiplexing. Streaming. Bidirectional. And it generates code for you: write a `.proto` file, get client and server code in Go, Java, Python, whatever. Strict contracts. No guessing.

## Another Way to See It

REST is like sending a letter. Written in plain language. Anyone who knows the language can read it. Slow to write, slow to deliver, but universal. gRPC is like a secret handshake. Efficient. Compact. But only people who know the handshake understand it. Your internal services? They know the handshake. A random third-party developer? Give them the letter.

## Connecting to Software

REST uses URLs. `GET /users/123`. `POST /orders`. Each endpoint is a resource. Stateless. Cacheable (HTTP caching works naturally with URLs—every cache knows what to store). Great for public APIs, web apps, mobile apps that need to talk to your backend. Browser can call it. Postman can call it. curl from the command line. Third-party developers love it because the contract is visible, debuggable, and well-understood. Everyone's happy.

gRPC uses a schema. You define your service and messages in a `.proto` file. The compiler generates code. Client and server are *forced* to agree on the contract. Change the schema? Regenerate. Both sides update. No "I thought the field was called `user_id`" surprises. No version mismatches hiding in the shadows. And because it's binary, a 10KB JSON payload might become 2KB. Latency drops. Throughput rises. For internal services doing millions of RPCs per second, that adds up fast.

## Let's Walk Through the Diagram

```
REST:
  Client ---[HTTP/1.1, JSON]---> Server
  GET /users/123
  Response: {"id":123,"name":"Ranjeet","email":"r@x.com"}

gRPC:
  Client ---[HTTP/2, Protobuf binary]---> Server
  GetUser(UserRequest{id:123})
  Response: <binary blob, smaller, faster>
```

REST: one request, one response. Request/response. Simple. gRPC: same, but also supports streaming. Unary (request/response), server streaming (server sends multiple messages), client streaming (client sends multiple messages), bidirectional (both stream). For a log ingestion pipeline or a real-time dashboard, streaming is huge. REST would need polling or WebSockets. gRPC does it natively. And HTTP/2 multiplexing means many requests over one connection—no head-of-line blocking. REST over HTTP/1.1 opens a new connection per request (or uses keep-alive with limits). gRPC is built for high concurrency out of the box. Client can send a stream. Server can respond with a stream. Or both. Real-time dashboards, file uploads, live updates—gRPC shines.

## Real-World Examples (2-3)

- **Stripe's public API**: REST. Third-party developers integrate. They need docs, Postman, curl. JSON is friendlier.
- **Google's internal services**: gRPC. Millions of RPCs per second. Latency matters. They control both sides.
- **Kubernetes API**: REST for humans, but also supports gRPC for internal components. Best of both.
- **Your mobile app to backend**: Could be REST (simpler, works with any HTTP client). Could be gRPC if you control both and need speed (e.g., real-time game state). Mobile gRPC needs gRPC-Web or a native client—more setup. REST works out of the box. Unless you're Google-scale, REST is usually the pragmatic choice for mobile.
- **Event-driven microservices**: Service A publishes to a topic. Service B consumes. Often uses gRPC for the control plane (schema registry, service discovery) while the data plane might use something else. gRPC fits well where you have typed contracts and code generation. REST fits where you want openness and ease of inspection.

## Let's Think Together

**Your mobile app talks to your backend. REST or gRPC? What about backend Service A talking to Service B?**

Mobile to backend: often REST. Easier debugging. Works with standard HTTP. Mobile devs know REST. Unless you need streaming or extreme performance, REST is fine. Service A to Service B: gRPC often wins. Internal. High throughput. You control both. Code generation keeps them in sync. No third party. Speed matters.

## What Could Go Wrong? (Mini Disaster Story)

You chose gRPC for your public API. "It's faster! Binary is better!" Your API is consumed by startups, indie devs, and random scripts. They want to curl it. They want to see JSON. They want Postman collections. Instead they get Protobuf. They need to generate client code from your .proto. They need to understand the schema. Browser clients? gRPC isn't native. You need gRPC-Web—a proxy. More complexity. Adoption drops. Support tickets rise. "How do I call this from Python?" "Why can't I just use fetch?" You saved 50ms of latency. You lost adopters. Pick the right tool for the audience.

## Surprising Truth / Fun Fact

gRPC was created by Google. The "g" has stood for different things over the years—Google, good, green. It doesn't matter. What matters: HTTP/2 and Protobuf were designed for exactly this. REST was designed for the web, for documents, for humans. gRPC was designed for machines talking to machines. Different design goals. Different sweet spots. Kubernetes uses gRPC internally. Envoy uses it. Cloud-native infrastructure runs on gRPC. Your public-facing API? Probably REST. Know your audience. Pick accordingly.

---

## Quick Recap (5 bullets)

- REST: HTTP/1.1, JSON, human-readable, universal, browser-friendly, good for public APIs—curl it, inspect it, document it easily
- gRPC: HTTP/2, Protobuf, binary, fast, streaming, code generation, good for internal services
- Use REST when: public APIs, browser clients, third-party devs, simple CRUD, wide compatibility
- Use gRPC when: microservice-to-microservice, high throughput, low latency, streaming, you control both sides
- Don't use gRPC for public APIs unless you have a strong reason—REST is the standard; when in doubt, REST wins for openness

## One-Liner to Remember

*REST for the world. gRPC for your own backyard.*

Bottom line: match the protocol to your consumers. Public, diverse, browser-heavy? REST. Internal, high-throughput, you control both ends? gRPC. The "best" choice depends on context.

---

## Next Video

Up next: GraphQL—when "order exactly what you want" beats the fixed menu. See you there.
