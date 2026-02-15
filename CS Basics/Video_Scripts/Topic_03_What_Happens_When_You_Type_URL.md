# What Happens When You Type a URL and Press Enter?

## Video Length: ~4-5 minutes | Level: Beginner

---

## Hook (20-30 seconds)

You type "google.com" and hit Enter. One second later, you see the page. Simple, right? You do it every day. But here's the surprise: **your computer had no idea where Google lived.** Think about that for a second. You typed a name. A word. "Google." Your computer doesn't know addresses. It had to ask around. It had to find the right place. It had to knock on the right door. And it did all of that in less than a second. How? Let me show you this journey. It's like sending a letter to a stranger's house—and getting a reply before you blink.

---

## The Big Analogy

Imagine you want to send a letter to your friend. You know their name: "Priya." But the post office doesn't deliver to names. The post office needs an **address**.

**Step 1: You write the letter.** "Dear Priya, I hope you're well..." You put it in an envelope. You write "Priya, Mumbai" on the front. But that's not enough. Where in Mumbai?

**Step 2: You go to the post office.** You say: "I need to send this to Priya in Mumbai. Where does she live?" The post office looks in their book. They have a list. Names and addresses. "Priya lives at 42 Garden Street, Mumbai." They write the full address on your envelope. Now the postman knows where to go.

**Step 3: The postman takes the letter.** He doesn't deliver to "Priya." He delivers to "42 Garden Street." He finds the house. He knocks. He hands over the letter.

**Step 4: The person at that house (let's say it's Priya's family) receives it.** They read it. They write a reply. They give the reply to the postman.

**Step 5: The postman brings the reply back to you.** You never needed to know "42 Garden Street." The post office found it for you. That's exactly what happens when you type a URL.

---

## Now Let's Connect to Software

When you type "youtube.com" and press Enter, here's the full journey:

**Step 1: Your browser says:** "I need youtube.com. Where does it live?" Your computer doesn't store this. It has to ask.

**Step 2: DNS (Domain Name System)**—this is like the post office. Your browser asks DNS: "Where is youtube.com?" DNS looks in its list. It says: "youtube.com lives at 142.250.185.78." We call this number an **IP address**—like a street address for computers. Every website has one. But we use names because "youtube.com" is easier to remember than "142.250.185.78."

**Step 3: Your browser now has the address.** It opens a connection to that address. Like the postman walking to 42 Garden Street. This is called a **TCP connection**—a reliable link between your computer and the server.

**Step 4: Your browser sends an HTTP request.** "Give me the YouTube homepage." The request travels over the internet. It reaches the server at 142.250.185.78.

**Step 5: The server receives it.** It understands: "Someone wants the YouTube homepage." It finds the right files. It prepares the page. It creates a response.

**Step 6: The server sends the response back.** The page—HTML, images, videos—travels back through the internet to your computer.

**Step 7: Your browser receives it.** It reads the HTML. It loads the images. It renders the page. You see YouTube. All of this in less than one second. Here's the crazy part.

---

## Let's Look at the Diagram

```
    FULL JOURNEY: YOU → DNS → SERVER → YOU
    
    [YOU]              [DNS]              [SERVER]
    Browser         (Post Office)         (YouTube)
       │                    │                    │
       │  1. "Where is      │                    │
       │     youtube.com?"  │                    │
       │ ───────────────►  │                    │
       │                    │  2. "142.250.185.78"
       │  ◄───────────────  │                    │
       │                    │                    │
       │  3. "Give me the page" (TCP + HTTP)     │
       │ ─────────────────────────────────────►  │
       │                    │                    │ 4. Server processes
       │                    │                    │    finds files
       │                    │                    │    prepares response
       │  5. "Here is the page"                  │
       │  ◄────────────────────────────────────  │
       │                    │                    │
       │  6. Browser renders. You see YouTube!   │
```

Follow the numbers. Step 1: Ask DNS. Step 2: Get the address. Step 3: Send the request. Step 4: Server works. Step 5: Get the response. Step 6: See the page. Every URL you type goes through this. Every single one.

---

## Real Examples

**Example 1: You search "weather in Delhi" on Google.** Your browser asks DNS: "Where is google.com?" DNS answers with an IP. Your browser connects. It sends: "Show me search results for weather in Delhi." Google's server searches. It finds weather data. It sends back a page. You see the results. Same flow.

**Example 2: You open Instagram.** DNS finds Instagram's address. Your browser connects. It sends: "Give me my feed." Instagram's servers find your account, your follows, the posts. They send the data. Your phone displays it. Same flow.

**Example 3: You type your bank's URL.** DNS finds the bank. Your browser connects with encryption (HTTPS). It sends: "Show me the login page." The bank's server sends it. You see the login form. Same flow. Every. Single. Time.

---

## Fun Fact

This entire process—DNS lookup, connection, request, response, rendering—happens in **less than 1 second**. Often 200 or 300 milliseconds. You blink, and 10 steps happened across thousands of kilometers. Your request might have traveled from India to a server in the USA and back. In the time it takes to say "google.com." That's not magic. That's decades of engineering. Let that sink in.

---

## What Could Go Wrong? (Mini-Story)

What if the post office gives you the wrong address? You send a letter to "42 Garden Street" but Priya moved last month. The letter goes to the wrong house. A stranger gets it. No reply. You wait. Nothing.

In tech, that's when **DNS is wrong or hacked**. Someone could change the records. You type "mybank.com" thinking you're going to your bank. But you get sent to a fake site. A copy. It looks the same. You enter your password. Now the hackers have it. That's why we have HTTPS—the lock in the browser. That's why you should always check the URL. Trust, but verify. One wrong address, and everything can go wrong.

---

## Quick Recap

- When you type a URL, your browser first asks DNS: "Where does this site live?"
- DNS returns an IP address (like a street address for computers).
- Your browser opens a connection and sends an HTTP request to that address.
- The server receives it, prepares the page, and sends back a response.
- Your browser renders the response. You see the page.
- DNS = the post office that finds addresses for names. The whole journey happens in less than a second.

---

## One-Liner to Remember

> **DNS is the post office of the internet—it turns names like google.com into addresses computers can find.**

---

## Next Video

You send a request. The server sends back a response. But what exactly are these? What do they look like? **Request and response**—the two words behind every click on the internet. Next video, we break them down. You'll see the real conversation. Don't miss it.
