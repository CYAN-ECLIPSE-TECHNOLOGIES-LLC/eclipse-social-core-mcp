# Eclipse Social Core MCP

**Powered by Cyan Eclipse Technologies** — https://cetech.ai

**The shared core of the Eclipse social adapter family — one canonical, owner-approved content package becomes a native draft, scheduled post, live post, or prep pack on each platform, according to what that platform actually sanctions. Analytics return with their platform definitions intact. It never uses a session workaround, never automates around a platform gate, and never publishes an unapproved variant.**

## Why this exists

Social platforms are separate publishing systems with separate accounts, media rules, API permissions, metrics, link behavior, and enforcement risk. A generic "post everywhere" abstraction that hides those differences produces broken crops, dead links, false analytics, and account jeopardy. The core holds the things every adapter must agree on — canonical content, rights, claims, approval, adaptation diffs, receipts, account safety — so each adapter only has to tell the truth about one platform. Spec: `~/workspace/cyan-eclipse/eclipse-social-family-spec-20261025.md` (§3–§7).

## Status — honest labels

v0.1.0, phase **S0 core**. **Governance only: this server performs no platform action and makes no network calls.** It holds packages, computes variants + diffs, records hash-bound approvals, evaluates engagement policy, and receipts everything. Adapters execute — or hand the owner a prep pack — elsewhere, only in their sanctioned mode. Local stdio, Python stdlib only, synthetic fixture package. **No certification claimed — bench pending.**

## The hash law

An approval binds hashes, not vibes (§3.1). Ingest issues a SHA-256 **content hash** over the canonical object; every variant gets a **variant hash** over its media, copy, link, order, disclosures, schedule, and destination. `approve_variant` records both hashes; `approval_check` recomputes them from current fields. **Any change — copy, schedule, destination, link, disclosure — changes the hash and invalidates the approval**; the variant returns to review. Proven three ways in the test suite, including a direct field-tamper case.

## Tools (15)

| Tool | What it does |
|---|---|
| `account_set` | Register/update an authorized account: declared capability modes (capability → mode) + latest capability probe. A **failed probe downgrades effective modes automatically** — publish/draft collapse to `PREP_PACK`, own-engagement to `COMMUNITY_PREP`, reads stay flagged. Evaluation only; no credentials exist in this system. |
| `account_inventory` | All accounts with declared + effective mode matrices, last probe, kill-switch state. |
| `content_ingest` | Accept a canonical content object (§3.1): masters + provenance, copy, claims **with sources**, rights per asset, accessibility assets, disclosure record, intended/prohibited surfaces, schedule. Missing rights, unsourced claims, or missing alt text are **named blockers**. Re-ingesting changed content bumps the version. |
| `content_get` | One canonical record in full. |
| `adapt_preview` | Build one native variant for an adapter profile (`aperture_feed`, `aperture_reel`, `aperture_story`, `prism_shorts`, `zephyr`, `wire`): geometry, copy under the surface's limit, the surface's working link placement, platform-required disclosure labels, element order — plus the classified diff. |
| `adaptation_diff` | The classified diff for a variant (`MEDIA_CROP`, `TEXT_REWRITE`, `LINK_PLACEMENT`, `ORDER`, `DISCLOSURE`, `METADATA`, `FORMAT_OMISSION`, …). A rewrite that drops a canonical number/claim is flagged **substantive** — never silent. |
| `variant_revise` | Revise a variant; the hash recomputes and any approval bound to the old hash is invalidated. |
| `approval_pack` | The review artifact: canonical item + variants + diffs + destinations + schedule. |
| `approve_variant` / `approval_check` | Record / verify a hash-bound owner approval. |
| `policy_check` | **The engagement playbook as an evaluator** (§5). Actions: `like`, `comment`, `report_stop`, `reset`. Enforces week-1 caps (**≤15 likes, ≤5 comments/day**), week-2+ caps (≤30/≤10), ≤2 likes per target per day, no links / no self-promo / no hashtag stuffing / ≤1 emoji in comments, no duplicate comments, and stop-signal finality (an action block stops the session until an owner reset). **Every check is receipted, ALLOW and DENY alike.** |
| `engagement_log` / `engagement_report` | Append-only log of executed/owner-completed actions + the daily-report view (totals vs caps). No action goes unreported. |
| `adapter_kill_switch` | Disable family / one adapter / one account. Writes freeze first; drafts and receipts remain readable. |
| `receipt_list` | The hash-chained receipt ledger, with chain verification. |

## Modes (§2.1)

`PUBLISH_API` · `DRAFT_API` · `PREP_PACK` · `READ_API` · `OWN_ENGAGEMENT_API` · `COMMUNITY_PREP` · `COMMUNITY_API_PILOT`. No mode includes browser-session scripting, cookie reuse, proxies, or password collection — ever (§7). Community engagement defaults to `COMMUNITY_PREP` for every adapter at launch.

## Run it

```bash
python3 server.py            # MCP over stdio, stdlib only, no dependencies
python3 smoke.py             # end-to-end smoke over real stdio (temp state)
python3 -m unittest discover tests   # 26 tests
```

State persists in `data/state.json` beside the server (override with `ECLIPSE_SOCIAL_CORE_STATE`). `data/` is gitignored.

### Fixtures

`fixtures/sample_content.json` — one synthetic White-Report-style episode package (9:16 reel master + cover, a sourced claim, owned rights, alt text, AI-media disclosure) that the tests and smoke drive end to end.

## Roadmap (per spec §21)

- **S1** — Prism product face over Eclipse Connect rails.
- **S2** — Zephyr (built alongside this core) + Commons.
- **S3/S4** — Wire, Meridian, Pulse, Comet, Atlas by gate state. Each phase starts from a dated terms/capability record; a phase never inherits another adapter's verdict.

## License / attribution

A Cyan Eclipse Technologies product. The "Powered by Cyan Eclipse Technologies" attribution travels with it.
