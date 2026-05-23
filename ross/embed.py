"""Local embeddings (fastembed / BGE-small, 384-dim, ONNX — no GPU, no API).

Lazy-loads the model so importing this module stays cheap.
"""
from functools import lru_cache

from ross.config import EMBED_MODEL


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=EMBED_MODEL)


def embed(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _model().embed(texts)]


def embed_one(text: str) -> list[float]:
    return embed([text])[0]
