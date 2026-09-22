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
git archive HEAD lp-api landing app docs-site | tar -x -C /tmp/deploy
cd /tmp/deploy/lp-api && railway up --service api --detach
cd /tmp/deploy/app && railway up --service app --detach   # the app: static, no variables
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

`LPVAL_RPC` takes a whitespace-separated list of endpoints, tried in order, each optionally carrying
headers for providers that want the key there rather than in the path:

```
LPVAL_RPC="https://archive.example/v2/KEY  https://pool.example|x-api-key:KEY  https://public.example"
```

Put the most reliable archive node first: the fee rate behind every quote is then measured over the
window the caller asked for, from the very first request, instead of over the eight minutes a
pruning node keeps. The others are what it falls back to when the first is rate-limited, refusing
the key, or simply down — a failover that lands in well under a second.

**Every key is a secret, wherever the provider puts it.** These belong in the service's variables
and nowhere else. The client strips all of them out of error text before it reaches a caller, since
a failed probe reports its reason on a public route, and logs hostnames only.

`PORT` is provided by the platform and the server binds every interface when it sees it. Locally it
stays on loopback.

## 2. The landing page

A second service from the same repository with **root directory `landing`**. Two static pages, the
home page and `/olanas`, served by `server.py` with a strict content security policy: no script at
all, no inline style, nothing framed. No variables to set.

The landing used to collect waitlist signups onto a volume. That form is gone, and the endpoint
with it. Anything collected before it closed is still on `landing-volume`, untouched: registering
an SSH key once (from an interactive terminal if the key has a passphrase) lets you download it.

```bash
railway ssh keys add
railway volume files -v landing-volume download /waitlist.jsonl ./waitlist.jsonl
python3 landing/read_waitlist.py < waitlist.jsonl
```

Keep the file out of this repository: those are other people's addresses. Once it is read, the
volume and the two `WAITLIST_*` variables can be deleted from the service.

## What is live now

| Service | URL |
|---|---|
| API | `https://api-production-9e87.up.railway.app` — try `/health`, or `/v1/position/2908278/quote` |
| Landing | `https://landing-production-abe1.up.railway.app` |
| Docs | `https://docs-production-3405.up.railway.app` — built from `docs-site/` inside its Dockerfile |
| App | `https://app-production-7810.up.railway.app` — Robinhood Chain and testnet; listing waits on a deployed vault |

All four are generated Railway subdomains and will change the day a real domain is pointed at them.

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
