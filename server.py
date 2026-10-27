#!/usr/bin/env python3
# Eclipse Social Core MCP
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai

"""Eclipse Social Core MCP — v0.1.0, phase S0 (shared core).

Powered by Cyan Eclipse Technologies (cetech.ai).

The shared core of the Eclipse social adapter family (spec
eclipse-social-family-spec-20261025.md): one canonical, versioned,
hash-bound content package; per-adapter native variants with
classified adaptation diffs; hash-bound owner approvals that ANY
change invalidates; a per-account capability mode registry with
downgrade-on-probe-failure semantics; per-adapter/account/family kill
switches; and the engagement policy module — the house engagement
playbook (~/workspace/white-report/engagement-playbook.md) as data.

S0 SCOPE — GOVERNANCE ONLY. This server performs NO platform action:
no posting, no liking, no commenting, no network call. It holds
packages, computes variants + diffs, records approvals, evaluates
engagement policy, and receipts everything. Adapters execute (or hand
the owner a prep pack) elsewhere, only in their sanctioned mode.

HASH LAW (spec SS3.1): an approval binds the exact canonical hash and
the exact variant hash. Any later change to media, copy, links,
order, disclosure, schedule, or destination changes the variant hash
and invalidates that variant's approval.

Receipts: every ingest, adaptation, approval, revision, policy check
(ALLOW and DENY alike), kill-switch change, and probe-driven
downgrade appends a hash-chained receipt — append-only, verifiable.

Transport: MCP over stdio (newline-delimited JSON-RPC 2.0), stdlib only.
State file: $ECLIPSE_SOCIAL_CORE_STATE or ./data/state.json beside here.
"""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

STATE_PATH = Path(os.environ.get(
    "ECLIPSE_SOCIAL_CORE_STATE",
    Path(__file__).parent / "data" / "state.json"))

MODES = ("PUBLISH_API", "DRAFT_API", "PREP_PACK", "READ_API",
         "OWN_ENGAGEMENT_API", "COMMUNITY_PREP", "COMMUNITY_API_PILOT")

# Downgrade-on-probe-failure (spec SS3.2 tool 13): a failed capability
# probe downgrades the adapter automatically; it never triggers a
# workaround. Write modes collapse to prep; community pilot collapses
# to prep; reads stay readable but are flagged unverified.
DOWNGRADE = {"PUBLISH_API": "PREP_PACK", "DRAFT_API": "PREP_PACK",
             "OWN_ENGAGEMENT_API": "COMMUNITY_PREP",
             "COMMUNITY_API_PILOT": "COMMUNITY_PREP",
             "READ_API": "READ_API", "PREP_PACK": "PREP_PACK",
             "COMMUNITY_PREP": "COMMUNITY_PREP"}

DIFF_CATEGORIES = ("MEDIA_CROP", "MEDIA_DURATION", "TEXT_REWRITE",
                   "METADATA", "LINK_PLACEMENT", "ORDER", "INTERACTIVE",
                   "DISCLOSURE", "RIGHTS_LIMIT", "FORMAT_OMISSION")

# Per-adapter adaptation profiles (v0.1: the surfaces S0 needs plus the
# family's documented link/geometry truths from the spec chapters).
# char_limit applies to the variant's primary copy text.
PROFILES = {
    "aperture_feed": {"platform": "instagram", "surface": "feed",
                      "aspect": "4:5", "char_limit": 2200,
                      "links_clickable": False,
                      "link_placement": "profile_link",
                      "requires_ai_label": True},
    "aperture_reel": {"platform": "instagram", "surface": "reel",
                      "aspect": "9:16", "char_limit": 2200,
                      "links_clickable": False,
                      "link_placement": "profile_link",
                      "requires_ai_label": True},
    "aperture_story": {"platform": "instagram", "surface": "story",
                       "aspect": "9:16", "char_limit": 2200,
                       "links_clickable": True,
                       "link_placement": "story_link_sticker",
                       "requires_ai_label": True},
    "prism_shorts": {"platform": "youtube", "surface": "shorts",
                     "aspect": "9:16", "char_limit": 100,
                     "links_clickable": False,
                     "link_placement": "profile_and_longform",
                     "requires_ai_label": True},
    "zephyr": {"platform": "bluesky", "surface": "post",
               "aspect": None, "char_limit": 300,
               "links_clickable": True, "link_placement": "in_post",
               "requires_ai_label": False},
    "wire": {"platform": "x", "surface": "lead_post",
             "aspect": None, "char_limit": 280,
             "links_clickable": True,
             "link_placement": "first_self_reply",
             "requires_ai_label": False},
}

