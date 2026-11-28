"""
Preprocessing and the two planned baselines (Simul's README, section 5).

Preprocessing (fit on training rows only, saved with each model):
  numeric      median imputation + one missing-indicator column for every
               feature that has missing values in training; then
               standardisation (mean 0, sd 1) for logistic regression
  categorical  syntax_kind one-hot over the training vocabulary; unseen
               kinds map to an all-zero "other"
  LightGBM     receives the same columns but WITHOUT imputation or scaling:
               missing values stay NaN and use LightGBM's own handling

Models:
  LightGBM LambdaMART  LGBMRanker(objective="lambdarank"); rows sorted so each
                       case is contiguous; group sizes rebuilt from the
                       training rows; labels 0/1
  L2 logistic reg.     lbfgs, C=1.0; per-case sample weights so every case
                       weighs 1 in total (bug line 0.5, other lines share
                       0.5), which also balances the 1-vs-358 classes
  Neural ranker        (workbook ch. 7.3) small MLP on the same standardised
                       columns as logistic regression: in -> 32 -> 16 -> 1,
                       ReLU, dropout 0.1. Pairwise ranking loss within each
                       case: mean over (bug line, other line) pairs of
                       softplus(score_other - score_bug); every case weighs
                       the same. Adam, lr 1e-3, weight decay 1e-4, fixed 300
                       epochs, CPU, seeded (no early stopping: the starter has
                       no valid internal development group).
Fixed settings for the starter package (no tuning: only one lineage). All
hyperparameters and default seeds are read from model_config.json, which is
copied into every run folder.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
from lightgbm import LGBMRanker
from sklearn.linear_model import LogisticRegression

CONFIG_PATH = Path(__file__).resolve().parent / "model_config.json"
CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
CONFIG_SHA256 = hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()
DEFAULT_SEEDS = CONFIG["seeds"]
LGBM_PARAMS = dict(CONFIG["lgbm"])
LOGREG_PARAMS = {k: CONFIG["logreg"][k] for k in ("C", "solver", "max_iter")}
MLP_PARAMS = {k: CONFIG["mlp"][k] for k in ("hidden", "dropout", "lr", "weight_decay", "epochs")}


class Preprocessor:
    def fit(self, X, kinds):
        self.medians = np.array([np.nanmedian(X[:, j]) if (~np.isnan(X[:, j])).any() else 0.0
                                 for j in range(X.shape[1])])
        self.flag_cols = [j for j in range(X.shape[1]) if np.isnan(X[:, j]).any()]
        self.vocab = sorted(set(kinds))
        Z = self._assemble(self._impute(X), X, kinds)
        self.mean = Z.mean(axis=0)
        self.std = np.where(Z.std(axis=0) > 0, Z.std(axis=0), 1.0)
        return self

    def _impute(self, X):
        return np.where(np.isnan(X), self.medians, X)

    def _assemble(self, Xnum, Xraw, kinds):
        flags = np.isnan(Xraw[:, self.flag_cols]).astype(float) if self.flag_cols else np.zeros((len(Xraw), 0))
        onehot = np.array([[float(k == v) for v in self.vocab] for k in kinds]).reshape(len(kinds), len(self.vocab))
        return np.hstack([Xnum, flags, onehot])

    def for_logreg(self, X, kinds):
        return (self._assemble(self._impute(X), X, kinds) - self.mean) / self.std

    def for_lgbm(self, X, kinds):
        return self._assemble(X, X, kinds)          # NaN kept for LightGBM

    def column_names(self, names):
        return list(names) + [f"missing:{names[j]}" for j in self.flag_cols] + [f"kind:{v}" for v in self.vocab]


def case_weights(case_index, y):
    w = np.zeros(len(y))
    for c in np.unique(case_index):
        m = case_index == c
        pos, neg = (m & (y == 1)), (m & (y == 0))
        if pos.any():
            w[pos] = 0.5 / pos.sum()
        if neg.any():
            w[neg] = 0.5 / neg.sum()
    return w


def make_logreg(seed):
    try:
        return LogisticRegression(l1_ratio=0.0, random_state=seed, **LOGREG_PARAMS)   # newer sklearn: L2
    except TypeError:
        return LogisticRegression(penalty="l2", random_state=seed, **LOGREG_PARAMS)


def fit_logreg(Z, y, case_index, seed):
    m = make_logreg(seed)
    m.fit(Z, y, sample_weight=case_weights(case_index, y))
    return m


def fit_lgbm(Z, y, case_index, seed):
    runs = [case_index[0]] + [b for a, b in zip(case_index[:-1], case_index[1:]) if a != b]
    if len(runs) != len(set(runs)):
        raise ValueError("training rows must be contiguous by case (a case appears twice)")
    sizes = [int(np.sum(case_index == c)) for c in runs]
    if sum(sizes) != len(y):
        raise ValueError("group sizes do not cover all rows")
    m = LGBMRanker(random_state=seed, **LGBM_PARAMS)
    m.fit(Z, y, group=sizes)
    return m


# ---------------------------------------------------------------- neural ranker
class NeuralRanker:
    """Small MLP scored with a within-case pairwise ranking loss."""

    def __init__(self, n_inputs, seed, params=MLP_PARAMS):
        import torch
        from torch import nn
        self.torch, self.params, self.seed = torch, dict(params), seed
        torch.manual_seed(seed)
        layers, prev = [], n_inputs
        for h in params["hidden"]:
            layers += [nn.Linear(prev, h), nn.ReLU(), nn.Dropout(params["dropout"])]
            prev = h
        layers.append(nn.Linear(prev, 1))
        self.net = nn.Sequential(*layers)
        self.loss_history = []

    def fit(self, Z, y, case_index):
        torch, p = self.torch, self.params
        torch.manual_seed(self.seed)
        X = torch.tensor(Z, dtype=torch.float32)
        cases = []
        for c in dict.fromkeys(case_index):
            m = np.where(case_index == c)[0]
            pos, neg = m[y[m] == 1], m[y[m] == 0]
            if len(pos) and len(neg):
                cases.append((torch.tensor(pos), torch.tensor(neg)))
        if not cases:
            raise ValueError("no case has both a bug line and other lines")
        opt = torch.optim.Adam(self.net.parameters(), lr=p["lr"], weight_decay=p["weight_decay"])
        self.net.train()
        for _ in range(p["epochs"]):
            opt.zero_grad()
            s = self.net(X).squeeze(-1)
            loss = torch.stack([torch.nn.functional.softplus(s[neg][None, :] - s[pos][:, None]).mean()
                                for pos, neg in cases]).mean()
            loss.backward()
            opt.step()
            self.loss_history.append(float(loss))
        return self

    def score(self, Z):
        torch = self.torch
        self.net.eval()
        with torch.no_grad():
            return self.net(torch.tensor(Z, dtype=torch.float32)).squeeze(-1).numpy().astype(float)

    def state(self):
        return {"state_dict": self.net.state_dict(), "params": self.params, "seed": self.seed,
                "n_inputs": self.net[0].in_features, "loss_history": self.loss_history}

    @classmethod
    def from_state(cls, state):
        m = cls(state["n_inputs"], state["seed"], state["params"])
        m.net.load_state_dict(state["state_dict"])
        m.loss_history = list(state.get("loss_history", []))
        return m


def fit_mlp(Z, y, case_index, seed):
    return NeuralRanker(Z.shape[1], seed).fit(Z, y, case_index)
