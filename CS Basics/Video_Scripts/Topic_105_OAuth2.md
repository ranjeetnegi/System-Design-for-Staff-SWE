# OAuth 2.0: High-Level Flow

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You're at a hotel. The valet asks for your keys. You need to think fast. Do you hand over your entire keychain? Your house key. Your office key. Your car key. Everything? No. You give them ONE key. The car key. They can park your car. They can't enter your house. They can't open your safe. That's OAuth. **Limited access**. You never give an app your password. You give it a token that says "you can do THIS. Nothing else." Let me show you how that works when Spotify says "Login with Facebook."

---

## The Story

OAuth 2.0 is about delegated access. You have data somewhere—Facebook, Google, your bank. An app wants to use that data. The old way: "Give me your Facebook password." You'd be insane to do that. The app could do anything. Read your messages. Post as you. Delete your account. OAuth solves this. You never give the app your password. You go to Facebook. You log in. Facebook asks: "Spotify wants to access your friends list. Allow?" You say yes. Facebook gives Spotify a **token**—a limited key. Spotify can read your friends. That's it. No password. No full access. Just what you approved.

The flow has names. **Resource Owner** = you. You own the data. **Client** = the app (Spotify). It wants access. **Authorization Server** = Facebook's login and consent page. **Resource Server** = Facebook's API that has your data. The client never sees your password. You talk to the authorization server. You grant permission. The authorization server gives the client a token. The client uses that token to talk to the resource server. Your password stays with Facebook. Safe.

---

## Another Way to See It

Think of a hotel room key. The front desk gives you a key. That key opens YOUR room. It doesn't open other rooms. It doesn't open the safe. Limited scope. OAuth tokens have scopes too. "Read friends." "Post on my behalf." "Access email." You choose what to grant. Or think of a parking garage. You get a ticket. The ticket lets you in and out. It doesn't give you keys to the manager's office. OAuth = the ticket. Limited. Revocable. Not your master key.

---

## Connecting to Software

The **Authorization Code** flow—the most secure for web apps. Step 1: User clicks "Login with Facebook" on Spotify. Step 2: Spotify redirects the user to Facebook. Step 3: User logs into Facebook (if not already). Step 4: Facebook shows: "Spotify wants: access your friends list, access your profile." Step 5: User clicks "Allow." Step 6: Facebook redirects back to Spotify with a **code** in the URL. Not a token. A code. Short-lived. One-time use. Step 7: Spotify's server exchanges the code for a token. This happens server-to-server. The code goes to Facebook. Facebook returns an access token. Step 8: Spotify stores the token. Uses it to call Facebook's API. Gets the user's friends. Done. The user's password never touched Spotify. Ever.

Why the code exchange? Why not return the token directly? Security. If Facebook redirected with the token in the URL, it could leak—browser history, referrer headers, logs. The code is useless to an attacker. Only Spotify's server, with its client secret, can exchange it for a token. Extra step. Extra safety.

---

## Let's Walk Through the Diagram

```
    OAUTH 2.0 - AUTHORIZATION CODE FLOW

    ┌──────┐                    ┌──────────┐                 ┌───────────┐
    │ User │                    │ Spotify  │                  │ Facebook  │
    │(You) │                    │ (Client) │                  │ (Auth +    │
    └──┬───┘                    └────┬─────┘                  │  Resource) │
       │                             │                         └─────┬─────┘
       │  1. "Login with Facebook"   │                               │
       │ ─────────────────────────► │                               │
       │                             │  2. Redirect to Facebook       │
       │                             │ ─────────────────────────────►│
       │                             │                               │
       │  3. User logs in + grants permission                        │
       │ ◄──────────────────────────────────────────────────────────│
       │                             │                               │
       │  4. Redirect with CODE (not token!)                         │
       │ ─────────────────────────► │                               │
       │                             │  5. Exchange code for token   │
       │                             │  (server-to-server, with       │
       │                             │   client secret)              │
       │                             │ ─────────────────────────────►│
       │                             │  6. Access token              │
       │                             │ ◄─────────────────────────────│
       │  7. Logged in!              │                               │
       │ ◄───────────────────────────│                               │
       │                             │  8. API calls with token      │
       │                             │ ─────────────────────────────►│
       │                             │     (limited data only)        │
       │                             │                               │

    Password NEVER leaves Facebook. Token has LIMITED scope.
```

---

## Real-World Examples (2-3)

**Example 1: "Login with Google."** You click it on a new app. You go to Google. You log in. Google asks: "This app wants your email and profile picture. Allow?" You allow. Google gives the app a token. The app knows who you are. It never saw your password. OAuth.

**Example 2: Slack integrations.** You add a Google Drive integration to Slack. Slack says: "We need access to your Drive to show files." You authorize. Google gives Slack a token. Slack can list files. Share links. It can't delete your Drive. Scoped. Limited.

**Example 3: Banking aggregators.** Apps that show all your accounts in one place. They use OAuth with each bank. You never give the aggregator your bank password. You authorize at each bank. The aggregator gets tokens. Read-only access. Your passwords stay at the banks. OAuth enables this safely.

---

## Let's Think Together

Why doesn't the app just ask for your Facebook password directly? What's wrong with that?

If Spotify had your password, it could do anything. Post statuses. Message people. Change your password. Delete your account. You'd have to trust Spotify completely—and every employee, every bug, every hacker who compromises them. One breach = your Facebook is gone. With OAuth, Spotify gets a token. Limited scope. You chose "friends list" only. They can't do more. If the token leaks, you revoke it at Facebook. Your password is unchanged. You never gave it away. OAuth = minimum necessary access. Password sharing = giving away the keys to the kingdom. Never do it.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup builds "Login with Google." They use the Implicit flow—Google returns the token directly in the URL fragment. Simple. Fast. No server needed. But the token is in the URL. It gets logged. It gets cached. It appears in browser history. A shared computer. A proxy. Token leaks. Now an attacker has access to the user's Google data—until the token expires. The fix? Use Authorization Code flow. Exchange code for token on the server. Token never hits the browser. Implicit flow is deprecated for this reason. Convenience cost users their data. OAuth has secure flows. Use them.

---

## Surprising Truth / Fun Fact

OAuth 2.0 is an authorization protocol—not authentication. It answers "can this app access my data?" It doesn't answer "who is this user?" OpenID Connect (OIDC) adds authentication on top of OAuth. It adds an ID token—a JWT with user identity. "Login with Google" often uses OAuth + OIDC together. OAuth = authorization. OIDC = authentication. They're different. Many people say "OAuth" when they mean both. Now you know the difference.

---

## Quick Recap (5 bullets)

- **OAuth 2.0** = delegated access. Give apps LIMITED tokens. Never your password.
- **Roles**: Resource Owner (you), Client (app), Authorization Server, Resource Server.
- **Authorization Code flow**: Redirect to auth server → user grants → code returned → exchange for token (server-side).
- **Why code not token in redirect?** Security. Code is one-time, short-lived. Token exchange happens server-to-server.
- **Scopes** define what the token can do. "Read friends." "Post on behalf." Minimum necessary access.

---

## One-Liner to Remember

**OAuth: Give the valet the car key, not the house key. Limited access. No password sharing.**

---

## Next Video

Sessions or tokens? When do you use which? Next: **Session vs Token—when to use each**. Two restaurants. Two strategies. Stay tuned.