# Engagement playbook as data (playbook "Daily caps (hard)" + spec SS5.1).
PLAYBOOK = {
    "week1": {"likes_per_day": 15, "comments_per_day": 5,
              "sessions_per_day": 1},
    "week2plus": {"likes_per_day": 30, "comments_per_day": 10,
                  "sessions_per_day": 2},
    "likes_per_target_per_day": 2,
    "max_hashtags_in_comment": 2,
    "max_emoji_in_comment": 1,
    "stop_signals": ("action_block", "try_again_later", "checkpoint",
                     "unusual_activity", "signin_challenge",
                     "password_reentry"),
    "promo_phrases": ("check my page", "check out my", "dm me",
                      "link in bio", "follow me", "follow back"),
}

URL_RE = re.compile(r"(https?://|www\.)", re.IGNORECASE)
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")


class ToolError(Exception):
    pass


def now() -> int:
    return int(time.time())


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


# --------------------------------------------------------------------- state
def empty_state() -> dict:
    return {"accounts": {}, "contents": {}, "variants": {},
            "engagement": {"stopped": False, "stop_reason": None,
                           "comment_keys": [], "log": []},
            "kill": {"family": False, "adapters": {}, "accounts": {}},
            "receipts": []}


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return empty_state()


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=1))


# ------------------------------------------------------------------ receipts
def emit_receipt(state: dict, rtype: str, detail: dict) -> dict:
    """Append-only, hash-chained (house pattern)."""
    prev = state["receipts"][-1]["hash"] if state["receipts"] else "GENESIS"
    entry = {"seq": len(state["receipts"]) + 1, "ts": now(), "type": rtype,
             "prev_hash": prev, "detail": detail}
    entry["hash"] = sha(prev + canon({k: v for k, v in entry.items()
                                      if k != "hash"}))
    state["receipts"].append(entry)
    return entry


def verify_receipt_chain(receipts) -> bool:
    prev = "GENESIS"
    for e in receipts:
        if e.get("prev_hash") != prev:
            return False
        expect = sha(prev + canon({k: v for k, v in e.items() if k != "hash"}))
        if e.get("hash") != expect:
            return False
        prev = e["hash"]
    return True


# ------------------------------------------------------------------ accounts
def effective_modes(account: dict) -> dict:
    """Declared modes, downgraded if the last capability probe failed."""
    declared = account.get("declared_modes", {})
    probe = account.get("probe") or {}
    if probe.get("status") == "failed":
        return {cap: DOWNGRADE.get(mode, mode)
                for cap, mode in declared.items()}
    return dict(declared)


def t_account_set(state, args):
    """Register/update an account + its declared capability modes and
    latest capability probe. Evaluation only — no platform is contacted.
    A failed probe downgrades effective modes (see DOWNGRADE)."""
    account_id = str(args["account_id"])
    for cap, mode in (args.get("modes") or {}).items():
        if mode not in MODES:
            raise ToolError(f"unknown mode {mode!r} for capability {cap!r}; "
                            f"modes are {list(MODES)}")
    acct = state["accounts"].get(account_id, {"account_id": account_id})
    for k in ("platform", "adapter", "owner", "account_type", "role",
              "connection_state"):
        if k in args:
            acct[k] = args[k]
    if "modes" in args:
        acct["declared_modes"] = dict(args["modes"])
    if "probe" in args:
        acct["probe"] = args["probe"]
    acct["effective_modes"] = effective_modes(acct)
    acct["kill_switch"] = bool(state["kill"]["accounts"].get(account_id))
    state["accounts"][account_id] = acct
    downgraded = acct["effective_modes"] != acct.get("declared_modes", {})
    r = emit_receipt(state, "account_set",
                     {"account_id": account_id,
                      "probe_status": (acct.get("probe") or {}).get("status"),
                      "downgraded": downgraded})
    return {"account": acct, "downgraded": downgraded,
            "receipt_seq": r["seq"],
            "note": ("Probe failed: effective modes downgraded per SS3.2. "
                     "A downgrade never triggers a workaround."
                     if downgraded else
                     "Effective modes equal declared modes.")}


def t_account_inventory(state, args):
    out = []
    for aid, acct in sorted(state["accounts"].items()):
        a = dict(acct)
        a["effective_modes"] = effective_modes(a)
        a["kill_switch"] = bool(state["kill"]["accounts"].get(aid))
        out.append(a)
    return {"accounts": out, "count": len(out),
            "family_kill_switch": state["kill"]["family"],
            "note": "No credential values are held or returned (spec SS7)."}


# ------------------------------------------------------------------- content
CONTENT_FIELDS = ("canonical_id", "title", "body", "short_copy",
                  "long_copy", "cta", "canonical_url", "campaign",
                  "language", "territory", "release_window", "expiry",
                  "media", "claims", "rights", "accessibility",
                  "disclosures", "intended_surfaces",
                  "prohibited_surfaces", "schedule", "hashtags")


def content_hash(obj: dict) -> str:
    return sha(canon({k: obj.get(k) for k in CONTENT_FIELDS}))


