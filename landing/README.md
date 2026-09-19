# Landing page and waitlist

A static page plus a signup endpoint. No dependency, no build step.

```
index.html          the page, CSS and JS included
assets/             logo, favicon, share image
api/waitlist.py     the POST /api/waitlist endpoint
dev_server.py       local preview, standard library only
server.py           the container entry point: same handler, bound to every interface
read_waitlist.py    prints the list, de-duplicated, from whatever is piped into it
Dockerfile          four lines; nothing to install
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

Two options, and **without one of them the endpoint answers 503** rather than accepting an address
it cannot keep.

- **A file on a mounted volume.** Set `WAITLIST_DATA_DIR` to the mount point and `WAITLIST_FILE` to
  a path inside it. No third party ever sees the addresses. The server refuses to start if the file
  is outside the declared mount, because a container's filesystem is replaced on every deploy and a
  page that collects onto it looks like it works while losing everything.
- **A webhook.** `WAITLIST_WEBHOOK_URL` receives `{"email", "role", "source", "ts"}` as JSON. A
  Discord webhook URL is detected and gets a message shaped for it, with the email stripped of
  anything that could render as a link. Google Sheets, Make, n8n or your own API work unchanged.
  This gives you a push notification and hands the addresses to whoever runs that endpoint.

The webhook wins when both are set. `docs/DEPLOY.md` has the deployment details, including how to
read the list over `railway ssh` without opening any route on the public page.

Guards in place: email validated on the page and on the server, a honeypot field for bots, the
request body capped and a negative `Content-Length` refused, roles and sources restricted to a list,
the same answer whether or not an address was already on the list so the endpoint is not a membership
oracle, and no redirects followed on the outbound webhook.

## Deploying

See [`../docs/DEPLOY.md`](../docs/DEPLOY.md). The service runs from its `Dockerfile` and binds every
interface when the platform hands it a `PORT`.

`api/waitlist.py` keeps the shape of a Vercel Python function, so the folder also deploys there with
no framework and no build command: `index.html` at the root, `api/waitlist.py` at `/api/waitlist`.
The volume option does not exist on Vercel, so that route needs the webhook.

## Before publishing

- "Tenure" is a working name. Check the trademark and the domain.
- Re-read the claims in the Status section on every change: number of tests, audit, deployment.
- The `og:image` share image is absolute and points at the current Railway subdomain. It has to be
  updated the day a real domain is pointed at the service, or link previews break.
- Emails are personal data. The footer promises a single use and deletion on request: honour that,
  and provide a contact address.
