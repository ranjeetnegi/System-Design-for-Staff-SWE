# HTTP: What is a Method? (GET, POST, PUT, DELETE)

## Video Length: ~4-5 minutes | Level: Beginner

---

## Hook (20-30 seconds)

You walk into a beautiful library. Tall shelves. Wooden tables. The smell of old books. A librarian greets you with a smile. "What would you like to do today?"

You could read a book. Add a new one. Fix an old one. Remove an outdated one. That's it. Four actions. Four verbs. The entire internet works the same way. Every website. Every app. Every API. Just four main actions. Once you see it, you'll never forget it. Let me show you.

---

## The Big Analogy

Picture that library. A big, organized room full of books. You approach the librarian.

**"I'd like to READ this book."** You point to a shelf. "Bring me that one, please." The librarian brings it. You look. You take notes. The book stays on the shelf. You didn't change anything. You just looked. That's **GET**. Read. Fetch. No side effects.

**"I wrote a new book. Can you ADD it to the collection?"** The librarian takes it. Finds a new spot on the shelf. The collection grows. Something new exists now. That's **POST**. Create. Add. Make something that wasn't there before.

**"This book has errors. Here's the corrected version. Please REPLACE the old one."** Same shelf. Same spot. Same book ID. But new content. The old one is gone. The new one is in its place. That's **PUT**. Update. Replace. Existing thing, new data.

**"This book is outdated. Please REMOVE it."** The librarian takes it off the shelf. Gone. Deleted. That's **DELETE**. Remove. Destroy.

Now notice something important. GET doesn't change anything. Safe. You can do it a hundred times—nothing breaks. POST creates new things. PUT updates existing things. DELETE removes things. Read. Add. Replace. Remove. Four verbs. These are called HTTP **methods**—or sometimes HTTP verbs. They tell the server: "What do you want me to DO with this data?"

---

## A Second Way to Think About It

Think of a filing cabinet. GET = open a drawer, look at a file. POST = add a new file. PUT = replace an entire file with a new version. DELETE = shred the file. Same idea. Different metaphor.

And what about **PATCH**? "Don't replace the whole book—just fix page 42." Or "Don't replace the entire file—just change the address field." PATCH = small update. Partial update. PUT = full replacement. PATCH = tweak one part. Both update. But PATCH is surgical. PUT is wholesale.

---

## Now Let's Connect to Software

Whenever your browser talks to a website, it sends a request. That request has a method. GET, POST, PUT, DELETE—and PATCH. But these four (or five) are the stars.

- **GET** — Safe. No changes. Just fetching. "Give me that page. Give me that image." You can refresh a GET request a hundred times. Nothing breaks. Idempotent and safe.

- **POST** — Creates new stuff. Log in. Sign up. Submit a form. Post a comment. The server creates something new in its database. Not idempotent—do it twice, you might create two things.

- **PUT** — Updates existing stuff. "Change my email." "Edit this product." Same URL, new data. Full replacement.

- **DELETE** — Removes stuff. "Delete my account." "Remove this item from cart." Poof—gone.

Every time you click, scroll, or type on the web, one of these methods is usually behind it.

---

## Let's Look at the Diagram

```
         THE INTERNET LIBRARY
    ┌─────────────────────────────────────┐
    │                                     │
    │   GET      "Read this book"         │  📖  No changes
    │   POST     "Add a new book"         │  ➕  Create new
    │   PUT      "Replace this book"      │  ✏️   Update entire
    │   PATCH    "Fix page 42 only"       │  🔧  Update part
    │   DELETE   "Remove this book"       │  🗑️   Remove
    │                                     │
    └─────────────────────────────────────┘

    REAL API EXAMPLES:

    GET    /products/123       → Show product details
    POST   /products           → Create new product
    PUT    /products/123       → Replace entire product data
    PATCH  /products/123       → Update just the price
    DELETE /products/123      → Remove product
```

See how the URL stays consistent? The method changes the action. `/products/123` with GET = read it. With PUT = update it. With DELETE = remove it. Same URL. Different verb. That's clean API design.

---

## Real Examples (2-3)

**Example 1: Social media.** You open your profile. That's a GET request—"Give me my profile data." You change your bio and click Save. That's a PUT—"Update my profile." You write a new post and hit Publish. That's a POST—"Create a new post." You delete an old photo. That's a DELETE—"Remove this post." Four actions. Same idea everywhere.

**Example 2: E-commerce.** Browsing products? GET. Adding to cart? POST. Updating quantity? PUT or PATCH. Removing from cart? DELETE. Every button, every click, maps to a method.

**Example 3: User management.** List users? GET /users. Create user? POST /users. Edit user? PUT /users/123. Delete user? DELETE /users/123. Predictable. Clean.

---

## Let's Think Together

Here's a question. You click "Like" on an Instagram post. Which HTTP method is used? GET? POST? PUT?

Pause. Think about it.

You're changing something. The like count goes up. So it's not GET—GET doesn't change things. Is it POST or PUT? You're creating a new "like" relationship. The like didn't exist before. So it's **POST**. If you were updating an existing like—maybe changing it from a heart to a laugh—that could be PUT or PATCH. But adding a new like? POST. Create. That's the answer.

---

## What Could Go Wrong? (Mini-Story)

Imagine a developer builds a "Delete Account" feature. They're lazy. They make it a GET request. The URL is something like: `https://mysite.com/delete-account?id=123`. One click. Account deleted.

Sounds fine, right? Here's the problem. Google's web crawler follows links. It does GET requests. All day long. Crawling the web. Indexing pages. What if someone links to that delete URL? In a forum. In a comment. Google crawls it. GET /delete-account?id=123. Your account gets deleted. By a robot. True story—this has happened. Companies have lost data because they put destructive actions behind GET. GET must be safe. No side effects. Never use GET to delete, create, or change anything. Use the right method. It's like using a hammer for a nail, not a spoon.

---

## Surprising Truth / Fun Fact

The HTTP spec defines more methods than just GET, POST, PUT, DELETE. There's HEAD (like GET but no body—just headers). OPTIONS (what can you do?). CONNECT (for proxies). TRACE (for debugging). But here's the thing: you'll use GET, POST, PUT, and DELETE 99% of the time. Maybe PATCH. The rest? Rare. Know they exist. But master the big four first.

---

## Quick Recap

- **GET** = Read. Fetch. No changes. Safe to repeat.
- **POST** = Add. Create. New thing.
- **PUT** = Replace. Update. Existing thing, new data.
- **PATCH** = Partial update. Fix one part. PUT = whole replacement.
- **DELETE** = Remove. Delete. Gone.
- These methods define what you can DO with data on the internet.

---

## One-Liner to Remember

> **GET reads, POST creates, PUT updates, DELETE removes—the four verbs of the web.**

---

## Next Video

Okay, so you sent a request. But what does the server say back? 200? 404? 500? Those numbers are like traffic lights for the internet. Let's decode them next!