def validate_content(obj: dict):
    """Named blockers, never silent acceptance (spec SS3.1/SS3.2)."""
    blockers = []
    if not (obj.get("title") or obj.get("body") or obj.get("short_copy")):
        blockers.append("content carries no title/body/short_copy")
    media = obj.get("media") or []
    rights = {r.get("asset_id") for r in obj.get("rights") or []}
    for m in media:
        if m.get("asset_id") not in rights:
            blockers.append(f"media asset {m.get('asset_id')!r} has no "
                            "rights record")
    for c in obj.get("claims") or []:
        if not c.get("source"):
            blockers.append(f"claim {c.get('text', '')[:40]!r}... has no "
                            "source — claims travel with their evidence")
    if obj.get("disclosures") is None:
        blockers.append("disclosure record missing (sponsorship / "
                        "affiliate / AI-media labels are variant fields, "
                        "not postscripts)")
    acc = obj.get("accessibility") or {}
    alt = acc.get("alt_text") or {}
    for m in media:
        if m.get("kind") in ("photo", "image", "graphic") \
                and m.get("asset_id") not in alt:
            blockers.append(f"image asset {m.get('asset_id')!r} has no "
                            "alt text — captions and alt text travel "
                            "with the asset")
    return blockers


def t_content_ingest(state, args):
    obj = args["content"]
    blockers = validate_content(obj)
    if blockers:
        raise ToolError("content_ingest blockers: " + "; ".join(blockers))
    cid = str(obj["canonical_id"])
    h = content_hash(obj)
    existing = state["contents"].get(cid)
    if existing and existing["content_hash"] == h:
        return {"canonical_id": cid, "version": existing["version"],
                "content_hash": h, "status": "unchanged",
                "note": "Identical content re-ingested; no new version."}
    version = (existing["version"] + 1) if existing else 1
    record = {k: obj.get(k) for k in CONTENT_FIELDS}
    record["version"] = version
    record["content_hash"] = h
    record["approval"] = None
    state["contents"][cid] = record
    r = emit_receipt(state, "content_ingest",
                     {"canonical_id": cid, "version": version,
                      "content_hash": h})
    return {"canonical_id": cid, "version": version, "content_hash": h,
            "status": "ingested", "receipt_seq": r["seq"]}


def t_content_get(state, args):
    rec = state["contents"].get(str(args["canonical_id"]))
    if not rec:
        raise ToolError(f"unknown canonical_id: {args['canonical_id']}")
    return rec


# ---------------------------------------------------------------- adaptation
HASHED_VARIANT_FIELDS = ("variant_id", "canonical_id", "canonical_hash",
                         "adapter", "surface", "destination_account",
                         "media", "copy_text", "link", "hashtags",
                         "disclosures_out", "order", "schedule", "mode")


def variant_hash(variant: dict) -> str:
    return sha(canon({k: variant.get(k) for k in HASHED_VARIANT_FIELDS}))


def _numbers(text: str):
    # Magnitude suffix counts only when attached ($635.6M), so a
    # following capitalized word is never eaten into the token.
    return re.findall(r"\$?\d[\d,\.]*%?(?:[KMB]\b)?", text or "")


