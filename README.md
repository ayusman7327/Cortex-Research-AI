# Cortex Research AI

An authenticated research workspace built with Python, Streamlit, Google Gemini, and FAISS. Upload papers, notes, tables, and scans; ask questions, generate structured summaries, and inspect the sources behind each answer.

Start with [START_HERE.md](START_HERE.md) for the GitHub upload and deployment steps.

## Features

- Local account registration, login, logout, password changes, and recovery codes.
- Optional Google / OpenID Connect sign-in for cloud deployment.
- Authentication before document upload or AI processing, with an isolated workspace for each browser session.
- Multi-document extraction and overlapping passages that retain source locations.
- Batched Gemini embeddings and normalized FAISS cosine retrieval.
- Source-grounded chat, recent follow-up context, and inspectable evidence excerpts.
- Structured summaries covering every indexed passage through hierarchical synthesis.
- Citation-reference validation for answers and summaries.
- Session chat history, document explorer, and Markdown downloads.
- Streamlit Cloud secrets support, bounded API retries, and safe error messages.

## Supported uploads

| Format | What the app reads | Source reference |
| --- | --- | --- |
| PDF | Selectable text; AI reading for scanned pages with little native text | Original page |
| DOCX | Body paragraphs and tables in document order | Extracted section |
| TXT, MD | UTF-8 or UTF-16 text | Extracted section |
| CSV, TSV | Rows with first-row context | Row range |
| JSON | Valid JSON formatted as text | Extracted section |
| XLSX | Worksheets and saved cell values | Sheet and row range |
| PNG, JPG, JPEG, WebP | Gemini transcription and brief chart descriptions | Image section |

AI reading is enabled by default and can be switched off. It requires a Gemini key, sends images to Gemini, and adds API calls. Transcriptions may contain errors. PDF figures on pages with substantial native text and images embedded inside DOCX/XLSX are not automatically interpreted.

Damaged, empty, unsupported, or encrypted files are reported individually. Valid files in the same upload continue processing. Duplicate contents are skipped; repeated filenames receive distinct source names. Executables, ZIP archives, legacy DOC/XLS, presentations, audio, and video are not supported.

## Run on your computer

Requires Python 3.12, internet access, and a Gemini API key with embedding and generation quota. Local account creation itself does not require a Gemini key.

1. Extract the ZIP and open the **Cortex-Research-AI** folder.
2. Create and activate a virtual environment:

~~~powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
~~~

On macOS/Linux use `source .venv/bin/activate` and `cp .env.example .env`.

3. Set the new local `.env` file:

~~~dotenv
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-3.6-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
CORTEX_AUTH_MODE=local
CORTEX_ALLOW_REGISTRATION=true
~~~

Replace the key placeholder with your actual key. Keep `.env` private.

4. Start the app:

~~~powershell
python -m streamlit run app.py
~~~

5. Open the local URL, create an account, and save the recovery code shown after registration. Log in, upload files, and select **Process documents**.

The default local account database is `data/auth.sqlite3`. Retain and back up this private file to retain accounts. Account storage and hosting options are explained in [AUTHENTICATION.md](AUTHENTICATION.md).

## Upload to GitHub and deploy

Upload the **contents** of the extracted project folder to your repository, so `app.py`, `requirements.txt`, `auth/`, `rag/`, and `utils/` are at its root. Include `.streamlit/`, `.github/`, `.gitignore`, and `.env.example`. The ZIP is a download package; uploading only the ZIP will not deploy the app.

