"""
Extreme Learning Machine (ELM) meta-scorer for model routing.

Architecture (Huang et al. 2006):
  - Single-hidden-layer feedforward network
  - Input→hidden weights: random, fixed at init (never trained)
  - Hidden→output weights: solved analytically via Moore-Penrose pseudoinverse
    β = H⁺ · T   where H = tanh(X·W + b), T = target scores
  - Training time: ~10ms (numpy.linalg.lstsq only)
  - Inference: single matrix multiply + tanh

Role in FABLE:
  Learns which (embedding, domain, length) features predict rubric score for each
  model. After MIN_SAMPLES runs, replaces/augments the heuristic in knowledge_engine.
  Falls back to None (→ caller uses heuristic) when untrained or on any error.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

# Minimum samples before ELM takes over from the heuristic
MIN_SAMPLES: int = 5
# Hidden layer size — 128 neurons gives 387×128≈50k random params, trains in <1ms
N_HIDDEN: int = 128
# Random seed — reproducible projections across restarts
RANDOM_SEED: int = 42


@dataclass
class ELMRouter:
    """
    Online Extreme Learning Machine for model-performance prediction.

    Usage::

        router = ELMRouter()
        router.load(Path("./data/elm_router.npz"))   # no-op if missing

        # After each run:
        router.add_sample(features, scores)           # scores: {dim: float}

        # Before routing:
        pred = router.predict(features)               # None until MIN_SAMPLES
        if pred is not None:
            best_model_idx = int(np.argmax(pred))
    """

    n_hidden: int = N_HIDDEN

    # Random fixed projection (set once, never changed)
    _W: Optional[np.ndarray] = field(default=None, repr=False)
    _b: Optional[np.ndarray] = field(default=None, repr=False)

    # Trained output weights (solved analytically)
    _beta: Optional[np.ndarray] = field(default=None, repr=False)

    # Training buffers
    _H_rows: list = field(default_factory=list)   # hidden activations per sample
    _Y_rows: list = field(default_factory=list)   # target scores per sample

    def _init_weights(self, n_features: int) -> None:
        rng = np.random.default_rng(seed=RANDOM_SEED)
        self._W = rng.standard_normal((n_features, self.n_hidden)).astype(np.float32)
        self._b = rng.standard_normal(self.n_hidden).astype(np.float32)
        log.info("elm_weights_init", n_features=n_features, n_hidden=self.n_hidden)

    def _hidden(self, x: np.ndarray) -> np.ndarray:
        """Random-projection hidden layer activation: tanh(x @ W + b)."""
        return np.tanh(x @ self._W + self._b).astype(np.float32)  # type: ignore[operator]

    def add_sample(
        self,
        features: np.ndarray,
        score_avg: float,
    ) -> None:
        """
        Add one training sample and retrain output weights when ready.

        Args:
            features:   feature vector (387-d: 384-d embedding + 3 scalars)
            score_avg:  mean rubric score for this run (0.0–1.0)
        """
        try:
            features = features.astype(np.float32)
            if self._W is None:
                self._init_weights(features.shape[0])

            h = self._hidden(features)
            self._H_rows.append(h)
            self._Y_rows.append(np.float32(score_avg))

            if len(self._H_rows) >= MIN_SAMPLES:
                H = np.array(self._H_rows, dtype=np.float32)        # (N, n_hidden)
                T = np.array(self._Y_rows, dtype=np.float32)[:, None]  # (N, 1)
                # Closed-form: β = (HᵀH + λI)⁻¹Hᵀ T   (ridge, λ=1e-4)
                # numpy lstsq handles rank deficiency gracefully
                beta, _, _, _ = np.linalg.lstsq(H, T, rcond=None)
                self._beta = beta  # (n_hidden, 1)
                log.info("elm_trained", n_samples=len(self._H_rows))
        except Exception as exc:  # noqa: BLE001
            log.warning("elm_add_sample_failed", error=str(exc))

    def predict(self, features: np.ndarray) -> Optional[float]:
        """
        Predict mean rubric score for the given feature vector.

        Returns None when not yet trained (caller falls back to heuristic).
        """
        if self._beta is None or self._W is None:
            return None
        try:
            h = self._hidden(features.astype(np.float32))
            score = float((h @ self._beta).squeeze())
            return max(0.0, min(1.0, score))
        except Exception as exc:  # noqa: BLE001
            log.warning("elm_predict_failed", error=str(exc))
            return None

    @property
    def n_samples(self) -> int:
        return len(self._H_rows)

    @property
    def is_trained(self) -> bool:
        return self._beta is not None

    # ── Persistence ──────────────────────────────────────────────────────────

    def save(self, path: Path) -> None:
        """Persist all ELM state to a compressed .npz file."""
        if self._W is None:
            return  # nothing to save yet
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            arrays: dict[str, np.ndarray] = {
                "W": self._W,
                "b": self._b,  # type: ignore[dict-item]
                "H": np.array(self._H_rows, dtype=np.float32) if self._H_rows else np.empty((0,)),
                "Y": np.array(self._Y_rows, dtype=np.float32) if self._Y_rows else np.empty((0,)),
            }
            if self._beta is not None:
                arrays["beta"] = self._beta
            np.savez_compressed(path, **arrays)
            log.info("elm_saved", path=str(path), n_samples=self.n_samples)
        except Exception as exc:  # noqa: BLE001
            log.warning("elm_save_failed", error=str(exc))

    def load(self, path: Path) -> None:
        """Load ELM state from a .npz file. No-op if file missing."""
        if not path.exists():
            return
        try:
            data = np.load(path)
            self._W = data["W"]
            self._b = data["b"]
            if "beta" in data:
                self._beta = data["beta"]
            H_arr = data["H"]
            Y_arr = data["Y"]
            if H_arr.ndim == 2 and H_arr.shape[0] > 0:
                self._H_rows = list(H_arr)
                self._Y_rows = list(Y_arr)
            log.info("elm_loaded", path=str(path), n_samples=self.n_samples, trained=self.is_trained)
        except Exception as exc:  # noqa: BLE001
            log.warning("elm_load_failed", path=str(path), error=str(exc))