def compute_diffs(content: dict, variant: dict):
    """Classify every difference from canonical (spec SS3.2 tool 4).
    Substantive = a number, claim, quotation, source, or CTA changed;
    substantive changes require explicit approval in the diff."""
    diffs = []
    prof_aspect = variant["media"][0]["aspect_out"] if variant["media"] \
        else None
    for m_c, m_v in zip(content.get("media") or [], variant["media"]):
        if m_v["aspect_out"] != m_c.get("aspect"):
            diffs.append({"category": "MEDIA_CROP",
                          "field": f"media:{m_c['asset_id']}",
                          "from": m_c.get("aspect"),
                          "to": m_v["aspect_out"], "substantive": False,
                          "note": "Geometry change only; claim/evidence "
                                  "must survive the crop (SS3.3)."})
        if m_v.get("duration_out") is not None \
                and m_c.get("duration") is not None \
                and m_v["duration_out"] != m_c["duration"]:
            diffs.append({"category": "MEDIA_DURATION",
                          "field": f"media:{m_c['asset_id']}",
                          "from": m_c["duration"],
                          "to": m_v["duration_out"], "substantive": False})
    canon_copy = content.get("short_copy") or content.get("body") or ""
    if variant["copy_text"] != canon_copy:
        lost = [n for n in _numbers(canon_copy)
                if n not in _numbers(variant["copy_text"])]
        diffs.append({"category": "TEXT_REWRITE", "field": "copy_text",
                      "from": canon_copy, "to": variant["copy_text"],
                      "substantive": bool(lost),
                      "note": ("Numbers/claims dropped by the rewrite: "
                               + ", ".join(lost) if lost else
                               "Rewrite preserves every number in the "
                               "canonical copy.")})
    canon_link = {"placement": "canonical_url", "url": content.get("canonical_url")}
    if variant["link"] != canon_link:
        diffs.append({"category": "LINK_PLACEMENT", "field": "link",
                      "from": canon_link, "to": variant["link"],
                      "substantive": False,
                      "note": "The variant states the working link path "
                              "for its surface (SS3.3); it never relies "
                              "on a link the surface does not make usable."})
    canon_order = ["media", "copy", "link"]
    if variant["order"] != canon_order:
        diffs.append({"category": "ORDER", "field": "order",
                      "from": canon_order, "to": variant["order"],
                      "substantive": False})
    if variant["disclosures_out"] != (content.get("disclosures") or {}):
        added = {k: v for k, v in variant["disclosures_out"].items()
                 if (content.get("disclosures") or {}).get(k) != v}
        diffs.append({"category": "DISCLOSURE", "field": "disclosures",
                      "from": content.get("disclosures") or {},
                      "to": variant["disclosures_out"],
                      "substantive": False,
                      "note": f"Platform-required labels added: {added}"})
    canon_tags = content.get("hashtags") or []
    if variant["hashtags"] != canon_tags:
        diffs.append({"category": "METADATA", "field": "hashtags",
                      "from": canon_tags, "to": variant["hashtags"],
                      "substantive": False})
    if content.get("cta") \
            and content["cta"] not in (variant["copy_text"] or ""):
        diffs.append({"category": "FORMAT_OMISSION", "field": "cta",
                      "from": content["cta"], "to": None,
                      "substantive": True,
                      "note": "CTA does not survive on this surface; "
                              "shown in the diff, never dropped silently."})
    return diffs


def build_variant(content: dict, adapter: str, account_id: str,
                  mode: str, schedule_override=None) -> dict:
    prof = PROFILES[adapter]
    copy_src = content.get("short_copy") or content.get("body") or ""
    copy_text = copy_src
    if prof["char_limit"] and len(copy_src) > prof["char_limit"]:
        copy_text = copy_src[:prof["char_limit"] - 1].rstrip() + "…"
    media = []
    for m in content.get("media") or []:
        media.append({"asset_id": m["asset_id"], "kind": m.get("kind"),
                      "aspect_out": prof["aspect"] or m.get("aspect"),
                      "duration_out": m.get("duration")})
    disclosures_out = dict(content.get("disclosures") or {})
    if prof["requires_ai_label"] and disclosures_out.get("ai_media"):
        disclosures_out["platform_ai_label"] = True
    order = ["media", "copy", "link"]
    if prof["link_placement"] == "first_self_reply":
        order = ["media", "copy", "link_in_first_self_reply"]
    variant = {
        "variant_id": f"{content['canonical_id']}::{adapter}",
        "canonical_id": content["canonical_id"],
        "canonical_hash": content["content_hash"],
        "adapter": adapter, "surface": prof["surface"],
        "destination_account": account_id,
        "media": media, "copy_text": copy_text,
        "link": {"placement": prof["link_placement"],
                 "url": content.get("canonical_url")},
        "hashtags": list(content.get("hashtags") or []),
        "disclosures_out": disclosures_out,
        "order": order,
        "schedule": schedule_override or content.get("schedule"),
        "mode": mode,
    }
    variant["diffs"] = compute_diffs(content, variant)
    variant["variant_hash"] = variant_hash(variant)
    variant["version"] = 1
    variant["approval"] = None
    return variant


def kill_blocked(state, adapter=None, account_id=None):
    if state["kill"]["family"]:
        return "family kill switch is ON"
    if adapter and state["kill"]["adapters"].get(adapter):
        return f"adapter kill switch is ON for {adapter}"
    if account_id and state["kill"]["accounts"].get(account_id):
        return f"account kill switch is ON for {account_id}"
    return None


def t_adapt_preview(state, args):
    cid = str(args["canonical_id"])
    content = state["contents"].get(cid)
    if not content:
        raise ToolError(f"unknown canonical_id: {cid}")
    adapter = str(args["adapter"])
    if adapter not in PROFILES:
        raise ToolError(f"unknown adapter profile: {adapter}; "
                        f"known: {sorted(PROFILES)}")
    account_id = str(args.get("account_id", ""))
    blocked = kill_blocked(state, adapter, account_id or None)
    if blocked:
        emit_receipt(state, "adapt_blocked",
                     {"canonical_id": cid, "adapter": adapter,
                      "reason": blocked})
        raise ToolError(f"adapt_preview blocked: {blocked}")
    if adapter in (content.get("prohibited_surfaces") or []):
        raise ToolError(f"{adapter} is a PROHIBITED surface for {cid}")
    acct = state["accounts"].get(account_id)
    mode = args.get("mode") or "PREP_PACK"
    if acct:
        eff = effective_modes(acct)
        declared = [m for m in eff.values()]
        if mode not in declared and declared:
            raise ToolError(
                f"mode {mode} is not in account {account_id}'s effective "
                f"mode matrix {eff} (probe status: "
                f"{(acct.get('probe') or {}).get('status')})")
    variant = build_variant(content, adapter, account_id, mode,
                            args.get("schedule"))
    state["variants"][variant["variant_id"]] = variant
    r = emit_receipt(state, "adapt_preview",
                     {"variant_id": variant["variant_id"],
                      "variant_hash": variant["variant_hash"],
                      "diffs": len(variant["diffs"])})
    return {"variant": variant, "receipt_seq": r["seq"]}


