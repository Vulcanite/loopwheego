"""Unit tests for pure geometry, dedup, and scoring helpers in route_generator.

No network: these functions never call OSRM or other HTTP services.
"""

from __future__ import annotations

import pytest

from app.services.route_generator import (
    _dedupe_anchor_bearing_buckets,
    _max_segment_km,
    _max_segment_threshold_km,
    _overlap_ratio,
    _score_loop,
)
from app.utils.geo import haversine_km


def _pt(lng: float, lat: float) -> list[float]:
    return [lng, lat]


def _anchor(*, bearing: float, dist: float, kind: str, name: str) -> dict:
    return {
        "name": name,
        "lat": 1.35,
        "lng": 103.82,
        "bearing_deg": bearing,
        "start_dist_km": dist,
        "kind": kind,
    }


# ─────────────────────────────────────────────────────────────
# _overlap_ratio
# ─────────────────────────────────────────────────────────────


class TestOverlapRatio:
    def test_short_polyline_is_fully_overlapped(self) -> None:
        assert _overlap_ratio([]) == 1.0
        assert _overlap_ratio([_pt(0.0, 0.0)]) == 1.0
        assert _overlap_ratio([_pt(0.0, 0.0), _pt(1.0, 0.0)]) == 1.0

    def test_unique_segments_have_zero_overlap(self) -> None:
        # Open path of distinct edges: no repeated (unordered) segment keys.
        polyline = [_pt(0.0, 0.0), _pt(1.0, 0.0), _pt(1.0, 1.0), _pt(0.0, 1.0)]
        assert _overlap_ratio(polyline) == 0.0

    def test_out_and_back_counts_as_half_overlap(self) -> None:
        # A→B then B→A hashes to the same unordered segment key, so 1 of 2
        # segments is a repeat.
        polyline = [_pt(103.8, 1.3), _pt(103.81, 1.3), _pt(103.8, 1.3)]
        assert _overlap_ratio(polyline) == pytest.approx(0.5)

    def test_retraced_loop_is_fully_overlapped(self) -> None:
        a, b, c = _pt(0.0, 0.0), _pt(1.0, 0.0), _pt(1.0, 1.0)
        polyline = [a, b, c, a, b, c]
        # 5 segments, first pass introduces 3 unique keys, second pass retraces
        # two of them (c→a is new). Repeated = sum(max(0, count-1)).
        ratio = _overlap_ratio(polyline)
        assert 0.0 < ratio <= 1.0
        assert ratio == pytest.approx(2.0 / 5.0)

    def test_rounding_collapses_near_duplicate_vertices(self) -> None:
        # Keys round to 5 decimal places: 4e-6° of jitter is the same vertex,
        # so A→A'→A hashes as a single retraced edge.
        polyline = [
            _pt(103.80000, 1.30000),
            _pt(103.800004, 1.30000),
            _pt(103.80000, 1.30000),
        ]
        identical = [
            _pt(103.80000, 1.30000),
            _pt(103.80000, 1.30000),
            _pt(103.80000, 1.30000),
        ]
        assert _overlap_ratio(polyline) == pytest.approx(_overlap_ratio(identical))
        assert _overlap_ratio(polyline) == pytest.approx(0.5)


# ─────────────────────────────────────────────────────────────
# bearing-bucket dedup
# ─────────────────────────────────────────────────────────────


class TestDedupeAnchorBearingBuckets:
    def test_prefers_seed_places_over_directional(self) -> None:
        directional = _anchor(bearing=10.0, dist=0.5, kind="directional", name="dir")
        seed = _anchor(bearing=11.0, dist=0.8, kind="seed_place", name="seed")
        picked = _dedupe_anchor_bearing_buckets([directional, seed], max_anchors=4)
        assert picked[0]["name"] == "seed"

    def test_skips_same_bucket_until_half_capacity(self) -> None:
        # 22.5° buckets: 0–22.4 share bucket 0. max_anchors=4 → skip dupes
        # while len(picked) < 2.
        same_bucket = [
            _anchor(bearing=1.0, dist=0.4, kind="seed_place", name="a"),
            _anchor(bearing=10.0, dist=0.5, kind="seed_place", name="b"),
            _anchor(bearing=20.0, dist=0.6, kind="seed_place", name="c"),
        ]
        picked = _dedupe_anchor_bearing_buckets(same_bucket, max_anchors=4)
        assert [a["name"] for a in picked] == ["a"]

    def test_allows_same_bucket_after_half_capacity(self) -> None:
        anchors = [
            _anchor(bearing=0.0, dist=0.4, kind="seed_place", name="n"),
            _anchor(bearing=90.0, dist=0.4, kind="seed_place", name="e"),
            _anchor(bearing=5.0, dist=0.5, kind="seed_place", name="n2"),
        ]
        picked = _dedupe_anchor_bearing_buckets(anchors, max_anchors=4)
        names = [a["name"] for a in picked]
        assert names == ["n", "e", "n2"]

    def test_caps_at_max_anchors(self) -> None:
        anchors = [
            _anchor(bearing=float(i * 23), dist=0.4 + i * 0.01, kind="seed_place", name=f"a{i}")
            for i in range(20)
        ]
        picked = _dedupe_anchor_bearing_buckets(anchors, max_anchors=8)
        assert len(picked) == 8

    def test_empty_input(self) -> None:
        assert _dedupe_anchor_bearing_buckets([]) == []


