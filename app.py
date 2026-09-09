"""Cortex Research AI — document research workspace."""
import hashlib
import streamlit as st
from auth.ui import require_user
from rag.config import ROOT, public_error, GENERATION_MODEL, has_api_key, UserFacingError
from rag.document_processor import process_uploads, SUPPORTED_EXTENSIONS
from rag.text_splitter import create_text_chunks
from rag.vector_store import build_vector_store
from rag.rag_pipeline import run_rag_pipeline
from rag.summary_generator import generate_paper_summary

st.set_page_config(page_title="Cortex Research AI", page_icon="🧠", layout="wide")
st.markdown("<style>" + (ROOT / "styles.css").read_text(encoding="utf-8") + "</style>", unsafe_allow_html=True)
current_user = require_user()
state = st.session_state
for key, value in {"chat_history": [], "paper_summary": None, "upload_signature": None,
                   "uploader_version": 0, "upload_errors": [], "upload_warnings": []}.items():
    if key not in state:
        state[key] = value

def location(source):
    return source.get("location", f'Page {source["page_number"]}')

def clear_documents():
    for key in ("extracted_pages", "stored_chunks", "vector_index"):
        state.pop(key, None)
    state.chat_history = []
    state.paper_summary = None
    state.upload_errors = []
    state.upload_warnings = []

def show_sources(sources):
    with st.expander("Evidence and source references"):
        st.caption("Retrieval similarity measures text relevance; it is not AI confidence.")
        for number, source in enumerate(sources, 1):
            st.text(f'Source {number} · {source["source"]} · {location(source)}')
            st.caption(f'Cosine similarity: {source.get("similarity_score", 0):.3f}')
            st.text(source["text"])

with st.sidebar:
    st.markdown("### 🧠 Cortex Research AI")
    st.caption("Your research, with evidence.")
    st.divider()
    st.markdown("**1 · Add your documents**")
    uploaded = st.file_uploader("Research documents", type=SUPPORTED_EXTENSIONS, accept_multiple_files=True,
                                key=f"papers_{state.uploader_version}")
    st.caption("PDF, DOCX, TXT, MD, CSV, TSV, JSON, XLSX, PNG, JPG, WebP")
    st.caption("Up to 10 files · 20 MB each · 50 MB total")
    use_ocr = st.checkbox("Read scans and images with AI", value=True,
                         help="Sends images or scanned pages to Gemini. Adds API calls and processing time.")
    signature = (tuple((f.name, hashlib.sha256(f.getvalue()).hexdigest()) for f in (uploaded or [])), use_ocr)
    if signature != state.upload_signature:
        clear_documents()
        state.upload_signature = signature
    configured = has_api_key()
    if not configured:
        st.warning("Gemini API key required")
        with st.expander("Set up your API key", expanded=True):
            st.markdown("**On your computer:** copy .env.example to .env and add your key.\n\n"
                        "**On Streamlit Cloud:** open App settings → Secrets and add:")
            st.code('GEMINI_API_KEY = "your_api_key_here"', language="toml")
            st.caption("Use your real key in the private settings, then restart the app.")
    if st.button("Process documents", type="primary", disabled=not uploaded or not configured, use_container_width=True):
        clear_documents()
        try:
            with st.status("Preparing your documents…", expanded=True) as progress:
                st.write("Reading files and recovering scanned text when needed…")
                result = process_uploads(uploaded, use_ocr=use_ocr)
                state.upload_errors = result["errors"]
                state.upload_warnings = result["warnings"]
                pages = result["pages"]
                if not pages:
                    raise UserFacingError("No readable files were found. Check the upload details below.")
                st.write("Creating searchable passages…")
                chunks = create_text_chunks(pages)
                if len(chunks) > 5000:
                    raise UserFacingError("Too much text for one session. Upload fewer documents.")
                st.write(f"Indexing {len(chunks)} passages with Gemini…")
                index, stored = build_vector_store(chunks)
                state.extracted_pages = pages
                state.stored_chunks = stored
                state.vector_index = index
                progress.update(label="Documents ready", state="complete", expanded=False)
        except Exception as error:
            st.error(public_error(error))
    st.divider()
    if st.button("Clear chat", use_container_width=True):
        state.chat_history = []
    if st.button("Clear summary", use_container_width=True):
        state.paper_summary = None
    if st.button("Reset workspace", use_container_width=True):
        clear_documents()
        state.uploader_version += 1
        state.upload_signature = None
        st.rerun()
    st.caption("Document text, scanned pages, images and questions are sent to Google Gemini. "
               "This app keeps your workspace in session memory and does not save uploads.")
    st.caption(f"Generation: {GENERATION_MODEL}")

