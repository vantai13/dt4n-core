#!/usr/bin/env python3
"""Pure tests for generated static routing."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mininet.gen_routes import load_spec, next_hop_table, verify_no_loop  # noqa: E402



def test_static_routes_match_phase_45_intent():
    spec = load_spec(str(ROOT / "ditto/topology_spec.json"))
    table = next_hop_table(spec)

    assert table["s1"]["10.0.0.4"] == "s2"
    assert table["s1"]["10.0.0.5"] == "s3"
    assert table["s2"]["10.0.0.5"] == "s3"
    assert table["s3"]["10.0.0.4"] == "s2"


def test_static_routes_have_no_forwarding_loop():
    spec = load_spec(str(ROOT / "ditto/topology_spec.json"))
    table = next_hop_table(spec)

    assert verify_no_loop(table, spec) is True


if __name__ == "__main__":
    test_static_routes_match_phase_45_intent()
    test_static_routes_have_no_forwarding_loop()
    print("static routing tests passed")
