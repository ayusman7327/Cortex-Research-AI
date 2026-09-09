<div align="center">

# 🧠 Cortex Research AI

### Intelligent Research Assistant Powered by Retrieval-Augmented Generation (RAG)

Analyze research papers, perform semantic search, generate AI-powered summaries, and receive source-grounded answers using Google Gemini, FAISS, and Python.

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Google Gemini](https://img.shields.io/badge/Google-Gemini-4285F4?style=for-the-badge&logo=google&logoColor=white)
![FAISS](https://img.shields.io/badge/FAISS-Vector_Search-blue?style=for-the-badge)
![LangChain](https://img.shields.io/badge/LangChain-RAG-success?style=for-the-badge)

</div>

---

# 📖 Overview

Cortex Research AI is a Retrieval-Augmented Generation (RAG) platform designed to help researchers, students, and professionals interact with research papers intelligently.

Instead of generating answers purely from an LLM, Cortex Research AI retrieves the most relevant document sections using semantic search and provides accurate, source-grounded responses powered by Google Gemini.

The platform enables users to upload PDF research papers, extract text, build vector embeddings, perform semantic retrieval, generate AI-powered summaries, and ask natural language questions while maintaining contextual accuracy.

---

# ✨ Features

- Upload and analyze PDF research papers
- Intelligent text extraction and preprocessing
- Automatic document chunking
- Semantic vector embeddings
- FAISS vector database for fast retrieval
- Retrieval-Augmented Generation (RAG)
- AI-powered research paper summarization
- Context-aware question answering
- Source-grounded responses with citations
- Chat history support
- Multi-document processing
- Secure API key management using environment variables
- Modern and responsive Streamlit interface

---

# ⚙️ How It Works

```text
Research Paper (PDF)
          │
          ▼
Text Extraction
          │
          ▼
Document Chunking
          │
          ▼
Vector Embeddings
          │
          ▼
FAISS Vector Store
          │
          ▼
Semantic Retrieval
          │
          ▼
Google Gemini
          │
          ▼
Context-Aware Answer
```

---

# 🏗 Architecture

```text
                Streamlit UI
                      │
                      ▼
               Document Upload
                      │
                      ▼
              PDF Text Extraction
                      │
                      ▼
            Recursive Text Splitter
                      │
                      ▼
             Gemini Embeddings
                      │
                      ▼
              FAISS Vector Store
                      │
                      ▼
         Retrieval-Augmented Generation
                      │
                      ▼
              Google Gemini Model
                      │
                      ▼
        Source-Grounded AI Responses
```

---

# 🛠 Tech Stack

| Category | Technologies |
|-----------|--------------|
| Language | Python |
| Frontend | Streamlit |
| Backend | FastAPI |
| LLM | Google Gemini |
| RAG Framework | LangChain |
| Vector Database | FAISS |
| PDF Processing | PyPDF |
| Environment | Python Dotenv |

---

# 📂 Project Structure

```text
Cortex-Research-AI
│
├── .github
├── .streamlit
├── auth
├── data
├── examples
├── rag
│   ├── config.py
│   ├── document_processor.py
│   ├── pdf_processor.py
│   ├── rag_pipeline.py
│   ├── summary_generator.py
│   ├── text_splitter.py
│   └── vector_store.py
│
├── tests
├── utils
├── app.py
├── requirements.txt
├── requirements-dev.txt
├── styles.css
└── README.md
```

---

# 🚀 Installation

Clone the repository

```bash
git clone https://github.com/ayusman7327/Cortex-Research-AI.git
```

Navigate to the project

```bash
cd Cortex-Research-AI
```

Create a virtual environment

### Windows

```bash
python -m venv .venv
```

Activate

```bash
.venv\Scripts\activate
```

### macOS/Linux

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

Install dependencies

```bash
pip install -r requirements.txt
```

---

# 🔐 Environment Variables

Create a `.env` file in the project root.

```env
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
```

---

# ▶️ Run the Application

Launch the Streamlit application

```bash
streamlit run app.py
```

The application will be available at

```text
http://localhost:8501
```

---

# 💡 Usage

1. Launch Cortex Research AI.
2. Upload one or more research papers in PDF format.
3. Process the uploaded documents.
4. Generate an AI-powered summary.
5. Ask questions related to the uploaded papers.
6. Receive context-aware answers backed by retrieved document sections.

---

# 🌟 Project Highlights

- Retrieval-Augmented Generation (RAG) architecture
- Semantic document search using vector embeddings
- Intelligent PDF preprocessing
- Google Gemini integration
- AI-generated research summaries
- Source-grounded question answering
- Multi-document support
- Fast semantic retrieval using FAISS
- Modular and scalable project structure
- Clean and responsive user interface

---

# 📈 Future Improvements

- Research paper comparison
- Citation generation (APA, IEEE, MLA)
- Research gap identification
- Flashcard generation
- Quiz generation
- Export AI summaries
- OCR support for scanned PDFs
- Docker deployment
- Cloud deployment
- Multi-LLM support

---

# 🤝 Contributing

Contributions are welcome.

1. Fork the repository.
2. Create a new feature branch.
3. Commit your changes.
4. Push to your branch.
5. Open a Pull Request.

---

# 👨‍💻 Author

**Ayusman Mishra**

B.Tech Computer Science & Information Technology

Siksha 'O' Anusandhan (SOA) University

GitHub: https://github.com/ayusman7327

LinkedIn: https://www.linkedin.com/in/ayusman-mishra-b76976352

---

# 📄 License

This project is developed for educational and research purposes.

---

<div align="center">

### ⭐ If you found this project useful, consider giving it a star on GitHub.

Built with ❤️ using Python, Streamlit, Google Gemini, LangChain and FAISS.

</div>