def t_adaptation_diff(state, args):
    v = state["variants"].get(str(args["variant_id"]))
    if not v:
        raise ToolError(f"unknown variant_id: {args['variant_id']}")
    content = state["contents"][v["canonical_id"]]
    diffs = compute_diffs(content, v)
    return {"variant_id": v["variant_id"], "variant_hash": v["variant_hash"],
            "diffs": diffs,
            "substantive_changes": [d for d in diffs if d["substantive"]],
            "note": "A number, claim, quotation, source, or CTA may not "
                    "change silently (SS3.2). Substantive diffs require "
                    "explicit approval in the pack."}


REVISE_FIELDS = ("copy_text", "hashtags", "schedule",
                 "destination_account", "link", "disclosures_out",
                 "order", "media")


def t_variant_revise(state, args):
    """Apply an owner-side revision to a variant. HASH LAW: any change
    recomputes the variant hash; an existing approval bound to the old
    hash is thereby invalidated and the variant returns to review."""
    vid = str(args["variant_id"])
    v = state["variants"].get(vid)
    if not v:
        raise ToolError(f"unknown variant_id: {vid}")
    changes = args.get("changes") or {}
    bad = [k for k in changes if k not in REVISE_FIELDS]
    if bad:
        raise ToolError(f"cannot revise fields: {bad}; "
                        f"revisable: {list(REVISE_FIELDS)}")
    old_hash = v["variant_hash"]
    for k, val in changes.items():
        v[k] = val
    content = state["contents"][v["canonical_id"]]
    v["diffs"] = compute_diffs(content, v)
    v["variant_hash"] = variant_hash(v)
    v["version"] += 1
    invalidated = bool(v.get("approval")) \
        and v["approval"]["variant_hash"] != v["variant_hash"]
    if invalidated:
        v["approval"] = None
    r = emit_receipt(state, "variant_revise",
                     {"variant_id": vid, "old_hash": old_hash,
                      "new_hash": v["variant_hash"],
                      "fields": sorted(changes),
                      "approval_invalidated": invalidated})
    return {"variant": v, "approval_invalidated": invalidated,
            "receipt_seq": r["seq"],
            "note": ("Approval was bound to the previous hash and is "
                     "now invalid; the variant returns to review."
                     if invalidated else
                     "No approval existed or the hash is unchanged.")}


def t_approval_pack(state, args):
    cid = str(args["canonical_id"])
    content = state["contents"].get(cid)
    if not content:
        raise ToolError(f"unknown canonical_id: {cid}")
    variants = [v for v in state["variants"].values()
                if v["canonical_id"] == cid]
    return {"canonical": content,
            "variants": variants,
            "review_contract": "Owner approves the exact pack or it "
                               "does not move (SS4). Approvals bind "
                               "hashes, not vibes."}


def t_approve_variant(state, args):
    vid = str(args["variant_id"])
    v = state["variants"].get(vid)
    if not v:
        raise ToolError(f"unknown variant_id: {vid}")
    content = state["contents"][v["canonical_id"]]
    if content["content_hash"] != v["canonical_hash"]:
        raise ToolError("canonical content changed since this variant "
                        "was built; rebuild the variant before approval")
    v["approval"] = {"approver": str(args["approver"]), "ts": now(),
                     "canonical_hash": content["content_hash"],
                     "variant_hash": v["variant_hash"]}
    r = emit_receipt(state, "variant_approved",
                     {"variant_id": vid, "approver": args["approver"],
                      "variant_hash": v["variant_hash"]})
    return {"variant_id": vid, "approval": v["approval"],
            "receipt_seq": r["seq"]}


