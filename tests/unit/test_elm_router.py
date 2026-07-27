"""
Tests for the ELM meta-scorer's persistence contract (Phase 11).

Covers the save/load round-trip and the geometry guard that stops a changed
ELM_ROUTER_N_HIDDEN from restoring weights of the wrong shape.
"""
from __future__ import annotations

import numpy as np

from backend.core.elm_router import ELMRouter

N_FEATURES = 16


def _train(router: ELMRouter, n_samples: int) -> None:
    rng = np.random.default_rng(0)
    for _ in range(n_samples):
        router.add_sample(rng.random(N_FEATURES).astype(np.float32), float(rng.random()))


def test_untrained_predict_returns_none():
    r = ELMRouter(n_hidden=8, min_samples=5)
    assert r.predict(np.zeros(N_FEATURES, dtype=np.float32)) is None
    assert r.is_trained is False


def test_trains_at_min_samples():
    r = ELMRouter(n_hidden=8, min_samples=5)
    _train(r, 4)
    assert r.is_trained is False   # one short
    _train(r, 1)
    assert r.is_trained is True
    assert 0.0 <= r.predict(np.zeros(N_FEATURES, dtype=np.float32)) <= 1.0


def test_save_load_roundtrip_preserves_predictions(tmp_path):
    path = tmp_path / "elm.npz"
    r1 = ELMRouter(n_hidden=8, min_samples=5)
    _train(r1, 6)
    r1.save(path)

    probe = np.random.default_rng(7).random(N_FEATURES).astype(np.float32)
    r2 = ELMRouter(n_hidden=8, min_samples=5)
    r2.load(path)

    assert r2.is_trained is True
    assert r2.n_samples == r1.n_samples
    assert r2.predict(probe) == r1.predict(probe)


def test_load_skips_when_n_hidden_changed(tmp_path):
    """A stale .npz written at a different n_hidden must be ignored, not restored
    into a shape-mismatched matmul that crashes later inside predict()."""
    path = tmp_path / "elm.npz"
    r1 = ELMRouter(n_hidden=8, min_samples=5)
    _train(r1, 6)
    r1.save(path)

    r2 = ELMRouter(n_hidden=32, min_samples=5)   # config changed since that save
    r2.load(path)

    assert r2.is_trained is False        # weights discarded, will retrain
    assert r2.n_samples == 0
    # Still usable afterwards: retraining at the new geometry works.
    _train(r2, 6)
    assert r2.is_trained is True
    assert r2.predict(np.zeros(N_FEATURES, dtype=np.float32)) is not None


def test_load_missing_file_is_noop(tmp_path):
    r = ELMRouter(n_hidden=8, min_samples=5)
    r.load(tmp_path / "does-not-exist.npz")
    assert r.is_trained is False
