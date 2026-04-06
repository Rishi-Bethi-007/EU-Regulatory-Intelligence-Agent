from sentence_transformers import SentenceTransformer
from config.settings import EMBEDDING_MODEL

# Load once at module level — never reload per call
# First call downloads the model (~2GB), subsequent calls use cache
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print(f"Loading embedding model: {EMBEDDING_MODEL}")
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed_query(text: str) -> list[float]:
    """
    Embed a search query.
    e5 models require 'query: ' prefix for queries — never skip this.
    """
    model = get_model()
    return model.encode(f"query: {text}").tolist()


def embed_passage(text: str) -> list[float]:
    """
    Embed a document chunk.
    e5 models require 'passage: ' prefix for passages — never skip this.
    """
    model = get_model()
    return model.encode(f"passage: {text}").tolist()


def embed_passages_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed multiple passages at once.
    Much faster than calling embed_passage() one by one.
    Use this during ingestion when loading many chunks.
    """
    model = get_model()
    return model.encode(
        [f"passage: {t}" for t in texts],
        batch_size=32,
        show_progress_bar=True
    ).tolist()
