from rag.config import UserFacingError
"""Normalized Gemini embeddings and an in-memory FAISS cosine index."""
import faiss
import numpy as np
from google.genai import types
from rag.config import get_client, EMBEDDING_MODEL, EMBEDDING_DIMENSION

get_gemini_client = get_client

def normalize_embedding(embedding):
    vector = np.asarray(embedding, dtype="float32").reshape(1, -1)
    if vector.shape[1] != EMBEDDING_DIMENSION or not np.isfinite(vector).all() or np.linalg.norm(vector) == 0:
        raise UserFacingError("Gemini returned an invalid embedding.")
    faiss.normalize_L2(vector)
    return vector

def _embed(client, texts, task):
    response = client.models.embed_content(
        model=EMBEDDING_MODEL, contents=texts,
        config=types.EmbedContentConfig(task_type=task, output_dimensionality=EMBEDDING_DIMENSION))
    if not response.embeddings or len(response.embeddings) != len(texts):
        raise UserFacingError("Gemini returned an incomplete embedding batch.")
    return np.vstack([normalize_embedding(e.values) for e in response.embeddings])

def create_document_embedding(client, text):
    return _embed(client, [text], "RETRIEVAL_DOCUMENT")

def create_query_embedding(client, question):
    return _embed(client, [question], "RETRIEVAL_QUERY")

def build_vector_store(chunks):
    stored = [c.copy() for c in chunks if c.get("text", "").strip()]
    if not stored:
        raise UserFacingError("No readable text chunks were provided.")
    index = faiss.IndexFlatIP(EMBEDDING_DIMENSION)
    client = get_gemini_client()
    try:
        for offset in range(0, len(stored), 32):
            index.add(_embed(client, [c["text"] for c in stored[offset:offset+32]], "RETRIEVAL_DOCUMENT"))
    finally:
        client.close()
    return index, stored

def search_vector_store(question, index, chunks, top_k=5):
    if not question.strip():
        raise UserFacingError("Please enter a question.")
    if top_k < 1 or index.ntotal == 0 or index.ntotal != len(chunks):
        raise UserFacingError("Invalid index or retrieval count. Reprocess your papers.")
    client = get_gemini_client()
    try:
        query = create_query_embedding(client, question)
    finally:
        client.close()
    scores, positions = index.search(query, min(top_k, index.ntotal))
    return [dict(chunks[int(i)], similarity_score=float(s)) for s, i in zip(scores[0], positions[0]) if i >= 0]