# ─────────────────────────────────────────────────────────────
# _max_segment_km / threshold
# ─────────────────────────────────────────────────────────────


class TestMaxSegment:
    def test_short_polyline_is_zero(self) -> None:
        assert _max_segment_km([]) == 0.0
        assert _max_segment_km([_pt(103.8, 1.3)]) == 0.0

    def test_matches_haversine_of_longest_edge(self) -> None:
        a = _pt(103.80, 1.30)
        b = _pt(103.81, 1.30)
        c = _pt(103.81, 1.40)  # ~11 km north, the jump
        polyline = [a, b, c]
        expected = haversine_km(a[1], a[0], c[1], c[0])
        # Longest edge is b→c, not a→c.
        expected_bc = haversine_km(b[1], b[0], c[1], c[0])
        assert _max_segment_km(polyline) == pytest.approx(expected_bc)
        assert expected_bc > expected * 0.5

    def test_walk_threshold_floors_and_caps(self) -> None:
        # max(0.9, min(2.2, target * 0.04))
        assert _max_segment_threshold_km("walk", 5.0) == pytest.approx(0.9)
        assert _max_segment_threshold_km("walk", 50.0) == pytest.approx(2.0)
        assert _max_segment_threshold_km("walk", 200.0) == pytest.approx(2.2)

    def test_cycle_threshold_floors_and_caps(self) -> None:
        # max(1.6, min(4.0, target * 0.05))
        assert _max_segment_threshold_km("cycle", 5.0) == pytest.approx(1.6)
        assert _max_segment_threshold_km("cycle", 50.0) == pytest.approx(2.5)
        assert _max_segment_threshold_km("cycle", 200.0) == pytest.approx(4.0)

    def test_implausible_jump_exceeds_walk_threshold(self) -> None:
        a = _pt(103.80, 1.30)
        b = _pt(103.80, 1.35)  # ~5.5 km, well above the 0.9 km walk floor
        jump = _max_segment_km([a, b])
        assert jump > _max_segment_threshold_km("walk", 5.0)


# ─────────────────────────────────────────────────────────────
# _score_loop
# ─────────────────────────────────────────────────────────────


def _straight_polyline(n: int = 4) -> list[list[float]]:
    return [_pt(103.80 + i * 0.002, 1.30) for i in range(n)]


class TestScoreLoop:
    def _score(self, **overrides: object) -> float:
        kwargs: dict = {
            "polyline": _straight_polyline(),
            "loop_distance_km": 5.0,
            "target_distance_km": 5.0,
            "a_bearing_deg": 0.0,
            "b_bearing_deg": 180.0,
            "a_kind": "directional",
            "b_kind": "directional",
        }
        kwargs.update(overrides)
        return _score_loop(**kwargs)

    def test_closer_distance_scores_better(self) -> None:
        on_target = self._score(loop_distance_km=5.0)
        off_target = self._score(loop_distance_km=7.0)
        assert on_target < off_target
        assert off_target - on_target == pytest.approx(2.0 * 26.0)

    def test_overlap_increases_score(self) -> None:
        unique = _straight_polyline()
        out_and_back = [_pt(103.80, 1.30), _pt(103.81, 1.30), _pt(103.80, 1.30)]
        assert _score_loop(
            polyline=out_and_back,
            loop_distance_km=5.0,
            target_distance_km=5.0,
            a_bearing_deg=0.0,
            b_bearing_deg=180.0,
            a_kind="directional",
            b_kind="directional",
        ) > _score_loop(
            polyline=unique,
            loop_distance_km=5.0,
            target_distance_km=5.0,
            a_bearing_deg=0.0,
            b_bearing_deg=180.0,
            a_kind="directional",
            b_kind="directional",
        )

    def test_wider_anchor_spread_scores_better(self) -> None:
        opposite = self._score(a_bearing_deg=0.0, b_bearing_deg=180.0)
        narrow = self._score(a_bearing_deg=0.0, b_bearing_deg=40.0)
        assert opposite < narrow

    def test_seed_place_bonus(self) -> None:
        directional = self._score(a_kind="directional", b_kind="directional")
        one_seed = self._score(a_kind="seed_place", b_kind="directional")
        two_seed = self._score(a_kind="seed_place", b_kind="seed_place")
        assert one_seed == pytest.approx(directional - 3.0)
        assert two_seed == pytest.approx(directional - 6.0)

    def test_lower_score_is_better(self) -> None:
        # Distance error dominates: 1 km off costs 26 points, a full overlap
        # costs 100, so a clean on-target loop must beat a clean 4 km miss.
        good = self._score(loop_distance_km=5.0, target_distance_km=5.0)
        bad = self._score(loop_distance_km=9.0, target_distance_km=5.0)
        assert good < bad
