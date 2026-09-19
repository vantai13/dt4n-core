"""Tap file DONG BANG cua Phase 7 (Lesson 7.7 phan 2). Mot nguon su that cho freeze + manifest."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 1. He thong dang CHAY (runtime): doi mot byte = he khac = receipt cu vo gia tri.
RUNTIME = [
    "bridge/adapter.py", "bridge/bootstrap.py", "bridge/collector.py", "bridge/collector_version.py",
    "bridge/command_agent.py", "bridge/detector_contract.py", "bridge/detector_runner.py",
    "bridge/differ.py", "bridge/ditto_common.py", "bridge/freshness.py", "bridge/health.py",
    "bridge/live_controller.py", "bridge/pusher.py", "bridge/sync_agent.py",
    "twin/link_direction.py",
    "ml/operating_range.py",
    "ditto/policy.json", "ditto/routing_table.json", "ditto/topology_spec.json",
    "dashboard/package.json", "dashboard/package-lock.json",
]
# 2. Da ghim tu 6R: PHAI trung bit voi phase6r_manifest (khong duoc troi).
PINNED_6R = [
    "ml/blast_radius.py", "ml/conservation.py", "ml/fsm.py", "ml/intervention_log.py", "ml/model.py",
    "ml/payload.py", "ml/release.py", "ml/serve.py", "ml/serve_fast.py", "ml/snapshot_contract.py",
    "models/detector-release-1.0.0.json", "models/envelope-1.0.0.json",
]
# 3. Hop dong da niem phong ma runtime DOC.
SEALED = [
    "results/report/phase6r_slo.json", "results/report/phase7_prereg.json",
    "results/report/phase7_contract.json", "results/report/phase7_contract_amendment_1.json",
    "results/report/phase7_s6_v2_prereg.json",
]
# 4. Dung cu do nghiem thu: doi dung cu giua cac lan do = so sanh vo nghia.
HARNESS = [
    "scripts/phase7_live_common.py", "scripts/measure_phase7_s12_live.py", "scripts/measure_phase7_e2e.py",
    "scripts/run_phase7_s11_live.py", "scripts/run_phase7_contention.py", "scripts/soak_phase7_live_v2.py",
    "scripts/run_phase7_acceptance.py", "mininet/controller_static.py",
    "measurements/clock_bridge.py", "measurements/e2e_budget.py", "measurements/stability.py",
    "measurements/stats.py", "rl/injection.py", "rl/scenarios.py", "mininet/env_runner.py",
]


def dashboard_src() -> list[str]:
    return sorted(str(p.relative_to(ROOT)) for p in (ROOT / "dashboard/src").rglob("*") if p.is_file())


def frozen_files() -> dict[str, list[str]]:
    return {"runtime": RUNTIME + dashboard_src(), "pinned_6r": PINNED_6R,
            "sealed": SEALED, "harness": HARNESS}
