# Landing

Two static pages, no script, no build step, no dependency.

```
index.html        the home page
olanas.html       Tenure on Olanas: the valuation API as a service agents pay for per request
assets/site.css   the stylesheet both pages share
assets/motion.css the icons, the animations and the screen switcher, all CSS
assets/shots/     real captures of the app, copied to docs-site/public/shots
make-icons.py     the icon set: an inline sprite in each page, one file per icon for the docs
assets/           logo, favicon, share image
dev_server.py     local preview, standard library only
server.py         the container entry point: same handler, every interface, security headers
read_waitlist.py  reads the list collected before the signup form was removed
Dockerfile        four lines; nothing to install
```

## Local preview

```bash
python dev_server.py
```

Then open http://127.0.0.1:8410 and http://127.0.0.1:8410/olanas. The server answers those two
pages and `/assets/`, nothing else: it sits next to source.

## The four sites

Tenure lives on four domains, and every one links to the other three from its header or footer:

| Site | Where |
|---|---|
| Home, this folder | `landing-production-abe1.up.railway.app` |
| App | `app-production-7810.up.railway.app` |
| Docs | `docs-production-3405.up.railway.app` |
| Valuation API | `api-production-9e87.up.railway.app` |

When a real domain replaces any of them, search the repository for the old one: the headers,
footers, the docs config and the `og:` tags all carry it.

## Content security

`server.py` sends `script-src 'none'` and no `'unsafe-inline'` for styles, so a `<script>` or a
`style="…"` attribute added to either page simply does not run. `check.sh` fails if one is added.

## Before publishing

- Re-read the Status section on every change: what is live, what is next, the audit.
- The `og:image` share image is absolute and points at the current Railway subdomain.
