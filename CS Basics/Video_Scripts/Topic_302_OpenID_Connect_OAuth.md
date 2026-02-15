# OpenID Connect vs OAuth: The Identity Layer

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You tap "Sign in with Google." One click. You're in. But what's actually happening behind that button? Is it OAuth? Is it OpenID Connect? And why does it matter? Here's the secret: OAuth answers "Can you do this?" OpenID Connect answers "Who are you?" They work together—but they're not the same thing.

## The Story

Imagine you're at a club. There's a bouncer at the door. Two different questions get two different answers.

**OAuth** is like a VIP pass. The bouncer asks: "Are you allowed in?" You show your pass. Yes or no. That's **authorization**—what you're permitted to do. Can this app access my photos? My calendar? My contacts? OAuth handles that.

**OpenID Connect** is like your ID card. The bouncer asks: "Who are you?" You show your ID. Name, photo, date of birth, maybe your address. That's **authentication**—who you are. Your identity. Your profile.

OAuth tells the app *what* you're allowed to do. OpenID Connect tells the app *who* you are. They're related. But different.

## Another Way to See It

Think of a hotel. OAuth is the room key. It says: "This person can enter room 402." It doesn't say who the person is. OpenID Connect is the check-in form. Name, ID number, signature. Now the hotel knows *who* has the key. OAuth = permissions. OpenID Connect = identity.

## Connecting to Software

Here's the flow in practice. User clicks "Sign in with Google." Your app redirects to Google. User logs in (or is already logged in). Google redirects back with a *code* in the URL. Your backend exchanges that code for tokens. With pure OAuth, you get an access token. With OpenID Connect, you get an access token *and* an ID token. The ID token is a JWT. Decode it—no API call needed—and you have the user's claims: sub (subject, the user ID), name, email, picture. Store that. Use it. No extra round-trip to a userinfo endpoint.

**OAuth 2.0** is an authorization framework. You've used it. "Allow this app to access your Google photos?" You click Yes. The app gets an **access token**. That token has scopes: read photos, write photos, delete photos. The app can now do those things on your behalf. But the token does *not* tell the app your name, email, or profile picture. It just says: "Someone with these permissions is making this request."

**OpenID Connect** is built *on top of* OAuth 2.0. It adds an **ID token**—a JWT (JSON Web Token). The ID token contains: your user ID, name, email, profile picture, maybe your locale. Now the app knows *who* authorized the request. "This is Ranjeet. And he authorized photo access." Identity + authorization, together. Think of it this way: OAuth gives you a key. OIDC gives you the key *and* a nametag. You need both if you want to greet the user by name and also access their resources.

## Let's Walk Through the Diagram

```
  USER          APP          IDENTITY PROVIDER (Google)

    |  "Sign in"   |
    |------------->|
    |              |  Redirect to Google
    |<-------------|
    |              |
    |  [Login at Google] ------>  User enters password
    |              |              <------ ID Token + Access Token
    |  Redirect back with tokens
    |<-------------|
    |              |
    |  App now has: 
    |  - Access Token (what user allowed)
    |  - ID Token (who the user is)
```

The access token goes to Google's APIs: "Give me this user's photos." The ID token stays with your app: "Display: Welcome, Ranjeet."

## Real-World Examples (2-3)

- **"Sign in with Google" on a random blog**: That's OpenID Connect. The blog needs to know who you are (to show your name, avatar) and might also need OAuth (to post on your behalf). Usually both.
- **A backup app that syncs your Google Drive**: Primarily OAuth. It needs permission to read/write files. It might not care about your name—just that it's your drive.
- **Enterprise SSO (Single Sign-On)**: OpenID Connect. The company needs to know the employee's identity—department, role, email—for access control. OAuth alone would say "this person can access the HR system." OIDC says "this is Jane from Engineering, she can access the HR system." The identity shapes the authorization. RBAC often needs both.

## Let's Think Together

Here's the question: **"Sign in with Google"—is this OAuth or OpenID Connect? What tokens are involved?**

Answer: Both! OAuth gives you the access token (authorization). OpenID Connect adds the ID token (identity). When you "Sign in with Google," you typically get both. The app uses the ID token to know who you are. It uses the access token only if it needs to call Google APIs on your behalf.

## What Could Go Wrong? (Mini Disaster Story)

Your app only uses OAuth. User signs in. You get an access token. Great. But your app needs to show "Welcome, Sarah!" on the homepage. The access token doesn't have Sarah's name. You'd have to make an extra API call to Google: "Who does this token belong to?" That's slow. Adds latency to every page load. And you're using the token for something it wasn't designed for. OpenID Connect solves this: the ID token *is* the user info. It's already in the flow. No extra round-trip. Use the right tool. Most "Sign in with Google" implementations use OIDC for this exact reason—they need the user's identity, not just permission to act on their behalf.

## Surprising Truth / Fun Fact

OpenID Connect was created in 2014—years after OAuth 2.0 (2012). Before OIDC, everyone was hacking OAuth to get identity: "Call the /me endpoint with the access token." Every provider had different userinfo endpoints, different response shapes. OIDC standardized it. One token, one format (JWT), one flow. Now "Sign in with Google" is just OpenID Connect. Same for Microsoft, Auth0, Okta. Simple. Interoperable. The identity layer finally had a standard.

---

## Quick Recap (5 bullets)

- OAuth = authorization: what the app can do (access token, scopes)
- OpenID Connect = authentication: who the user is (ID token, JWT with claims)
- OIDC is built on OAuth 2.0; you often get both tokens in one flow
- Access token → call APIs. ID token → display user info in your app
- "Sign in with Google" uses both: OAuth for permissions, OIDC for identity—two tokens, one flow, complete picture

## One-Liner to Remember

*OAuth says "you can." OpenID Connect says "you are."*

---

## Next Video

Up next: gRPC vs REST—when should you use which? The waiter with a notepad versus the QR code to the kitchen. See you there.