st.caption("RESEARCH INTELLIGENCE")
st.title("Cortex Research AI")
st.markdown("Read deeper. Ask better questions. **Follow the evidence.**")
st.caption("Ask questions across your documents, create structured summaries, and inspect the original evidence.")

if state.upload_errors or state.upload_warnings:
    with st.expander("Upload details", expanded=bool(state.upload_errors)):
        for message in state.upload_errors:
            st.warning(message)
        for message in state.upload_warnings:
            st.info(message)

if "vector_index" not in state:
    st.info("Add documents in the sidebar, then select Process documents.")
    a, b, c = st.columns(3)
    a.markdown("### 01 · Collect\nBring papers, notes, tables and scans into one workspace.")
    b.markdown("### 02 · Understand\nAsk questions or generate a structured summary of each document.")
    c.markdown("### 03 · Verify\nTrace answers to pages, sections, or spreadsheet rows.")
else:
    cols = st.columns(4)
    cols[0].metric("Documents", len(set(p["source"] for p in state.extracted_pages)))
    cols[1].metric("Pages / sections", len(state.extracted_pages))
    cols[2].metric("Passages", len(state.stored_chunks))
    cols[3].metric("Words", f'{sum(len(p["text"].split()) for p in state.extracted_pages):,}')
    chat_tab, summary_tab, explorer_tab = st.tabs(["Ask your documents", "Document summaries", "Document explorer"])
    with chat_tab:
        st.subheader("From question to evidence")
        st.caption("Try: What are the main findings? Explain the methods. What limitations are mentioned?")
        for chat in state.chat_history:
            with st.chat_message("user"):
                st.markdown(chat["question"])
            with st.chat_message("assistant"):
                st.markdown(chat["answer"])
                show_sources(chat["sources"])
        question = st.chat_input("Ask about your documents…", max_chars=2000)
        if question:
            try:
                with st.spinner("Finding evidence and composing an answer…"):
                    result = run_rag_pipeline(question, state.vector_index, state.stored_chunks,
                                              history=state.chat_history)
                state.chat_history.append(result)
                st.rerun()
            except Exception as error:
                st.error(public_error(error))
        if state.chat_history:
            transcript = "\n\n".join("## " + h["question"] + "\n\n" + h["answer"] +
                "\n\n" + "\n".join(f'[Source {i}] {s["source"]}, {location(s)}'
                                     for i, s in enumerate(h["sources"], 1)) for h in state.chat_history)
            st.download_button("Download conversation", transcript, "cortex-conversation.md", mime="text/markdown")
    with summary_tab:
        st.subheader("The essentials, document by document")
        st.caption("Covers every indexed passage. Long documents need multiple Gemini calls and may take several minutes.")
        if st.button("Generate document summaries", type="primary"):
            try:
                with st.spinner("Reading all sections and synthesizing summaries…"):
                    state.paper_summary = generate_paper_summary(state.stored_chunks)
            except Exception as error:
                st.error(public_error(error))
        if state.paper_summary:
            st.markdown(state.paper_summary)
            st.download_button("Download summary", state.paper_summary, "cortex-summary.md", mime="text/markdown")
    with explorer_tab:
        pages = state.extracted_pages
        selected = st.selectbox("Page or section", range(len(pages)),
            format_func=lambda i: f'{pages[i]["source"]} · {location(pages[i])}')
        st.text(pages[selected]["text"])
st.divider()
st.caption("Cortex Research AI · Verify important claims against the original. AI answers and scan transcriptions can contain errors.")
