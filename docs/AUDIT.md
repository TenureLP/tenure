# Audit round, 19 September 2026

Three reviews were run against the repository at commit `40f8c27`: an adversarial read of the
contracts, a security review of the two Python services, and a scalability and resilience
assessment of the API. What follows is what they found, what was fixed, and what was deliberately
left alone. Nothing here replaces an independent audit before a deployment.

## Fixed

### Contracts

| Severity | Finding | Fix |
|---|---|---|
| High | `_paused()` copied the callee's whole returndata before checking its length. A token answering with megabytes made every entry point of an active deal exceed the block gas limit, stranding the position and the escrowed rent forever, with no owner and no upgrade path to recover them. | The probe is an assembly `staticcall` under a 30,000 gas stipend that copies at most one word. A regression test funds a deal against a token returning 100,000 words and settles it under a 400,000 gas budget. |
| High | An open freeze was extrapolated indefinitely. One permissionless `checkpointFreeze` during a one-second halt stopped the rent for the rest of the term, costing the financier most of their yield. | A freeze counts only up to `MAX_FREEZE_GAP` (6 hours) past the last time it was actually observed. Both sides can keep the record honest cheaply; neither can let it drift their way. |
| Medium | A position could drift out of range between listing and funding. | `fund()` re-runs the in-range test. This also makes spot-tick manipulation uneconomic: it must now hold across two transactions whose timing the attacker does not control. The allowlist and pause checks that used to sit here went away with the registry. |
| Medium | The freeze probe was guessed. A token answering `paused()` in any other shape was silently read as "not frozen", which is the exact inversion of the design intent. | The probe is declared in the deal terms. With one declared present, an answer in the wrong shape is read as frozen rather than ignored. |
| Low | `feeRecipient` was read live at funding while the contract claimed every registry input was snapshotted at listing. | Snapshotted into the deal, and later removed outright along with the fee. |
| Low | `transferFinancierPosition` accepted the vault itself, after which nobody could call `release`. | Rejected. |
| Low | `checkpointFreeze` was the only state-writing function without the reentrancy guard. | Added. |
| Low | `leaseEnd` and `graceEnd` returned 1970 timestamps for unfunded deals. | They return 0. |
| Informational | A listing with zero rent or a zero buyback price was accepted. That is not a lease. | Rejected. |

### Services

| Severity | Finding | Fix |
|---|---|---|
| Critical | The payment proof was a bearer token. A transaction hash is public once mined, so anyone watching the chain could redeem a customer's payment first, and any unrelated transfer reaching the address was a free request. | The payer signs a message naming the transaction, the route and a server-issued nonce. The proof counts only if the recovered signer is the account that sent the funds. secp256k1 recovery is implemented in the repo, so the service keeps zero dependencies. |
| High | Zero confirmation depth: a receipt in the head block was accepted, and the transaction could then be reorged away. | Three confirmations, configurable. |
| High | The freshness check was skipped entirely when `eth_blockNumber` failed, so a years-old transfer became valid whenever the node faltered. | Fails closed. |
| High | A non-object JSON proof crashed the handler thread with no response at all. | Every field is type-checked; the whole block is wrapped. |
| High | A negative `Content-Length` made the waitlist read until the client closed the socket. Two gigabytes were streamed into it in three seconds. | The length is validated before the read. |
| High | The dev server served the signup file and its own source. | The signup file moved outside the served directory; only the page and its assets are servable. |
| Medium | Every upstream failure reached the user as "position not found", measured at 7.5 % of requests with no load at all. | A reverted call and an unreachable chain are now different outcomes; the second returns 502. Reads retry with backoff, and the batch fallback no longer fans one failed request into N. |
| Medium | Twenty people opening the same position produced twenty identical valuations. | One in flight per position; the rest wait for it. |
| Medium | The response cache was unbounded and keyed on a float the caller chose, so a one-line loop forced a permanent miss rate and unbounded memory. | Bounded LRU, quantised key. |
| Medium | A payment was consumed before the work, so any failure afterwards burned it with nothing delivered. | Released on failure. |
| Medium | The waitlist answered whether an address was already on the list. | The same answer either way. |
| Medium | An email could close a code span and render as a link in the team's chat. | Stripped. |
| Medium | Malformed RPC responses crashed verification in four distinct ways. | Each field is validated. |
| Low | No CORS preflight, so the paywall could never have been used from a browser. | `OPTIONS` and the exposed headers. |
| Low | Unbounded threads, no socket timeout, unescaped access logs, plain HTTP accepted for the RPC, spent payments unprunable. | Concurrency limit shedding with 503, HTTP/1.1 with a timeout, escaped logs, `https` enforced, a timestamp column and an hourly prune. |

## Deliberately not fixed

- **The seller can fund their own listing from a second address.** Unavoidable on chain. The spec previously implied more than the code delivers, and has been reworded.
- **A token that starves the freeze probe of gas is read as not frozen.** It no longer bricks anything, which was the severe half. Reading a failed probe as frozen would break every pool containing a token that simply has no freeze switch.
- **Spot-tick admission is not a TWAP.** Re-checking at funding raises the cost enough for now; a real measurement on a shallow pool is still owed.
- **Fees earned during the grace window** go to whoever takes delivery. Consistent with the lease being over, now documented.
- **`http.server` in production.** Fine for a prototype. The recommendation on the table is a WSGI adapter behind waitress, which would be the project's first dependency, and only at the socket layer.
- **Cache staleness of three seconds against 100 ms blocks.** Three orders of magnitude below the pricing noise of a 20 % haircut.

## Still owed before any deployment

An independent audit. A fork test of the manipulation cost on a real shallow pool. A decision on the serving layer. Multiple RPC endpoints with failover. And a note that USDG sits behind an upgradeable proxy and exposes `paused()`: if its issuer ever pauses it, rent stops accruing on every deal at once and no USDG moves until it resumes.
