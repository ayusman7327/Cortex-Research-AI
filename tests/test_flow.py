from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import pytest
from reportlab.pdfgen import canvas
from rag.pdf_processor import extract_text_from_multiple_pdfs, extract_text_from_pdf
from rag.text_splitter import create_text_chunks
from rag import vector_store as vs, rag_pipeline as rp, summary_generator as sg
from rag.config import public_error

def pdf(name="paper.pdf", text="The experiment measured 92 percent accuracy."):
    stream = BytesIO()
    doc = canvas.Canvas(stream)
    doc.drawString(40, 750, text)
    doc.showPage()
    doc.drawString(40, 750, "The limitation is a small dataset.")
    doc.save()
    stream.name = name
    return stream

@pytest.fixture
def client(monkeypatch):
    obj = Mock()
    def embed(**kwargs):
        vectors = []
        for text in kwargs["contents"]:
            v = np.zeros(768)
            v[0 if "accuracy" in text else 1] = 1
            vectors.append(SimpleNamespace(values=v.tolist()))
        return SimpleNamespace(embeddings=vectors)
    obj.models.embed_content.side_effect = embed
    monkeypatch.setattr(vs, "get_gemini_client", lambda: obj)
    return obj

def test_pdf_to_rag(client, monkeypatch):
    pages = extract_text_from_multiple_pdfs([pdf()])
    assert [p["page_number"] for p in pages] == [1, 2]
    chunks = create_text_chunks(pages)
    index, stored = vs.build_vector_store(chunks)
    monkeypatch.setattr(rp, "generate_text", lambda *a: "Accuracy is 92 percent. [Source 1]")
    result = rp.run_rag_pipeline("What accuracy?", index, stored)
    assert result["sources"][0]["page_number"] == 1
    assert result["sources"][0]["source"] == "paper.pdf"
    assert result["sources"][0]["similarity_score"] == pytest.approx(1)
    assert "[Source 1]" in result["answer"]
    assert client.close.call_count == 2
    assert client.models.embed_content.call_args.kwargs["config"].task_type == "RETRIEVAL_QUERY"

def test_invalid_pdfs():
    bad = BytesIO(b"not a pdf"); bad.name = "bad.pdf"
    with pytest.raises(ValueError):
        extract_text_from_pdf(bad)
    with pytest.raises(ValueError, match="unique"):
        extract_text_from_multiple_pdfs([pdf(), pdf()])

def test_blank_pdf():
    from pypdf import PdfWriter
    data = BytesIO(); writer = PdfWriter(); writer.add_blank_page(100, 100); writer.write(data)
    data.name = "scan.pdf"
    with pytest.raises(ValueError, match="selectable"):
        extract_text_from_pdf(data)

def test_invalid_vectors():
    for v in ([0]*768, [1]*2, [float("nan")]*768):
        with pytest.raises(ValueError):
            vs.normalize_embedding(v)

def test_cleanup_on_embedding_failure(client):
    client.models.embed_content.side_effect = RuntimeError("failed")
    with pytest.raises(RuntimeError):
        vs.build_vector_store([{"text": "test"}])
    client.close.assert_called_once()

def test_invalid_retrieval(client):
    index, chunks = vs.build_vector_store([{"text": "accuracy"}])
    with pytest.raises(ValueError):
        vs.search_vector_store("test", index, chunks, 0)
    with pytest.raises(ValueError):
        vs.search_vector_store(" ", index, chunks)

@pytest.mark.parametrize("answer", ["Invented answer", "Claim [Source 99]", "Claim [Source 0]"])
def test_bad_citations_withheld(monkeypatch, answer):
    monkeypatch.setattr(rp, "generate_text", lambda *a: answer)
    assert rp.generate_research_answer("Question", [{"source": "p", "page_number": 1, "text": "fact"}]) == rp.INSUFFICIENT

def test_summary_covers_late_pages_and_each_paper(monkeypatch):
    prompts = []
    def generate(prompt, *args):
        prompts.append(prompt)
        return "Summary " + __import__("re").findall(r"\[[^\]\n]+, (?:Page|Section) [^\]\n]+\]", prompt.split("Evidence:" + chr(10))[-1])[0]
    monkeypatch.setattr(sg, "generate_text", generate)
    chunks = [{"source": "paper.pdf", "page_number": i+1, "text": str(i)+"x"*1000} for i in range(60)]
    chunks.append({"source": "second.pdf", "page_number": 1, "text": "UNIQUE_SECOND_PAPER"})
    chunks[-2]["text"] += "FINAL_PAGE_EVIDENCE"
    summary = sg.generate_paper_summary(chunks)
    assert any("FINAL_PAGE_EVIDENCE" in p for p in prompts)
    assert any("UNIQUE_SECOND_PAPER" in p for p in prompts)
    assert "second.pdf" in summary
    assert len(prompts) > 3

def test_api_cleanup(monkeypatch):
    client = Mock()
    client.models.generate_content.side_effect = RuntimeError("secret payload")
    monkeypatch.setattr(rp, "get_generation_client", lambda: client)
    with pytest.raises(RuntimeError):
        rp.generate_text("test")
    client.close.assert_called_once()
    assert "secret" not in public_error(RuntimeError("secret"))

def test_app_initial_and_reset(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    at = authenticated_app(monkeypatch, tmp_path)
    assert not at.exception
    assert at.title[0].value == "Cortex Research AI"
    next(b for b in at.button if b.label == "Reset workspace").click().run()
    assert not at.exception
    assert at.session_state["chat_history"] == []


def test_app_processed_chat_summary_and_upload_change(client, monkeypatch, tmp_path):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    uploads = [pdf()]
    monkeypatch.setenv("GEMINI_API_KEY", "offline-test-key")
    monkeypatch.setattr(st, "file_uploader", lambda *a, **kw: uploads)
    monkeypatch.setattr(rp, "generate_text", lambda *a: "Accuracy is 92 percent. [Source 1]")
    monkeypatch.setattr(sg, "generate_text", lambda *a: "Findings [paper.pdf, Page 1]")
    at = authenticated_app(monkeypatch, tmp_path)
    next(b for b in at.button if b.label == "Process documents").click().run()
    assert not at.exception
    assert len(at.metric) == 4
    at.chat_input[0].set_value("What accuracy?").run()
    assert not at.exception
    assert len(at.session_state["chat_history"]) == 1
    next(b for b in at.button if b.label == "Generate document summaries").click().run()
    assert "Findings" in at.session_state["paper_summary"]
    next(b for b in at.button if b.label == "Clear chat").click().run()
    assert at.session_state["chat_history"] == []
    uploads.clear()
    at.run()
    assert not at.exception
    assert at.session_state["paper_summary"] is None
    assert len(at.chat_input) == 0

def authenticated_app(monkeypatch, tmp_path):
    from auth.service import AuthStore
    from auth import ui
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    store = AuthStore(tmp_path / "auth.sqlite3")
    store.register("researcher", "Researcher", "a strong test password")
    token = store.login("researcher", "a strong test password")
    monkeypatch.setattr(ui, "_store", lambda: store)
    monkeypatch.setattr(ui, "_mode", lambda: "local")
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
    at.session_state["_auth_token"] = token
    return at.run(timeout=30)