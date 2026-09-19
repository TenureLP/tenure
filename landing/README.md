# Landing page and waitlist

A static page plus a signup endpoint. No dependency, no build step.

```
index.html          the page, CSS and JS included
assets/             logo, favicon, share image
api/waitlist.py     the POST /api/waitlist endpoint (a Vercel Python function)
dev_server.py       local preview, standard library only
```

## Local preview

```bash
python dev_server.py
```

Then open http://127.0.0.1:8410. Locally, signups are appended to `../.waitlist/waitlist.jsonl`, one
JSON object per line. That path is deliberately outside the directory the dev server hands out, and
the server only serves the page and its assets, because it sits next to source and local state.

Duplicates are removed when the list is read, not on the way in: re-reading the whole file on every
signup is linear in its size, and the check-then-append it would need races between concurrent
requests anyway.

## Where signups go in production

The endpoint reads `WAITLIST_WEBHOOK_URL` and POSTs each signup there as JSON.

- **A Discord webhook.** The quickest route: in a private channel, Settings, Integrations, Webhooks,
  copy the URL. Each signup arrives as a message. The URL is detected and the message is shaped for
  Discord, with the email stripped of anything that could render as a link.
- **Google Sheets, Make, Zapier or your own API.** Any other URL receives
  `{"email", "role", "source", "ts"}`.

Without that variable, a Vercel deployment answers 503 rather than dropping signups silently.

Guards in place: email validated on the page and on the server, a honeypot field for bots, the
request body capped and a negative `Content-Length` refused, roles and sources restricted to a list,
the same answer whether or not an address was already on the list so the endpoint is not a membership
oracle, and no redirects followed on the outbound webhook.

## Deploying to Vercel

1. Create a Vercel project whose root is this `landing` folder. No framework, no build command.
2. Add the `WAITLIST_WEBHOOK_URL` environment variable.
3. Deploy. `index.html` is served at the root and `api/waitlist.py` becomes `/api/waitlist`.

## Before publishing

- "Tenure" is a working name. Check the trademark and the domain.
- Re-read the claims in the Status section on every change: number of tests, audit, deployment.
- The `og:image` share image must be an absolute URL once the domain is known.
- Emails are personal data. The footer promises a single use and deletion on request: honour that,
  and provide a contact address.
