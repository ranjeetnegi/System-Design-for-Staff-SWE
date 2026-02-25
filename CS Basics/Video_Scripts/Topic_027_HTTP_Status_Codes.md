# HTTP Status Codes: 200, 404, 500 (What They Mean)

## Video Length: ~4-5 minutes | Level: Beginner

---

## Hook (20-30 seconds)

You've seen it. That annoying page: **"404 - Page Not Found."** Maybe with a cute illustration. Maybe with a broken link. But what does 404 actually MEAN? Why 404 and not 403 or 500? Why that number?

Here's the truth. Every time your browser talks to a server, the server sends back a NUMBER. Before any content. Before any HTML. Just a number. That number tells you what happened. It's like a traffic light for the internet. Green means go. Red means stop. And the numbers? They tell you exactly why. Let me decode these secret numbers for you.

---

## The Big Analogy

Imagine you're at a restaurant. You order food. The waiter disappears into the kitchen. A few minutes later, he comes back. But he doesn't just drop the plate. He says something first. A number. A code. A status.

**"200."** He smiles. "Here's your food! Everything is perfect." He puts the plate in front of you. You're happy. Success. That's 200 OK.

**"301."** He hands you a card. "We actually moved to a new location last month. Here's the new address. Go there next time." Permanent redirect. The old place is gone.

**"400."** He looks confused. "Sorry, you asked for something that doesn't make sense. 'I want invisible soup?' I don't understand." Your mistake. Bad request.

**"401."** He crosses his arms. "You need a membership card to eat here. Show your card first." You're not authenticated. Who are you? Prove it.

**"403."** He sees your card. But he shakes his head. "I see your card. But you're not allowed in the VIP section. Sorry." You're authenticated—we know who you are—but you're not authorized. Different thing. 401 = who are you? 403 = you can't do this.

**"404."** He shrugs. "That dish doesn't exist on our menu. Never heard of it." Not found. The thing you asked for doesn't exist.

**"429."** He's flustered. "You've ordered 50 times in 1 minute! Slow down! The kitchen can't keep up." Too many requests. Rate limited.

**"500."** He looks scared. "The kitchen caught fire. We can't make anything right now. I'm so sorry." Server error. Something broke on their side. Not your fault.

**"503."** He's exhausted. "The kitchen is too busy. We're overwhelmed. Try again in a few minutes." Service unavailable. Overloaded.

The first digit tells you the category. 2xx = success. 3xx = redirect. 4xx = your mistake. 5xx = their mistake. Let that sink in.

---

## A Second Way to Think About It

Think of status codes as emoji for your request. 200 = 😊 "All good!" 404 = 🤷 "Can't find it." 500 = 😱 "Something exploded." They're short. They're clear. They tell the whole story in one number.

---

## Now Let's Connect to Software

Every time your browser sends a request to a server, the server ALWAYS sends back a status code. Always. No exceptions.

