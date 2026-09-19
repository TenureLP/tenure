# Deploying

Two services, both from this repository, both Python with no dependencies to install. Railway is the
fit here because the API is a long-running process that needs a disk: the paywall's ledger of spent
payments has to survive a restart, or a payment already redeemed could be redeemed again.

Each service has its own `Dockerfile`: four lines, a base image and a copy. It is there so the build
does not depend on a platform correctly guessing the language, the entrypoint and the Python
version. When that guessing was left on, the platform reported a different builder than the one
configured and neither the start command nor the health check survived.

## Pushing from the command line

`railway up` uploads the directory you run it from. **Do not run it from a Windows drive mounted
into WSL.** The archive it builds from `/mnt/c` carries mode 0777 on every entry and the builder
rejects it: the deployment fails within twenty seconds, at scheduling, with no build output at all
to explain itself. The identical tree deploys in twenty seconds from the Linux filesystem.

Stage a clean copy of exactly what is committed, and deploy that:

```bash
rm -rf /tmp/deploy && mkdir -p /tmp/deploy
git archive HEAD lp-api landing | tar -x -C /tmp/deploy
cd /tmp/deploy/lp-api && railway up --service api --detach
```

Linking is per directory, so a staged copy needs
`railway link --project <id> --environment production --service <name>` once.

## 1. The valuation API

Create a service from this repository with **root directory `lp-api`**. `railway.json` sets the
health check on `/health` and the restart policy; the `Dockerfile` sets the start command.

**Attach a volume.** Mount it anywhere, for example `/data`. Then set:

| Variable | Value | Why |
|---|---|---|
| `LPVAL_DATA_DIR` | `/data` | the mount point, used to prove the ledger is durable |
| `LPVAL_DB` | `/data/payments.sqlite` | spent payments |
| `LPVAL_SNAP_DB` | `/data/snapshots.sqlite` | fee-growth history |

Those three are required before the paywall can be turned on. The service refuses to start with a
paywall whose ledger sits on an ephemeral filesystem, rather than quietly letting one payment be
spent twice after a redeploy.

To charge for requests, add:

| Variable | Value |
|---|---|
| `LPVAL_PAY_TO` | the address that receives payments |
| `LPVAL_PRICE_WEI` | price per request, e.g. `1000000000000` |
| `LPVAL_NONCE_KEY` | any long random string, so challenges survive a restart |

Leave `LPVAL_PAY_TO` unset to run the API free, which is the sensible way to start.

`PORT` is provided by the platform and the server binds every interface when it sees it. Locally it
stays on loopback.

## 2. The landing page

A second service from the same repository with **root directory `landing`**. One variable:

| Variable | Value |
|---|---|
| `WAITLIST_WEBHOOK_URL` | where signups are POSTed |

A Discord webhook is the quickest: in a private channel, Settings, Integrations, Webhooks, copy the
URL. Any other URL receives `{"email", "role", "source", "ts"}`.

**Without that variable the signup form answers 503.** That is deliberate: the endpoint refuses to
accept an address it cannot deliver, rather than dropping it silently. Set it before sharing the
link.

`WAITLIST_FILE` is the local-development path and has to name a file explicitly. It is not a
substitute for the webhook here: a container's filesystem is replaced on every deploy, so a file
written inside one is a signup collected and then lost. The server prints where signups go on the
line it logs at boot, so a misconfigured deployment is visible without having to sign up to find
out.

## What is live now

| Service | URL |
|---|---|
| API | `https://api-production-9e87.up.railway.app` — try `/health`, or `/v1/position/2908278/quote` |
| Landing | `https://landing-production-abe1.up.railway.app` |

Both are generated Railway subdomains and will change the day a real domain is pointed at them.

## 3. Afterwards

Point a domain at each service, then update two things that hardcode a URL: the `og:image` meta tag
in `landing/index.html`, which must be absolute for link previews to render, and `LPVAL_RPC` if you
ever move off the public node.

## What is not covered here

The contracts are not deployed anywhere. `lease-vault/README.md` has the command, and
`lease-vault/verify-addresses.sh` should be run first: a young chain redeploys its infrastructure,
and a stale address in a deploy script is a silent way to lose a transaction.

The API serves with `http.server`, hardened but still not a production server: bounded concurrency,
socket timeouts, HTTP/1.1 and load shedding are in place, a real thread pool is not. It is sized for
a prototype behind a platform proxy, not for volume.