def t_approval_check(state, args):
    """Recompute the variant's hash from its current fields and compare
    with the hash the approval bound. Any drift = invalid."""
    vid = str(args["variant_id"])
    v = state["variants"].get(vid)
    if not v:
        raise ToolError(f"unknown variant_id: {vid}")
    current = variant_hash(v)
    appr = v.get("approval")
    if not appr:
        return {"variant_id": vid, "approved": False, "valid": False,
                "reason": "no approval recorded for this variant",
                "current_hash": current}
    valid = (appr["variant_hash"] == current
             and appr["canonical_hash"]
             == state["contents"][v["canonical_id"]]["content_hash"])
    return {"variant_id": vid, "approved": True, "valid": valid,
            "approved_hash": appr["variant_hash"],
            "current_hash": current,
            "reason": ("hashes match the approval record" if valid else
                       "variant or canonical content changed after "
                       "approval — approval invalid (SS3.1)")}


# ---------------------------------------------------------------- engagement
def caps_for(week: int) -> dict:
    return PLAYBOOK["week1"] if int(week) <= 1 else PLAYBOOK["week2plus"]


def comment_key(text: str) -> str:
    return sha(re.sub(r"\s+", " ", (text or "").strip().lower()))


def t_policy_check(state, args):
    """The playbook as an evaluator. Returns ALLOW / DENY / STOP with a
    named reason; EVERY check is receipted, denials included."""
    eng = state["engagement"]
    action = str(args.get("action", ""))
    verdict, reason = "ALLOW", ""

    if action == "report_stop":
        signal = str(args.get("signal", "action_block"))
        eng["stopped"] = True
        eng["stop_reason"] = signal
        r = emit_receipt(state, "policy_check",
                         {"action": action, "signal": signal,
                          "verdict": "STOP"})
        return {"verdict": "STOP",
                "reason": f"stop signal {signal!r} recorded. A stop is "
                          "a final state for the session (SS5.3) — the "
                          "product does not retry through another "
                          "identity, endpoint, or session.",
                "receipt_seq": r["seq"]}

    if action == "reset":
        if not args.get("owner_reset"):
            verdict, reason = "DENY", "reset requires owner_reset=true"
        else:
            eng["stopped"] = False
            eng["stop_reason"] = None
            reason = "owner reset the session stop"
        r = emit_receipt(state, "policy_check",
                         {"action": action, "verdict": verdict})
        return {"verdict": verdict, "reason": reason,
                "receipt_seq": r["seq"]}

    blocked = kill_blocked(state, args.get("adapter"),
                           args.get("account_id"))
    if blocked:
        verdict, reason = "DENY", f"kill switch: {blocked}"
    elif eng["stopped"]:
        verdict = "STOP"
        reason = (f"session stopped ({eng['stop_reason']}); all "
                  "engagement checks stop until an owner reset (SS5.3)")
    elif action == "like":
        counts = args.get("counts") or {}
        caps = caps_for(args.get("week", 1))
        if int(counts.get("likes_today", 0)) >= caps["likes_per_day"]:
            verdict = "DENY"
            reason = (f"daily like cap reached: {caps['likes_per_day']}"
                      f" (week {args.get('week', 1)} playbook cap)")
        elif int(counts.get("likes_for_target_today", 0)) \
                >= PLAYBOOK["likes_per_target_per_day"]:
            verdict = "DENY"
            reason = ("per-target like cap reached: "
                      f"{PLAYBOOK['likes_per_target_per_day']}/day "
                      "(no liking everything from one account in a row)")
        else:
            reason = (f"within caps ({counts.get('likes_today', 0)}/"
                      f"{caps['likes_per_day']} likes today)")
    elif action == "comment":
        counts = args.get("counts") or {}
        caps = caps_for(args.get("week", 1))
        text = str(args.get("comment_text", ""))
        if int(counts.get("comments_today", 0)) >= caps["comments_per_day"]:
            verdict = "DENY"
            reason = (f"daily comment cap reached: "
                      f"{caps['comments_per_day']} "
                      f"(week {args.get('week', 1)} playbook cap)")
        elif URL_RE.search(text):
            verdict = "DENY"
            reason = "links are prohibited in engagement comments (SS5.1)"
        elif any(p in text.lower() for p in PLAYBOOK["promo_phrases"]):
            verdict = "DENY"
            reason = ("self-promo is prohibited in engagement comments "
                      "(SS5.1): no 'check my page', no DM asks")
        elif text.count("#") > PLAYBOOK["max_hashtags_in_comment"]:
            verdict = "DENY"
            reason = "hashtag stuffing is prohibited in comments (SS5.1)"
        elif len(EMOJI_RE.findall(text)) > PLAYBOOK["max_emoji_in_comment"]:
            verdict = "DENY"
            reason = ("at most 1 emoji per comment, usually none "
                      "(playbook rule 3)")
        elif comment_key(text) in eng["comment_keys"]:
            verdict = "DENY"
            reason = ("duplicate / near-duplicate comment — never repeat "
                      "a comment (playbook rule 3)")
        else:
            eng["comment_keys"].append(comment_key(text))
            reason = (f"within caps ({counts.get('comments_today', 0)}/"
                      f"{caps['comments_per_day']} comments today); "
                      "comment text reserved against duplication")
    else:
        verdict, reason = "DENY", f"unknown engagement action: {action!r}"

    r = emit_receipt(state, "policy_check",
                     {"action": action, "verdict": verdict,
                      "reason": reason,
                      "account_id": args.get("account_id"),
                      "adapter": args.get("adapter")})
    return {"verdict": verdict, "reason": reason, "receipt_seq": r["seq"],
            "playbook_caps": caps_for(args.get("week", 1))}


