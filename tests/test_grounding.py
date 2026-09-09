"""Regression checks for multi-format source references and conversational retrieval."""
import re
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rag.config import UserFacingError
from rag import rag_pipeline as rp, summary_generator as sg
from rag.text_splitter import create_text_chunks
from utils.prompts import build_research_prompt, source_citation


def section(source="notes.txt", location="Section 1", text="The result is 92 percent."):
    return {"source": source, "location": location, "page_number": 1, "text": text}


def test_sheet_location_survives_chunking_and_prompt():
    original = section("data.xlsx", "Sheet Results, rows 1–40", "value " * 400)
    original["extraction"] = "local"
    chunks = create_text_chunks([original], chunk_size=100, chunk_overlap=20)
    assert len(chunks) > 1
    assert all(c["location"] == original["location"] for c in chunks)
    assert all(c["extraction"] == "local" for c in chunks)
    assert original["text"] == "value " * 400
    prompt = build_research_prompt("What are the results?", chunks[:1])
    assert "Location: Sheet Results, rows 1–40" in prompt
    assert "Location: Page 1" not in prompt


def test_old_pdf_chunks_keep_page_references():
    chunk = {"source": "paper.pdf", "page_number": 7, "text": "Findings."}
    assert source_citation(chunk) == "[paper.pdf, Page 7]"
    assert create_text_chunks([chunk])[0]["location"] == "Page 7"


def test_independent_question_uses_new_topic_only(monkeypatch):
    old = section("agriculture.pdf", "Page 1", "Rice yield was 12 tons.")
    current = section("energy.pdf", "Page 1", "The solar panel output was 400 W.")
    queries, prompts = [], []

    def retrieve(query, *args):
        queries.append(query)
        return [old if "rice" in query.lower() else current]

    def generate(prompt, *args):
        prompts.append(prompt)
        return "Output was 400 W. [Source 1]"

    monkeypatch.setattr(rp, "search_vector_store", retrieve)
    monkeypatch.setattr(rp, "generate_text", generate)
    history = [{"question": "What was the rice yield?", "answer": "12 tons. [Source 1]"}]
    result = rp.run_rag_pipeline("What was the solar panel output?", None,
                                 [old, current], history=history)
    assert result["sources"][0]["source"] == "energy.pdf"
    assert queries == ["What was the solar panel output?"]
    assert "rice" not in prompts[0]


def test_follow_up_uses_prior_subject_without_reusing_citations(monkeypatch):
    queries, prompts = [], []
    chunks = [section()]
    monkeypatch.setattr(rp, "search_vector_store",
                        lambda query, *args: queries.append(query) or chunks)
    monkeypatch.setattr(rp, "generate_text",
                        lambda prompt, *args: prompts.append(prompt) or "It was small. [Source 1]")
    result = rp.run_rag_pipeline(
        "What were its limitations?", None, chunks,
        history=[{"question": "What did the solar experiment measure?",
                  "answer": "The panel output. [Source 7]"}],
    )
    assert "solar experiment" in queries[0]
    assert "[Source 7]" not in queries[0]
    assert "must not be reused" in prompts[0]
    assert "[Source 1]" in result["answer"]


def test_explicit_file_question_does_not_reuse_history():
    assert not rp.is_follow_up("What does this chart in energy.pdf show?",
                              [section("energy.pdf")])


@pytest.mark.parametrize("answer", [
    "Valid [Source 1] but invented [Source 99]",
    "Valid [Source 1] but malformed [Source 2, 3]",
    "Valid [Source 1] but unfinished [Source 2",
])
def test_partly_valid_chat_citations_are_withheld(monkeypatch, answer):
    monkeypatch.setattr(rp, "generate_text", lambda *args: answer)
    assert rp.generate_research_answer("Question?", [section()]) == rp.INSUFFICIENT


def test_summary_corrects_invalid_location_once(monkeypatch):
    generate = Mock(side_effect=["Finding [data.xlsx, Page 1]",
                                "Finding [data.xlsx, Sheet Results, rows 1–40]"])
    monkeypatch.setattr(sg, "generate_text", generate)
    result = sg.generate_paper_summary([section("data.xlsx", "Sheet Results, rows 1–40")])
    assert "[data.xlsx, Sheet Results, rows 1–40]" in result
    assert "[data.xlsx, Page 1]" not in result
    assert generate.call_count == 2


@pytest.mark.parametrize("answer", [
    "Finding without a reference",
    "Finding [different.txt, Section 1]",
    "Finding [notes.txt, Section 99]",
    "Valid [notes.txt, Section 1] and invented [other.txt, Section 9]",
])
def test_summary_never_displays_unmatched_references(monkeypatch, answer):
    generate = Mock(return_value=answer)
    monkeypatch.setattr(sg, "generate_text", generate)
    with pytest.raises(UserFacingError, match="valid document references"):
        sg.generate_paper_summary([section()])
    assert generate.call_count == 2


def test_brackets_in_filename_are_validated_as_part_of_exact_reference(monkeypatch):
    monkeypatch.setattr(sg, "generate_text", lambda *args: "Result [notes [final].txt, Section 1]")
    result = sg.generate_paper_summary([section("notes [final].txt")])
    assert "[notes [final].txt, Section 1]" in result


def test_hierarchical_summary_checks_each_batch_and_preserves_later_evidence(monkeypatch):
    seen = []

    def summarize(prompt, *args):
        evidence = prompt.split("Evidence:\n", 1)[1]
        seen.append(evidence)
        citations = list(dict.fromkeys(re.findall(r"\[[^\[\]\n]+\]", evidence)))
        return "Findings " + " ".join(citations)

    monkeypatch.setattr(sg, "generate_text", summarize)
    chunks = [section("notes.txt", f"Section {i}", f"EVIDENCE_{i} " + "x" * 10000)
              for i in range(1, 8)]
    result = sg.generate_paper_summary(chunks)
    assert any("EVIDENCE_7" in evidence for evidence in seen)
    assert "[notes.txt, Section 7]" in result
    assert len(seen) > 4


def test_generation_keeps_default_sampling_and_closes_client(monkeypatch):
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(text="Answer", candidates=[])
    monkeypatch.setattr(rp, "get_generation_client", lambda: client)
    assert rp.generate_text("Question") == "Answer"
    assert client.models.generate_content.call_args.kwargs["config"].temperature is None
    client.close.assert_called_once()


def test_generation_rejects_truncated_output(monkeypatch):
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(
        text="Unfinished", candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")])
    monkeypatch.setattr(rp, "get_generation_client", lambda: client)
    with pytest.raises(UserFacingError, match="length limit"):
        rp.generate_text("Question")
    client.close.assert_called_once()
