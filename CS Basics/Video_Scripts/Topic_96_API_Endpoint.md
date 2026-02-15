# What Is an API Endpoint? (REST Basics)

## Video Length: ~4-5 minutes | Level: Beginner

---

## The Hook (20-30 seconds)

A restaurant menu. Each dish has a number. "Item 12: Chicken Biryani." "Item 23: Paneer Tikka." You tell the waiter the number and what you want to do—order, cancel, modify. In APIs, each endpoint is like a menu item. It has an address (URL) and supports actions (methods). GET /users/123 means "show me user 123." POST /orders means "create a new order." The endpoint is the address where you send your request.

---

## The Story

You're at a restaurant. Menu in hand. Each dish has a number. Item 12: Chicken Biryani. Item 23: Paneer Tikka. Item 45: Masala Dosa.

You call the waiter. "Item 12, please. I want to order it." The waiter knows exactly what to do. The number is the address. The action is order.

APIs work the same way. Each endpoint is like a menu item. It has an address—a URL. And it supports actions—HTTP methods. GET /users/123 means "show me user 123." POST /orders means "create a new order." The endpoint is where you send your request. The method is what you want to do.

---

## Another Way to See It

A post office. Each mailbox has an address. "123 Main Street, Apt 4." You write that address on an envelope. The postman delivers to that exact location. The address tells the system where to go. An API endpoint is your envelope's address. The URL. The path. The place your request arrives.

---

## Connecting to Software

**Endpoint** = URL + HTTP method. The combination defines what you're asking for.

**Structure:**
- Base URL: `https://api.example.com`
- Path: `/users/123`
- Query params: `?category=electronics&sort=price`
- Full: `https://api.example.com/users/123?category=electronics`

**HTTP methods** = the action:
- **GET** — Read. "Give me this resource." Safe. Idempotent.
- **POST** — Create. "Make something new." Not idempotent.
- **PUT** — Replace. "Update this entirely." Idempotent.
- **PATCH** — Partial update. "Change just these fields."
- **DELETE** — Remove. "Delete this." Idempotent.

**REST design:** Endpoints represent resources (nouns). Not actions (verbs).  
Good: `GET /users/123`, `POST /orders`.  
Bad: `GET /getUser`, `POST /createOrder`.

**Resource hierarchy:** `/users/123/orders` = orders belonging to user 123. Nested. Logical. The URL structure mirrors your data model. Shallow hierarchies are easier. Deep nesting like `/users/123/orders/456/items/789` can get unwieldy. Sometimes a flatter structure works better: `/order-items/789` with `order_id` in the response. Balance clarity with simplicity.

**Response format:** Usually JSON. `{"id": 123, "name": "Alice"}`. Some APIs use XML. Most modern APIs use JSON. It's easy to parse. Human-readable. Lightweight. Status codes matter too: 200 OK, 201 Created, 400 Bad Request, 404 Not Found, 500 Server Error. The endpoint plus method plus status code tell the full story. Design your endpoints early. Get them right. Changing URLs later is painful. Think in resources. Think in hierarchy. Think in simplicity.

---

## Let's Walk Through the Diagram

```
API Endpoint Structure:

  https://api.shop.com/products?category=books&limit=10
  │     │              │         │
  │     │              │         └── Query params (filtering)
  │     │              └── Path (resource)
  │     └── Host
  └── Protocol

  RESTful design:

  GET    /users        → List all users
  GET    /users/123    → Get user 123
  POST   /users        → Create user
  PUT    /users/123    → Update user 123
  DELETE /users/123    → Delete user 123

  Hierarchy: /users/123/orders → Orders of user 123
```

---

## Real-World Examples

**1. GitHub API**  
`GET /repos/{owner}/{repo}` — Get a repository.  
`POST /repos/{owner}/{repo}/issues` — Create an issue.  
Clear. Resource-based. Easy to guess.

**2. Stripe API**  
`POST /v1/charges` — Create a charge.  
`GET /v1/customers/{id}` — Get a customer.  
Resources. Methods. Predictable.

**3. Twitter API**  
`GET /2/users/{id}` — Get user.  
`POST /2/tweets` — Create tweet.  
Same pattern. Nouns. Actions via methods.

**Why it matters:** Well-designed endpoints are self-documenting. A developer sees `GET /users/123` and knows what it does. No need to read a manual. Bad endpoints like `GET /getUserById?id=123` mix verbs and nouns. Confusing. Inconsistent. Good API design is about predictability. When every endpoint follows the same pattern, developers learn faster. Fewer bugs. Happier integrations.

---

## Let's Think Together

Design endpoints for a blog: list posts, get one post, create post, delete post, list comments on a post.

Pause. Think.

- List posts: `GET /posts`
- Get one post: `GET /posts/456`
- Create post: `POST /posts`
- Delete post: `DELETE /posts/456`
- List comments on a post: `GET /posts/456/comments`

Nested: comments belong to a post. So `/posts/456/comments`. Create a comment? `POST /posts/456/comments`. Simple. Consistent. RESTful. What about updating a comment? `PATCH /posts/456/comments/789`. Delete? `DELETE /posts/456/comments/789`. The hierarchy reflects the data model. Users understand it. Developers can guess it. That's good API design. Predictable. Boring in the best way.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup built an API. Endpoints: `GET /getUserById`, `POST /createNewOrder`, `GET /fetchAllProducts`. Verbs everywhere. Inconsistent. New developers confused. "Is it getProduct or fetchProduct?" Documentation exploded. They refactored to REST: `GET /users/{id}`, `POST /orders`, `GET /products`. One style. Easier to learn. Fewer mistakes. Naming matters. Stick to resources and methods.

---

## Surprising Truth / Fun Fact

The most-called API endpoint in the world is probably Google's search endpoint. Billions of requests per day. Every search. Every autocomplete. Every "did you mean?" That one endpoint—or family of endpoints—handles more traffic than most entire companies. Endpoints are the front door of the internet. Every mobile app, every web app, every integration talks to APIs through endpoints. Get the design right: clear, consistent, predictable. Your future self and your API consumers will thank you. Start with resources. Use standard methods. Keep it simple. That's how you build APIs that scale—not just technically, but in adoption and ease of use. Developers prefer APIs that feel intuitive. When your endpoints follow REST conventions, documentation writes itself. Tools like OpenAPI and Postman work better. The ecosystem expects this style. Fight it and you create friction. Embrace it and you lower the barrier for every integration. Your API documentation becomes shorter. Examples become clearer. Onboarding new developers takes less time. Good endpoint design is a gift that keeps giving—to your team and to everyone who integrates with you.

---

## Quick Recap (5 bullets)

- Endpoint = URL + HTTP method. The address and the action.
- REST: use resources (nouns), not verbs. Good: GET /users/123. Bad: GET /getUser.
- Hierarchy: /users/123/orders = orders belonging to user 123.
- Query params for filtering: /products?category=electronics&sort=price.
- Response format: usually JSON.

---

## One-Liner to Remember

*An API endpoint is the address where your request lands—URL plus method tells the server what resource you want and what to do with it.*

---

## Next Video

Next: API versioning. Why v1 and v2 exist. How to change your API without breaking the world. Topic 97: API Versioning—Why and How.