For Streamlit Community Cloud, choose your repository and branch, set `app.py` as the main file, and select Python **3.12**. Configure **Google / OIDC sign-in** and your Gemini key in private Streamlit Secrets using the full instructions in [AUTHENTICATION.md](AUTHENTICATION.md#google-sign-in-on-streamlit-community-cloud). This avoids relying on a local account database on an ephemeral host.

For an existing app, update your repository and use **App settings → Secrets**. Never upload actual credentials or an account database to GitHub. See Streamlit's [secrets guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management) and [dependency setup](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies).

## Configuration

Application settings use environment variables, then Streamlit secrets, then the local `.env` file. `GOOGLE_API_KEY` is accepted as a fallback for `GEMINI_API_KEY`. The local `.env` path is relative to this project. Restart after changing configuration and reprocess documents after changing the embedding model.

| Setting | Default | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | Required for AI | Private Gemini credential |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Answer, summary, and transcription model |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | Passage and query embeddings |
| `GEMINI_TIMEOUT_SECONDS` | `60` | Per-request timeout, 10–300 seconds |
| `CORTEX_AUTH_MODE` | `local` | `local` accounts or `oidc` provider sign-in |
| `CORTEX_AUTH_DB` | `data/auth.sqlite3` | Private local account database path |
| `CORTEX_ALLOW_REGISTRATION` | `true` | Allow new local accounts; set `false` to close registration |
| `CORTEX_ALLOWED_EMAILS` | Unrestricted | Optional comma-separated verified email allowlist in OIDC mode |

OIDC connection credentials must be in Streamlit's `[auth]` secrets section, as shown in the authentication guide. They are not configured through `.env`.

Transient API failures have up to three attempts. Embeddings use 768 dimensions with document/query task types and L2 normalization. See Google's [model catalog](https://ai.google.dev/gemini-api/docs/models), [embedding guide](https://ai.google.dev/gemini-api/docs/embeddings), and [image input API](https://ai.google.dev/gemini-api/docs/generate-content/image-understanding).

## Architecture

~~~text
Account login → authenticated browser-session workspace
Documents    → format-specific extraction / scan transcription
             → source-aware chunks → Gemini embeddings → FAISS index
Question     → query embedding → relevant passages → grounded answer + references
Passages     → per-document batch summaries → hierarchical synthesis
Logout       → clear workspace and end the current sign-in session
~~~

| File or folder | Purpose |
| --- | --- |
| `app.py` | Streamlit UI, authentication gate, uploads, session lifecycle |
| `auth/` | Local accounts and sessions; OIDC identity validation |
| `rag/config.py` | Gemini environment, secrets, clients, safe errors |
| `rag/document_processor.py` | Multi-format extraction and scanned-page reading |
| `rag/pdf_processor.py` | Legacy PDF helper kept for compatibility |
| `rag/text_splitter.py` | Overlapping passages retaining source locations |
| `rag/vector_store.py` | Embedding batches and FAISS retrieval |
| `rag/rag_pipeline.py` | Grounded generation and follow-up context |
| `rag/summary_generator.py` | Complete passage coverage and citation checks |
| `utils/prompts.py` | Grounding instructions |
| `tests/` | Offline authentication, format, RAG, and UI tests |
| `.github/workflows/` | Automated test configuration |

## Verify the app

~~~powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m pip check
~~~

Tests use real parsers, password hashing, SQLite, and FAISS, with mocked Gemini responses and provider identities; they incur no API charges. See [VERIFICATION.md](VERIFICATION.md) for the recorded result and limitations.

For a live test, sign in, configure your key, process `examples/research-notes.txt`, ask “What accuracy did the trial achieve?”, and inspect the cited source. Generate a summary. Repeat with your own scanned PDF/image if you need scan support. The sample is clearly labeled fictional. Test your deployed OIDC callback with your own provider credentials before sharing the app.

## Limits and privacy

- Maximum 10 files, 20 MB per file, 50 MB total, 300 pages per PDF.
- Up to 30 scanned pages per PDF when AI reading is used; split longer scans.
- Up to 2 million extracted characters and 5,000 passages per workspace.
- Images must be at most 25 megapixels and are resized for transcription.
- Office files must expand to at most 100 MB; tables support up to 100,000 rows and XLSX sheets up to 1,000 columns.
- Spreadsheet formulas use saved results. Recalculate and save in Excel if values are missing. This is document retrieval, not an exact spreadsheet calculation engine.
- Uploaded documents, indexes, summaries, and chat live in the browser's Streamlit server session. They are not saved to the account database. Logout, reset, or the end of a session clears the workspace; changing uploads clears earlier results. Downloads remain wherever you save them.
- Local authentication stores account records, password hashes, recovery-code hashes, and session metadata in a private SQLite database. OIDC credentials and identity cookies are managed by Streamlit and your provider. See [AUTHENTICATION.md](AUTHENTICATION.md).
- Gemini receives document text, questions, and any images/scans being read. Calls may incur charges. All users of a deployment share its configured Gemini quota.
- Citation checks validate reference names and locations, not the truth of generated claims. Verify key findings and AI transcriptions against the originals.
- This project does not include persistent document libraries, email delivery, an admin dashboard, or background jobs.

## Troubleshooting

| Issue | Action |
| --- | --- |
| Forgot local password | Use your username and saved recovery code on the recovery screen |
| Too many sign-in attempts | Wait for the 15-minute restriction to expire |
| Account missing after redeployment | Restore your private database backup, or use OIDC on ephemeral hosting |
| Google callback / redirect mismatch | Make the provider's authorized redirect URI exactly match `[auth].redirect_uri` |
| Provider access denied | Check the test-user list and optional `CORTEX_ALLOWED_EMAILS` |
| API key required | Add the key to local `.env` or Streamlit private Secrets; restart |
| Gemini access denied | Check the Gemini project permissions and key |
| Quota reached | Check AI Studio quota/billing; retry later |
| Model unavailable | Use a model your account can access |
| No readable content | Enable AI reading for scans or supply readable text |
| Could not read file | Re-save in a supported format; unlock encrypted PDFs |
| Transcription too long | Crop the image or split the scanned PDF |
| Citation validation failed | Retry; use shorter documents or a narrower question |

`.gitignore` excludes credentials, the local account database, caches, virtual environments, and saved indexes. Review files before committing. This package does not publish or rename your GitHub repository.
