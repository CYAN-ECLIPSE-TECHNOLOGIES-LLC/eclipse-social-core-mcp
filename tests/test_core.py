#!/usr/bin/env python3
# Eclipse Social Core MCP
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
# Eclipse Social Core v0.1 (S0) — unit tests.

"""Eclipse Social Core v0.1 (S0) — unit tests.
Run: python3 -m unittest discover tests"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import server as S  # noqa: E402

ROOT = Path(__file__).parent.parent
FIX = ROOT / "fixtures"


def sample_content():
    return json.loads((FIX / "sample_content.json").read_text())


def ingested_state():
    st = S.empty_state()
    S.t_content_ingest(st, {"content": sample_content()})
    return st


class TestIngest(unittest.TestCase):
    def test_ingest_hashes_and_versions(self):
        st = S.empty_state()
        out = S.t_content_ingest(st, {"content": sample_content()})
        self.assertEqual(out["version"], 1)
        self.assertEqual(len(out["content_hash"]), 64)
        again = S.t_content_ingest(st, {"content": sample_content()})
        self.assertEqual(again["status"], "unchanged")
        changed = sample_content()
        changed["title"] = "A different title"
        bumped = S.t_content_ingest(st, {"content": changed})
        self.assertEqual(bumped["version"], 2)
        self.assertNotEqual(bumped["content_hash"], out["content_hash"])

    def test_rights_blocker_named(self):
        bad = sample_content()
        bad["rights"] = [r for r in bad["rights"]
                         if r["asset_id"] != "cover-001"]
        with self.assertRaises(S.ToolError) as cm:
            S.t_content_ingest(S.empty_state(), {"content": bad})
        self.assertIn("cover-001", str(cm.exception))
        self.assertIn("rights", str(cm.exception))

    def test_claim_without_source_blocked(self):
        bad = sample_content()
        bad["claims"] = [{"text": "unsourced claim", "source": ""}]
        with self.assertRaises(S.ToolError):
            S.t_content_ingest(S.empty_state(), {"content": bad})

    def test_missing_alt_text_blocked(self):
        bad = sample_content()
        bad["accessibility"] = {"captions": "x", "alt_text": {}}
        with self.assertRaises(S.ToolError) as cm:
            S.t_content_ingest(S.empty_state(), {"content": bad})
        self.assertIn("alt text", str(cm.exception))


class TestAdaptation(unittest.TestCase):
    def test_feed_variant_geometry_and_link_diff(self):
        st = ingested_state()
        out = S.t_adapt_preview(st, {"canonical_id": "wr-ep-sample-001",
                                     "adapter": "aperture_feed",
                                     "account_id": "ig-wr"})
        v = out["variant"]
        self.assertEqual(v["media"][0]["aspect_out"], "4:5")
        self.assertEqual(v["link"]["placement"], "profile_link")
        cats = {d["category"] for d in v["diffs"]}
        self.assertIn("MEDIA_CROP", cats)
        self.assertIn("LINK_PLACEMENT", cats)

    def test_zephyr_truncation_flags_substantive_number_loss(self):
        st = ingested_state()
        long = sample_content()
        long["canonical_id"] = "wr-long-001"
        long["short_copy"] = ("Markets were quiet today. " * 20) \
            + "Inflows printed $635.6M this week."
        S.t_content_ingest(st, {"content": long})
        out = S.t_adapt_preview(st, {"canonical_id": "wr-long-001",
                                     "adapter": "zephyr"})
        diffs = {d["category"]: d for d in out["variant"]["diffs"]}
        self.assertIn("TEXT_REWRITE", diffs)
        self.assertTrue(diffs["TEXT_REWRITE"]["substantive"])
        self.assertIn("$635.6M", diffs["TEXT_REWRITE"]["note"])

    def test_ai_label_added_as_disclosure_diff(self):
        st = ingested_state()
        out = S.t_adapt_preview(st, {"canonical_id": "wr-ep-sample-001",
                                     "adapter": "aperture_reel"})
        cats = {d["category"] for d in out["variant"]["diffs"]}
        self.assertIn("DISCLOSURE", cats)
        self.assertTrue(
            out["variant"]["disclosures_out"]["platform_ai_label"])

    def test_prohibited_surface_refused(self):
        st = ingested_state()
        c = sample_content()
        c["canonical_id"] = "wr-nogo-001"
        c["prohibited_surfaces"] = ["wire"]
        S.t_content_ingest(st, {"content": c})
        with self.assertRaises(S.ToolError):
            S.t_adapt_preview(st, {"canonical_id": "wr-nogo-001",
                                   "adapter": "wire"})


class TestHashLaw(unittest.TestCase):
    def _approved_variant(self, st):
        out = S.t_adapt_preview(st, {"canonical_id": "wr-ep-sample-001",
                                     "adapter": "aperture_feed",
                                     "account_id": "ig-wr"})
        vid = out["variant"]["variant_id"]
        S.t_approve_variant(st, {"variant_id": vid, "approver": "owner"})
        return vid

    def test_approval_valid_until_any_change(self):
        st = ingested_state()
        vid = self._approved_variant(st)
        chk = S.t_approval_check(st, {"variant_id": vid})
        self.assertTrue(chk["valid"])

    def test_copy_change_invalidates(self):
        st = ingested_state()
        vid = self._approved_variant(st)
        out = S.t_variant_revise(st, {"variant_id": vid, "changes": {
            "copy_text": "Edited after approval."}})
        self.assertTrue(out["approval_invalidated"])
        chk = S.t_approval_check(st, {"variant_id": vid})
        self.assertFalse(chk["valid"])

    def test_schedule_change_invalidates(self):
        st = ingested_state()
        vid = self._approved_variant(st)
        out = S.t_variant_revise(st, {"variant_id": vid, "changes": {
            "schedule": {"publish_at": "2026-10-27T13:05:00Z",
                         "timezone": "America/Los_Angeles"}}})
        self.assertTrue(out["approval_invalidated"])

    def test_destination_change_invalidates(self):
        st = ingested_state()
        vid = self._approved_variant(st)
        out = S.t_variant_revise(st, {"variant_id": vid, "changes": {
            "destination_account": "someone-else"}})
        self.assertTrue(out["approval_invalidated"])

    def test_direct_field_tamper_detected_by_check(self):
        st = ingested_state()
        vid = self._approved_variant(st)
        st["variants"][vid]["copy_text"] = "tampered outside the tools"
        chk = S.t_approval_check(st, {"variant_id": vid})
        self.assertFalse(chk["valid"])
        self.assertIn("changed after approval", chk["reason"])


class TestModesAndDowngrade(unittest.TestCase):
    def _account(self, st, probe_status):
        return S.t_account_set(st, {
            "account_id": "ig-wr", "platform": "instagram",
            "adapter": "aperture", "owner": "Cyan Eclipse Technologies",
            "modes": {"publishing": "PUBLISH_API", "drafts": "DRAFT_API",
                      "reads": "READ_API",
                      "own_engagement": "OWN_ENGAGEMENT_API",
                      "community": "COMMUNITY_PREP"},
            "probe": {"status": probe_status, "at": "2026-10-25",
                      "terms_version": "fixture"}})

    def test_ok_probe_keeps_modes(self):
        st = S.empty_state()
        out = self._account(st, "ok")
        self.assertFalse(out["downgraded"])
        self.assertEqual(out["account"]["effective_modes"]["publishing"],
                         "PUBLISH_API")

    def test_failed_probe_downgrades_writes_to_prep(self):
        st = S.empty_state()
        out = self._account(st, "failed")
        self.assertTrue(out["downgraded"])
        eff = out["account"]["effective_modes"]
        self.assertEqual(eff["publishing"], "PREP_PACK")
        self.assertEqual(eff["drafts"], "PREP_PACK")
        self.assertEqual(eff["own_engagement"], "COMMUNITY_PREP")
        self.assertEqual(eff["reads"], "READ_API")

    def test_unknown_mode_rejected(self):
        with self.assertRaises(S.ToolError):
            S.t_account_set(S.empty_state(), {
                "account_id": "x", "modes": {"publishing": "SESSION_COOKIE"}})


class TestPolicyCheck(unittest.TestCase):
    def test_week1_like_cap_16th_denied(self):
        st = S.empty_state()
        ok = S.t_policy_check(st, {"action": "like", "week": 1,
                                   "counts": {"likes_today": 14}})
        self.assertEqual(ok["verdict"], "ALLOW")
        no = S.t_policy_check(st, {"action": "like", "week": 1,
                                   "counts": {"likes_today": 15}})
        self.assertEqual(no["verdict"], "DENY")
        self.assertIn("cap", no["reason"])

    def test_week2_caps_higher(self):
        st = S.empty_state()
        out = S.t_policy_check(st, {"action": "like", "week": 2,
                                    "counts": {"likes_today": 15}})
        self.assertEqual(out["verdict"], "ALLOW")

    def test_comment_cap_denied(self):
        st = S.empty_state()
        out = S.t_policy_check(st, {"action": "comment", "week": 1,
                                    "counts": {"comments_today": 5},
                                    "comment_text": "Sharp point on the flows."})
        self.assertEqual(out["verdict"], "DENY")

    def test_per_target_like_cap(self):
        st = S.empty_state()
        out = S.t_policy_check(st, {"action": "like", "week": 1, "counts": {
            "likes_today": 3, "likes_for_target_today": 2}})
        self.assertEqual(out["verdict"], "DENY")
        self.assertIn("per-target", out["reason"])

    def test_comment_content_rules(self):
        st = S.empty_state()
        base = {"action": "comment", "week": 1,
                "counts": {"comments_today": 0}}
        link = S.t_policy_check(st, {**base, "comment_text":
                                     "Great chart, see https://x.example"})
        self.assertEqual(link["verdict"], "DENY")
        promo = S.t_policy_check(st, {**base, "comment_text":
                                      "Nice post, check my page"})
        self.assertEqual(promo["verdict"], "DENY")
        tags = S.t_policy_check(st, {**base, "comment_text":
                                     "On point #btc #crypto #ai #markets"})
        self.assertEqual(tags["verdict"], "DENY")
        good = S.t_policy_check(st, {**base, "comment_text":
                                     "The $635.6M print is the story — "
                                     "third straight week of inflows."})
        self.assertEqual(good["verdict"], "ALLOW")

    def test_duplicate_comment_denied(self):
        st = S.empty_state()
        args = {"action": "comment", "week": 1,
                "counts": {"comments_today": 0},
                "comment_text": "The flows confirm the bid."}
        self.assertEqual(S.t_policy_check(st, args)["verdict"], "ALLOW")
        self.assertEqual(S.t_policy_check(st, args)["verdict"], "DENY")

    def test_action_block_stops_everything(self):
        st = S.empty_state()
        stop = S.t_policy_check(st, {"action": "report_stop",
                                     "signal": "action_block"})
        self.assertEqual(stop["verdict"], "STOP")
        after = S.t_policy_check(st, {"action": "like", "week": 1,
                                      "counts": {"likes_today": 0}})
        self.assertEqual(after["verdict"], "STOP")
        reset = S.t_policy_check(st, {"action": "reset",
                                      "owner_reset": True})
        self.assertEqual(reset["verdict"], "ALLOW")
        again = S.t_policy_check(st, {"action": "like", "week": 1,
                                      "counts": {"likes_today": 0}})
        self.assertEqual(again["verdict"], "ALLOW")

    def test_every_check_receipted(self):
        st = S.empty_state()
        before = len(st["receipts"])
        S.t_policy_check(st, {"action": "like", "week": 1,
                              "counts": {"likes_today": 15}})  # DENY
        S.t_policy_check(st, {"action": "like", "week": 1,
                              "counts": {"likes_today": 0}})   # ALLOW
        self.assertEqual(len(st["receipts"]), before + 2)
        self.assertTrue(S.verify_receipt_chain(st["receipts"]))


class TestKillSwitchAndLog(unittest.TestCase):
    def test_kill_switch_blocks_adaptation(self):
        st = ingested_state()
        S.t_adapter_kill_switch(st, {"scope": "adapter",
                                     "adapter": "aperture_feed",
                                     "on": True})
        with self.assertRaises(S.ToolError) as cm:
            S.t_adapt_preview(st, {"canonical_id": "wr-ep-sample-001",
                                   "adapter": "aperture_feed"})
        self.assertIn("kill switch", str(cm.exception))

    def test_engagement_log_and_report(self):
        st = S.empty_state()
        S.t_engagement_log(st, {"account": "ig-wr", "action": "like",
                                "target_account": "bigcrypto",
                                "why": "on-topic BTC chart post",
                                "result": "done"})
        S.t_engagement_log(st, {"account": "ig-wr", "action": "comment",
                                "target_account": "bigcrypto",
                                "comment_text": "The flows confirm it.",
                                "why": "specific claim hook",
                                "result": "done"})
        rep = S.t_engagement_report(st, {"week": 1})
        self.assertEqual(rep["totals"], {"likes": 1, "comments": 1})
        self.assertEqual(rep["caps_remaining"]["likes"], 14)
        self.assertEqual(rep["caps_remaining"]["comments"], 4)


if __name__ == "__main__":
    unittest.main()

# Eclipse Social Core MCP · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
