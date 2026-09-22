# Documentation site

The public documentation, built with [VitePress](https://vitepress.dev) from the Markdown in this
folder. Node is needed to build it and for nothing else; the built site is served by `server.py`,
Python standard library only, like every other server in this repository.

```bash
npm ci
npm run dev        # live preview on 127.0.0.1:8430
npm run build      # static site in .vitepress/dist
python3 server.py  # serves the build, with the same headers as production
```

Deployed like the other services: stage a clean copy with `git archive` and `railway up` from it.
See [`../docs/DEPLOY.md`](../docs/DEPLOY.md).

When a figure changes in the contracts, the API or the app, the page describing it changes in the
same commit.
