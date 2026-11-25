"""
Frozen UniXcoder text encoder for the similarity features.

Frozen identity (recorded in every feature file that uses it):
  model     microsoft/unixcoder-base
  revision  5604afdc964f6c53782a6813140ade5216b99006 (pinned; never trained)
  pooling   mean of the last hidden layer over non-padding tokens
  max_len   256 tokens, truncation on the right
Embeddings are cached on disk by sha256(text) so repeated runs are identical.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

MODEL_ID = "microsoft/unixcoder-base"
REVISION = "5604afdc964f6c53782a6813140ade5216b99006"
MAX_LEN = 256
IDENTITY = {"model": MODEL_ID, "revision": REVISION, "pooling": "mean_last_hidden", "max_len": MAX_LEN}


class FrozenEncoder:
    def __init__(self, cache_dir):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._tok = self._model = None

    def _load(self):
        if self._model is None:
            self._tok = AutoTokenizer.from_pretrained(MODEL_ID, revision=REVISION)
            self._model = AutoModel.from_pretrained(MODEL_ID, revision=REVISION)
            self._model.eval().to("cuda" if torch.cuda.is_available() else "cpu")

    def _path(self, text):
        return self.cache_dir / (hashlib.sha256(text.encode("utf-8")).hexdigest() + ".npy")

    @torch.no_grad()
    def encode(self, texts, batch_size=32):
        out = [None] * len(texts)
        todo = []
        for i, t in enumerate(texts):
            p = self._path(t)
            if p.exists():
                out[i] = np.load(p)
            else:
                todo.append(i)
        if todo:
            self._load()
            dev = self._model.device
            for s in range(0, len(todo), batch_size):
                idx = todo[s:s + batch_size]
                enc = self._tok([texts[i] for i in idx], return_tensors="pt", padding=True,
                                truncation=True, max_length=MAX_LEN).to(dev)
                hidden = self._model(**enc).last_hidden_state
                m = enc["attention_mask"].unsqueeze(-1).float()
                vec = ((hidden * m).sum(1) / m.sum(1).clamp(min=1e-9)).float().cpu().numpy()
                for j, i in enumerate(idx):
                    out[i] = vec[j]
                    np.save(self._path(texts[i]), vec[j])
        return np.vstack(out)


def cosine(a, b):
    a = a / np.maximum(np.linalg.norm(a, axis=-1, keepdims=True), 1e-12)
    b = b / np.maximum(np.linalg.norm(b, axis=-1, keepdims=True), 1e-12)
    return a @ b.T


def identity_json():
    return json.dumps(IDENTITY, sort_keys=True)
