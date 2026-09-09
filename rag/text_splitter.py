"""Split extracted document sections without losing their source metadata."""
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag.config import UserFacingError
from utils.prompts import source_location


def create_text_chunks(pages: list[dict], chunk_size: int = 1000,
                       chunk_overlap: int = 200) -> list[dict]:
    if not pages:
        return []
    if chunk_size < 1 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise UserFacingError("Chunk size must be positive and larger than the overlap.")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = []
    for page in pages:
        text = page.get("text", "").strip()
        if not text:
            continue
        for passage in splitter.split_text(text):
            chunk = dict(page)
            chunk.update(id=len(chunks), text=passage, location=source_location(page))
            chunks.append(chunk)
    return chunks
