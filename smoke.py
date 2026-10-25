#!/usr/bin/env python3
"""Smoke: drive server.py over real stdio with a temp state file.
Ingests the synthetic fixture package, registers the dogfood account,
builds + approves a variant, revises it (approval must invalidate),
runs two engagement policy checks. NO platform is contacted."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent


def call(proc, rid, name, args):
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid,
                                 "method": "tools/call",
                                 "params": {"name": name,
                                            "arguments": args}}) + "\n")
    proc.stdin.flush()
    resp = json.loads(proc.stdout.readline())
    return json.loads(resp["result"]["content"][0]["text"])


def main():
    with tempfile.TemporaryDirectory() as td:
        env = {"ECLIPSE_SOCIAL_CORE_STATE": str(Path(td) / "state.json"),
               "PATH": "/usr/bin:/bin:/usr/local/bin"}
        proc = subprocess.Popen([sys.executable, str(ROOT / "server.py")],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                text=True, env=env)
        try:
            proc.stdin.write(json.dumps(
                {"jsonrpc": "2.0", "id": 0, "method": "initialize",
                 "params": {"protocolVersion": "2025-03-26"}}) + "\n")
            proc.stdin.flush()
            init = json.loads(proc.stdout.readline())
            print("server:", init["result"]["serverInfo"])
            rid = 1
            content = json.loads(
                (ROOT / "fixtures" / "sample_content.json").read_text())
            out = call(proc, rid, "content_ingest", {"content": content})
            rid += 1
            print("ingest:", out["status"], out["version"],
                  out["content_hash"][:12])
            out = call(proc, rid, "account_set", {
                "account_id": "ig-wr", "platform": "instagram",
                "adapter": "aperture",
                "modes": {"publishing": "PUBLISH_API",
                          "reads": "READ_API",
                          "community": "COMMUNITY_PREP"},
                "probe": {"status": "ok", "at": "2026-10-25",
                          "terms_version": "fixture"}})
            rid += 1
            print("account:", out["account"]["account_id"],
                  "downgraded:", out["downgraded"])
            out = call(proc, rid, "adapt_preview", {
                "canonical_id": "wr-ep-sample-001",
                "adapter": "aperture_reel", "account_id": "ig-wr",
                "mode": "PUBLISH_API"})
            rid += 1
            vid = out["variant"]["variant_id"]
            print("variant:", vid, "diffs:",
                  [d["category"] for d in out["variant"]["diffs"]])
            call(proc, rid, "approve_variant",
                 {"variant_id": vid, "approver": "owner"})
            rid += 1
            chk = call(proc, rid, "approval_check", {"variant_id": vid})
            rid += 1
            print("approval valid after approve:", chk["valid"])
            out = call(proc, rid, "variant_revise", {
                "variant_id": vid,
                "changes": {"copy_text": "Edited after approval."}})
            rid += 1
            print("approval invalidated by edit:",
                  out["approval_invalidated"])
            ok = call(proc, rid, "policy_check",
                      {"action": "like", "week": 1,
                       "counts": {"likes_today": 14}})
            rid += 1
            no = call(proc, rid, "policy_check",
                      {"action": "like", "week": 1,
                       "counts": {"likes_today": 15}})
            rid += 1
            print("policy: 15th like ->", ok["verdict"],
                  "| 16th like ->", no["verdict"])
            rec = call(proc, rid, "receipt_list", {})
            print("receipts:", rec["count"], "chain valid:",
                  rec["chain_valid"])
        finally:
            proc.stdin.close()
            proc.wait(timeout=10)


if __name__ == "__main__":
    main()
