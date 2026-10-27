# eclipse-social-core

**What this is:** the MCP server for **Eclipse Social Core** — the
shared core of Cyan Eclipse Technologies' Eclipse social adapter
family. One canonical, versioned, hash-bound content package;
per-adapter native variants with classified adaptation diffs;
hash-bound owner approvals that any change invalidates; a per-account
capability mode registry with downgrade-on-probe-failure semantics;
per-adapter/account/family kill switches; and the engagement policy
module (the house engagement playbook as data).

**What this is not:** it performs **no platform action** — no posting,
no liking, no commenting, no network call, and it holds no credential
material. Adapters execute (or hand the owner a prep pack) elsewhere,
only in their sanctioned mode.

## Run it

```console
$ pip install eclipse-social-core
$ eclipse-social-core        # MCP over stdio, Python stdlib only
```

MCP client config:

```json
{ "mcpServers": { "eclipse-social-core": { "command": "uvx", "args": ["eclipse-social-core"] } } }
```

## Tools (15)

`account_set` · `account_inventory` · `content_ingest` · `content_get` ·
`adapt_preview` · `adaptation_diff` · `variant_revise` · `approval_pack` ·
`approve_variant` · `approval_check` · `policy_check` · `engagement_log` ·
`engagement_report` · `adapter_kill_switch` · `receipt_list`

## Honest scope

- **Governance only (phase S0).** Hash law: an approval binds the exact
  canonical hash and the exact variant hash — any later change to
  media, copy, links, order, disclosure, schedule, or destination
  changes the variant hash and invalidates that variant's approval.
- Every ingest, adaptation, approval, revision, policy check (ALLOW
  and DENY alike), kill-switch change, and probe-driven downgrade
  appends a hash-chained receipt — append-only, verifiable.
- State persists in `data/state.json` beside the server (override with
  `ECLIPSE_SOCIAL_CORE_STATE`).
- Certified (local) by the Eclipse Test Bench at v0.1.0; the listing
  status in the Eclipse Bazaar catalog is in-development.

Powered by Cyan Eclipse Technologies LLC (cetech.ai) — a Veteran-Owned
Small Business. MIT licensed.
