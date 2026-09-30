"""Tests for libs.review_store.ReviewStore (synthetic data only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from libs.review_store import ReviewStore


def _store(tmp_path: Path) -> ReviewStore:
    return ReviewStore(tmp_path / "reviews.db")


def test_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.set_decision(
            source_id="note-001",
            job_id="job-a",
            status="accepted",
            reviewer="reviewer.one",
            rationale="matches taxonomy on page 2",
            calibrated_score=0.82,
        )
        row = store.get("note-001")
        assert row is not None
        assert row["status"] == "accepted"
        assert row["reviewer"] == "reviewer.one"
        assert row["rationale"] == "matches taxonomy on page 2"
        assert row["calibrated_score"] == 0.82
    finally:
        store.close()


def test_each_decision_appends_event_but_current_is_latest(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.set_decision("note-002", "job-a", "pending", "reviewer.one")
        store.set_decision("note-002", "job-b", "accepted", "reviewer.two", "confirmed")

        events = store.events("note-002")
        assert len(events) == 2
        # newest first
        assert events[0]["status"] == "accepted"
        assert events[1]["status"] == "pending"

        current = store.all()
        assert set(current) == {"note-002"}
        assert current["note-002"]["status"] == "accepted"
        assert current["note-002"]["reviewer"] == "reviewer.two"
    finally:
        store.close()


def test_run_id_is_persisted(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.set_decision(
            "note-r", "job-a", "accepted", "reviewer.one", run_id="run-v1"
        )
        row = store.get("note-r")
        assert row is not None
        assert row["run_id"] == "run-v1"
        # a re-decision on a new version overwrites the stored run_id
        store.set_decision(
            "note-r", "job-b", "accepted", "reviewer.two", run_id="run-v2"
        )
        assert store.get("note-r")["run_id"] == "run-v2"
    finally:
        store.close()


def test_invalid_status_raises(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        with pytest.raises(ValueError):
            store.set_decision("note-003", "job-a", "maybe", "reviewer.one")
        # nothing persisted on the rejected call
        assert store.get("note-003") is None
        assert store.events("note-003") == []
    finally:
        store.close()


def test_all_keyed_by_source_id(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.set_decision("note-a", "job-a", "accepted", "reviewer.one")
        store.set_decision("note-b", "job-a", "rejected", "reviewer.two")
        store.set_decision("note-c", "job-a", "needs_info", "reviewer.one")

        current = store.all()
        assert set(current) == {"note-a", "note-b", "note-c"}
        assert current["note-b"]["status"] == "rejected"
        for source_id, row in current.items():
            assert row["source_id"] == source_id
    finally:
        store.close()


def test_get_missing_returns_none(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        assert store.get("does-not-exist") is None
    finally:
        store.close()


def test_events_all_newest_first(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.set_decision("note-x", "job-a", "pending", "reviewer.one")
        store.set_decision("note-y", "job-a", "accepted", "reviewer.two")
        all_events = store.events()
        assert len(all_events) == 2
        assert all_events[0]["source_id"] == "note-y"
        assert all_events[1]["source_id"] == "note-x"
    finally:
        store.close()