def t_engagement_log(state, args):
    """Append-only log of executed / owner-completed actions (SS5.3).
    Every field the daily report needs is required or defaulted here."""
    entry = {"ts": int(args.get("ts", now())),
             "account": args.get("account"), "adapter": args.get("adapter"),
             "mode": args.get("mode"), "target_account": args.get("target_account"),
             "target_url": args.get("target_url"), "action": args.get("action"),
             "comment_text": args.get("comment_text"),
             "why": args.get("why"), "result": args.get("result"),
             "stop_or_warning": args.get("stop_or_warning")}
    state["engagement"]["log"].append(entry)
    r = emit_receipt(state, "engagement_log",
                     {"action": entry["action"],
                      "target_account": entry["target_account"],
                      "log_size": len(state["engagement"]["log"])})
    return {"logged": entry, "receipt_seq": r["seq"]}


def t_engagement_report(state, args):
    week = int(args.get("week", 1))
    caps = caps_for(week)
    log = state["engagement"]["log"]
    likes = [e for e in log if e["action"] == "like"]
    comments = [e for e in log if e["action"] == "comment"]
    return {"entries": log, "totals": {"likes": len(likes),
                                       "comments": len(comments)},
            "caps": caps,
            "caps_remaining": {
                "likes": caps["likes_per_day"] - len(likes),
                "comments": caps["comments_per_day"] - len(comments)},
            "stopped": state["engagement"]["stopped"],
            "note": "The daily report is generated from this log and "
                    "contains every action; no action goes unreported "
                    "(SS5.3)."}


# --------------------------------------------------------------- kill switch
def t_adapter_kill_switch(state, args):
    scope = str(args.get("scope", "adapter"))
    on = bool(args.get("on", True))
    if scope == "family":
        state["kill"]["family"] = on
        target = "family"
    elif scope == "adapter":
        target = str(args["adapter"])
        state["kill"]["adapters"][target] = on
    elif scope == "account":
        target = str(args["account_id"])
        state["kill"]["accounts"][target] = on
        if target in state["accounts"]:
            state["accounts"][target]["kill_switch"] = on
    else:
        raise ToolError(f"unknown kill scope: {scope!r}")
    r = emit_receipt(state, "kill_switch",
                     {"scope": scope, "target": target, "on": on})
    return {"scope": scope, "target": target, "on": on,
            "receipt_seq": r["seq"],
            "note": "Write capabilities freeze first; existing drafts "
                    "and receipts remain readable (SS3.2 tool 14)."}


def t_receipt_list(state, args):
    return {"receipts": state["receipts"],
            "count": len(state["receipts"]),
            "chain_valid": verify_receipt_chain(state["receipts"])}


