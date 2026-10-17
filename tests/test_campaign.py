from collections import Counter

from lambda_rca.config import Config
from lambda_rca.harness.campaign import plan_windows


def test_plan_matches_section_4_4():
    cfg = Config.load()
    plan = plan_windows(cfg)
    counts = Counter(w.fault_type for w in plan)
    # 5 fault types x 4 functions x 3 repetitions, 15 silent drift, 20 normal = 95 windows
    assert all(counts[f] == 12 for f in ["F1", "F2", "F3", "F4", "F5"])
    assert counts["F6"] == 15 and counts["N"] == 20
    assert len(plan) == 95
    assert len({w.window_id for w in plan}) == 95


def test_plan_is_deterministic_and_ids_are_neutral():
    cfg = Config.load()
    a, b = plan_windows(cfg), plan_windows(cfg)
    assert a == b
    assert all(w.window_id.startswith("W") and w.window_id[1:].isdigit() for w in a)