- You visit google.com → **200** (here's the page!)
- You visit google.com/asjdfklasdf → **404** (that page doesn't exist)
- Google's server crashes → **500** (something broke on their end)
- You send too many requests in one second → **429** (slow down!)
- You try to access a page without logging in → **401** (who are you?)
- You're logged in but try to access admin panel → **403** (you can't do that)
- A new user was created → **201 Created** (we made it!)
- The page moved permanently → **301** (go here instead)
- A middle server is confused → **502 Bad Gateway**
- The server is overloaded → **503** (try again later)

As a developer, you NEED to know these codes. They tell you exactly what went wrong—or right.

---

## Let's Look at the Diagram

```
HTTP STATUS CODES - The Traffic Light System

┌─────────────────────────────────────────────────┐
│                                                 │
│   2xx  SUCCESS (Green Light)                    │
│   ├── 200 OK          → "Here you go!"          │
│   ├── 201 Created     → "New thing made!"        │
│   └── 204 No Content  → "Done! Nothing to show." │
│                                                 │
│   3xx  REDIRECT (Yellow Light)                  │
│   ├── 301 Moved       → "We moved permanently"   │
│   └── 302 Found       → "Temporarily over here"  │
│                                                 │
│   4xx  CLIENT ERROR (Red Light - YOUR fault)    │
│   ├── 400 Bad Request → "Your request is wrong"  │
│   ├── 401 Unauthorized→ "Who are you? Log in!"   │
│   ├── 403 Forbidden   → "You can't access this"  │
│   ├── 404 Not Found   → "Doesn't exist"          │
│   └── 429 Too Many    → "Slow down!"             │
│                                                 │
│   5xx  SERVER ERROR (Red Light - SERVER's fault) │
│   ├── 500 Internal    → "Something broke!"      │
│   ├── 502 Bad Gateway → "Middle server confused" │
│   └── 503 Unavailable → "Too busy, try later"   │
│                                                 │
└─────────────────────────────────────────────────┘

EASY RULE:
  2xx = Happy path. Green. Go.
  4xx = You messed up. Red. Fix your request.
  5xx = They messed up. Red. Server problem.
```

Look at the first digit. 2 = success. 4 = client error. 5 = server error. That's the quick decode. Memorize that pattern.

---

## Real Examples (2-3)

Open any website. Right-click → Inspect → Network tab. Reload the page. You'll see dozens of requests. Each one has a status code. The main page: 200. An image that loaded: 200. A missing image: 404. A redirect: 301 or 302. If the site is down: 503. Try it. Visit a URL that doesn't exist on any website. You'll get a 404 page. Now you know what that number means.

Another example: You build a login form. User types wrong password. What status should you return? 200 with "Wrong password" in the body? No. That's lying. The request failed. Return **401 Unauthorized**. The client knows: authentication failed. Different from 403—that's "you're logged in but you can't do this." 401 = "we don't even know who you are."

---

## Let's Think Together

Here's a question. You try to log in with the wrong password. Which status code should the server return? 400? 401? 403?

Pause. Think about it.

400 means "your request is malformed." Wrong format. Bad JSON. That's not it—the password was wrong, not the format.

403 means "forbidden." You're authenticated, but you're not allowed. But you're NOT authenticated—you failed to prove who you are.

The answer is **401 Unauthorized**. You tried to authenticate. You failed. The server is saying: "I don't know who you are. Try again." 401 = authentication failed. 403 = you're known, but you can't access this resource. Big difference.

---

## What Could Go Wrong? (Mini-Story)

A team builds an API. Users can create profiles. The developer codes the "create profile" endpoint. It works. But they're lazy. They always return 200. Even when the database fails. Even when the profile wasn't saved. The function catches the error, returns a message: "Error: Could not save." But the status code? Still 200.

The frontend developer trusts the status code. 200 means success. So they show "Profile saved!" They move the user to the next screen. But the profile wasn't saved. The database had a glitch. The user thinks everything is fine. Hours later, they come back. No profile. "I thought I saved it!" Confusion. Anger. Support tickets. Debugging nightmare.

The fix? Return the RIGHT status code. 200 means success. If it failed, return 500. Or 400. Be honest. The status code is a contract. Don't lie.

---

## Surprising Truth / Fun Fact

Why 404? The story goes: at CERN, where the web was invented, there was a Room 404. That's where the web server lived. When someone asked for a page that didn't exist, the server would say: "Go to Room 404. They'll tell you." Over time, 404 became "not found." The story might be apocryphal—not everyone agrees—but it's a fun origin myth. And here's another fun fact: some companies create custom 404 pages. GitHub has one with a Star Wars theme. Amazon has a friendly "Oops!" page. They turn an error into a moment. Clever.

---

## Quick Recap

- Status codes = the server's answer about what happened
- **2xx** = Success (green light)
- **3xx** = Redirect (moved somewhere else)
- **4xx** = Client error (YOU did something wrong)
- **5xx** = Server error (THEY broke something)
- The most common: 200 (OK), 404 (Not Found), 500 (Server Error)
- 401 = not authenticated. 403 = not authorized. Different things.

---

## One-Liner to Remember

> **Status codes are traffic lights. 2xx = green (go!). 4xx = red (your fault). 5xx = red (their fault). Always check the light before you drive.**

---

## Next Video

The server sends back a status code, but it also sends other information—like instructions and metadata. These are called HTTP headers. Think of them as labels on an envelope. Next video: What are HTTP Headers?