TOOLS = {
    "account_set": (t_account_set, "Register/update an authorized account: platform, adapter, owner, role, declared capability modes (capability -> mode), and the latest capability probe {status: ok|failed, at, terms_version}. A FAILED probe downgrades effective modes automatically (write modes collapse to prep; reads flagged). Evaluation only — no platform is contacted, no credentials are held.",
                    {"account_id": {"type": "string"}, "platform": {"type": "string"}, "adapter": {"type": "string"}, "owner": {"type": "string"}, "account_type": {"type": "string"}, "role": {"type": "string"}, "connection_state": {"type": "string"}, "modes": {"type": "object"}, "probe": {"type": "object"}}, ["account_id"]),
    "account_inventory": (t_account_inventory, "All registered accounts with declared + effective mode matrices, last probe, and kill-switch state. No credential values exist in this system.",
                          {}, []),
    "content_ingest": (t_content_ingest, "Ingest a canonical content object (SS3.1): masters + provenance, copy, claims WITH sources, rights per asset, accessibility assets, disclosure record, intended/prohibited surfaces, schedule. Validates and issues the SHA-256 content hash; re-ingesting changed content bumps the version. Missing rights/claims-sources/alt-text are named blockers.",
                       {"content": {"type": "object"}}, ["content"]),
    "content_get": (t_content_get, "One canonical content record in full, hash + approval state included.",
                    {"canonical_id": {"type": "string"}}, ["canonical_id"]),
    "adapt_preview": (t_adapt_preview, "Build one native variant for an adapter profile (aperture_feed, aperture_reel, aperture_story, prism_shorts, zephyr, wire): media geometry, copy under the surface's limit, the surface's working link placement, platform-required disclosure labels, element order — plus the classified adaptation diff. The variant is hash-bound at build.",
                      {"canonical_id": {"type": "string"}, "adapter": {"type": "string"}, "account_id": {"type": "string"}, "mode": {"type": "string"}, "schedule": {"type": "object"}}, ["canonical_id", "adapter"]),
    "adaptation_diff": (t_adaptation_diff, "The classified diff for a built variant (MEDIA_CROP, TEXT_REWRITE, LINK_PLACEMENT, ORDER, DISCLOSURE, METADATA, FORMAT_OMISSION, ...). Substantive changes — numbers, claims, CTA — are flagged, never silent.",
                        {"variant_id": {"type": "string"}}, ["variant_id"]),
    "variant_revise": (t_variant_revise, "Revise a variant's copy/hashtags/schedule/destination/link/disclosures/order/media. HASH LAW: the hash recomputes; an approval bound to the old hash is invalidated and the variant returns to review.",
                       {"variant_id": {"type": "string"}, "changes": {"type": "object"}}, ["variant_id", "changes"]),
    "approval_pack": (t_approval_pack, "The review artifact (SS3.2 tool 6): canonical item + every native variant + diffs + destination/account + schedule. This is the object the owner approves.",
                      {"canonical_id": {"type": "string"}}, ["canonical_id"]),
    "approve_variant": (t_approve_variant, "Record the owner's approval of one variant, bound to the exact canonical hash and exact variant hash.",
                        {"variant_id": {"type": "string"}, "approver": {"type": "string"}}, ["variant_id", "approver"]),
    "approval_check": (t_approval_check, "Verify a variant's approval is still valid: recompute the hash from current fields and compare with the approved hash. Any post-approval change = invalid.",
                       {"variant_id": {"type": "string"}}, ["variant_id"]),
    "policy_check": (t_policy_check, "Engagement policy evaluator — the house playbook as data (SS5). action: like | comment | report_stop | reset. Enforces week-1 caps (15 likes / 5 comments per day) and week-2+ caps (30/10), the 2-likes-per-target cap, no links / no self-promo / no hashtag stuffing / <=1 emoji in comments, no duplicate comments, and stop-signal finality. EVERY check is receipted, ALLOW and DENY alike.",
                     {"action": {"type": "string"}, "week": {"type": "integer"}, "counts": {"type": "object"}, "comment_text": {"type": "string"}, "signal": {"type": "string"}, "account_id": {"type": "string"}, "adapter": {"type": "string"}, "owner_reset": {"type": "boolean"}}, ["action"]),
    "engagement_log": (t_engagement_log, "Append one executed or owner-completed engagement action to the append-only log (timestamp, account, adapter/mode, target, action, full comment text, why, result, cap context, stop state).",
                       {"account": {"type": "string"}, "adapter": {"type": "string"}, "mode": {"type": "string"}, "target_account": {"type": "string"}, "target_url": {"type": "string"}, "action": {"type": "string"}, "comment_text": {"type": "string"}, "why": {"type": "string"}, "result": {"type": "string"}, "stop_or_warning": {"type": "string"}, "ts": {"type": "integer"}}, ["action"]),
    "engagement_report": (t_engagement_report, "Daily-report view over the engagement log: every action, totals vs the week's caps, stop state.",
                          {"week": {"type": "integer"}}, []),
    "adapter_kill_switch": (t_adapter_kill_switch, "Independently disable one capability scope: family | adapter | account. Write capabilities freeze first; drafts and receipts remain readable.",
                            {"scope": {"type": "string"}, "adapter": {"type": "string"}, "account_id": {"type": "string"}, "on": {"type": "boolean"}}, ["scope"]),
    "receipt_list": (t_receipt_list, "The append-only, hash-chained receipt ledger, with chain verification.",
                     {}, []),
}


def tool_list():
    return [{"name": name, "description": desc,
             "inputSchema": {"type": "object", "properties": props, "required": req}}
            for name, (_, desc, props, req) in TOOLS.items()]


def handle(req: dict):
    method, rid = req.get("method", ""), req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": req.get("params", {}).get("protocolVersion", "2025-03-26"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "eclipse-social-core", "version": "0.1.0"}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": tool_list()}}
    if method == "tools/call":
        name = req["params"]["name"]
        args = req["params"].get("arguments", {})
        if name not in TOOLS:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
        state = load_state()
        try:
            out = TOOLS[name][0](state, args)
            save_state(state)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps(out, indent=1)}]}}
        except ToolError as e:
            save_state(state)  # receipts emitted before a refusal must persist
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}}
    if rid is not None:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return None  # notification


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            resp = handle(json.loads(line))
        except Exception as e:  # never crash the transport
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()

# Eclipse Social Core MCP · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
