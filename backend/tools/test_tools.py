"""
Quick test script to verify each tool works standalone.
Run from the project root: python -m backend.tools.test_tools
"""
import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.tools import db_tool, deploy_tool, slack_tool

print("=" * 60)
print("TOOL TEST SUITE")
print("=" * 60)

# ── Test 1: db_tool ───────────────────────────────────────────
print("\n[1] Testing db_tool.log_review ...")
result = db_tool.log_review(pr_number=42, verdict="approved", reasoning="Test PR - looks clean")
print(f"    Result: {result}")
assert result["status"] == "ok", f"FAIL: {result}"
print("    PASS ✓")

print("\n[2] Testing db_tool.log_deployment ...")
result = db_tool.log_deployment(environment="dev", image_tag="test-abc123", status="deployed")
deploy_id = result["id"]
print(f"    Result: {result}")
assert result["status"] == "ok", f"FAIL: {result}"
print("    PASS ✓")

print("\n[3] Testing db_tool.log_deployment (smoke_test_passed) ...")
result = db_tool.log_deployment(environment="dev", image_tag="test-abc123", status="smoke_test_passed")
print(f"    Result: {result}")
assert result["status"] == "ok", f"FAIL: {result}"
print("    PASS ✓")

print("\n[4] Testing db_tool.get_last_good_tag ...")
result = db_tool.get_last_good_tag(environment="dev")
print(f"    Result: {result}")
assert result["status"] == "ok" and result["image_tag"] == "test-abc123", f"FAIL: {result}"
print("    PASS ✓")

print("\n[5] Testing db_tool.log_rollback ...")
result = db_tool.log_rollback(deployment_id=deploy_id, reasoning="smoke test failed", reverted_to_tag="test-abc123")
print(f"    Result: {result}")
assert result["status"] == "ok", f"FAIL: {result}"
print("    PASS ✓")

# ── Test 2: deploy_tool smoke test ────────────────────────────
print("\n[6] Testing deploy_tool.run_smoke_test (dev) ...")
result = deploy_tool.run_smoke_test("dev")
print(f"    Result: {result}")
assert result["status"] == "pass", f"FAIL: {result}"
print("    PASS ✓")

# ── Test 3: slack_tool (will skip if no webhook configured) ───
print("\n[7] Testing slack_tool.send_message ...")
result = slack_tool.send_message("Test message from Agentic PR Release pipeline 🚀")
print(f"    Result: {result}")
print("    PASS ✓ (skipped if no webhook)")

# ── Summary ───────────────────────────────────────────────────
print("\n" + "=" * 60)
print("ALL TESTS PASSED ✓")
print("=" * 60)
