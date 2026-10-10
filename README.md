# GitContext 🔍

> **AI-Powered Codebase Intelligence Copilot — Hybrid Retrieval & Citation-Grounded LLM Assistant**

GitContext helps developers quickly understand unfamiliar repositories by indexing local source code and documentation, and finding the exact files, functions, classes, and line numbers relevant to developer questions.

---

## 🎯 The Problem GitContext Solves

When exploring a new codebase or onboarding to a large repository, developers spend hours asking:
* *"Where is authentication or token validation handled?"*
* *"Which function processes Stripe payments and charges customers?"*
* *"Where is the database connection pool configured?"*

Traditional search (like `grep` or standard IDE text search) either misses context or returns hundreds of raw text hits without structural meaning. GitContext parses your code into **semantic AST chunks** (functions, classes, methods) and **hierarchical documentation sections**, retrieves context using **BM25 + Hybrid ranking**, and synthesizes answers using an **LLM-powered assistant** with strictly verified citations.

---

## 🏗️ System & LLM Architecture

GitContext is organized into a deterministic ingestion/indexing foundation and a secure, citation-grounded LLM synthesis pipeline.

```mermaid
graph TD
    subgraph Phase 1 & 2: Ingestion & Hybrid Retrieval
        A[Local Repository] --> B[Ingestion Engine]
        B -->|Filter gitignore, secrets| C[Discovered .py & .md Files]
        C --> D[AST & Markdown Chunker]
        D --> E[Deterministic CodeChunks]
        E --> F[Storage: data/index/chunks.jsonl]
        F --> G[Hybrid Retriever: BM25 + Dense RRF]
    end

    subgraph Step 3: LLM & Grounded Citation Pipeline
        Q["Developer Question (CLI / API)"] --> G
        G -->|Top-K Scored Results| H["Numbered Evidence Chunks [1], [2]"]
        H --> I["Prompt Construction Engine (generation.py)"]
        I -->|System Guardrails & Untrusted Delimiters| J["Strict Grounding Prompt"]
        J --> K["Configurable LLM Client (llm.py)"]
        
        subgraph Multi-Provider Switchboard
            K -->|OpenAI / Gemini / Anthropic / Ollama / Mock| L[LLM Response]
        end
        
        L --> M["Citation Verifier & Validator (citations.py)"]
        H --> M
        M -->|Validate Chunk IDs & Line Ranges| N{Citation Valid?}
        N -->|Valid [1], [2]| O["Verified Sources List"]
        N -->|Invented [99]| P["Flag & Strip Hallucinations"]
        
        O --> R["Final Validated Response (assistant.py)"]
        P --> R
        R --> S["CLI: python -m gitcontext ask"]
        R --> T["FastAPI REST API"]
    end
```

### LLM Pipeline Core Principles

1. **Strict Evidence Grounding**: The LLM is instructed to answer *solely* from the provided code evidence. If the retrieved snippets do not contain the answer, the model is compelled to state `"Insufficient evidence"`.
2. **Untrusted Data Defense (Anti-Injection)**: Retrieved code and documentation are strictly treated as **untrusted data**, wrapped in isolated delimiters. Any instructions inside code comments (e.g., *"ignore previous instructions"*) are treated purely as passive text data.
3. **Mandatory `[1]`, `[2]` Citations**: Every claim in the generated answer must cite the corresponding evidence chunk.
4. **Separation of Facts and Inferences**: Responses are partitioned into **Facts** (directly observed from code with citations) and **Inferences** (logical deductions or "None").
5. **Post-Generation Citation Verification**: A deterministic citations engine parses the LLM's references, validates that the referenced chunk actually exists, checks that the file path and line numbers are valid ($1 \le \text{start\_line} \le \text{end\_line}$), and strips or flags invented citations (e.g., `[99]`).
6. **Multi-Provider Switchboard**: Supports OpenAI, Google Gemini, Anthropic Claude, local Ollama, and Mock providers configured exclusively via environment variables (`.env`). No keys are hardcoded.

### Module Breakdown

| Module | Location | Purpose |
|---|---|---|
| **Models** | [`src/gitcontext/models.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/models.py) | Defines `CodeChunk`, `SearchResult`, and `IndexMetadata` dataclasses with SHA-256 deterministic IDs. |
| **Ingestion** | [`src/gitcontext/ingestion.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/ingestion.py) | Safely scans local directory trees, filters ignored/sensitive files (`.gitignore`, `.env`, `node_modules`, `venv`), and reads UTF-8 files safely. |
| **Chunking** | [`src/gitcontext/chunking.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/chunking.py) | Uses Python AST (`ast.parse`) to extract functions and classes with 1-based line bounds; splits Markdown by heading hierarchy. |
| **Indexing** | [`src/gitcontext/indexing.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/indexing.py) | Serializes and loads chunks to/from `data/index/chunks.jsonl` and metadata to `metadata.json`. |
| **Retrieval** | [`src/gitcontext/retrieval.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/retrieval.py) | BM25 Okapi retriever and `HybridRetriever` using Reciprocal Rank Fusion (RRF) with small-corpus fallback. |
| **LLM Provider** | [`src/gitcontext/llm.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/llm.py) | Configurable multi-provider LLM abstraction (OpenAI, Gemini, Anthropic, Ollama, Mock) without hardcoded keys. |
| **Generation** | [`src/gitcontext/generation.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/generation.py) | Builds grounded prompts with numbered evidence chunks, security guardrails, and calls the LLM. |
| **Citations** | [`src/gitcontext/citations.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/citations.py) | Parses bracket citations, validates source paths and line bounds, flags or removes hallucinated references. |
| **Assistant** | [`src/gitcontext/assistant.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/assistant.py) | Core orchestration service decoupled from CLI, returning structured responses for CLI and FastAPI. |
| **Evaluation** | [`src/gitcontext/evaluation.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/evaluation.py) | Automated citation precision, recall, and validity rate evaluation suite. |
| **CLI** | [`src/gitcontext/cli.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/cli.py) | Command-line interface supporting `index`, `search`, `status`, and `ask` commands. |

---

## 🚀 Getting Started

### Prerequisites
* Python 3.11 or newer (Python 3.13 supported)

### 1. Installation

Clone or navigate to the repository directory and install dependencies:

#### Windows PowerShell:
```powershell
# Navigate to project folder
cd "c:\Users\Aditya Raj\OneDrive\Documents\Desktop\Git Context"

# Install package in editable mode with development dependencies
python -m pip install -e ".[dev]"
```

#### macOS / Linux:
```bash
python3 -m pip install -e ".[dev]"
```

---

## 💻 Usage & CLI Commands

### 1. Index a Repository
Point GitContext at any local codebase directory:

```bash
python -m gitcontext index fixtures/synthetic_repo
```

**Expected Output:**
```text
Indexing repository: C:\Users\...\Git Context\fixtures\synthetic_repo

--- Indexing Completed Successfully ---
Repository : synthetic_repo (C:\Users\...\Git Context\fixtures\synthetic_repo)
Files      : 3 file(s) ingested
Chunks     : 17 chunk(s) stored
Saved to   : C:\Users\...\Git Context\data\index\chunks.jsonl
Indexed at : 2026-10-09 17:46:44 UTC
```

---

### 2. Search the Codebase
Ask natural language questions or search for symbols:

```bash
python -m gitcontext search "how to hash and verify password"
```

**Expected Output:**
```text
Query: "how to hash and verify password"
Searching in: synthetic_repo (17 chunks)
======================================================================

Result #1 (Score: 10.02) [CODE]
  File     : auth.py
  Symbol   : def verify_user_credentials
  Lines    : L16 - L19 (python)
  Chunk ID : 2de8d4144f1580b5
  Preview  :
    def verify_user_credentials(provided_password: str, stored_hash: str, salt: str) -> bool:
        """Validate user credentials against stored salt and hash."""
        computed_hash, _ = hash_user_password(provided_password, salt=salt)
        return secrets.compare_digest(computed_hash, stored_hash)
----------------------------------------------------------------------

Result #2 (Score: 6.04) [CODE]
  File     : auth.py
  Symbol   : def hash_user_password
  Lines    : L8 - L13 (python)
  Chunk ID : 3dd46016a7e14510
  Preview  :
    def hash_user_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
        """Generate a cryptographic SHA-256 password hash with salt."""
        if salt is None:
            salt = secrets.token_hex(16)
        hashed = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
        return hashed, salt
----------------------------------------------------------------------
```

---

### 3. Check Current Index Status
View details of the currently loaded repository:

```bash
python -m gitcontext status
```

**Expected Output:**
```text
=== GitContext Index Status ===
Repository     : synthetic_repo
Source Path    : C:\Users\...\Git Context\fixtures\synthetic_repo
Files Ingested : 3
Chunks Stored  : 17
Index Path     : C:\Users\...\Git Context\data\index\chunks.jsonl
Last Indexed   : 2026-10-09 17:46:44 UTC
```

---

### 4. Ask Grounded Questions with Verified Citations (Step 3)
Query the codebase using an LLM that answers exclusively with cited file paths and line ranges:

```bash
python -m gitcontext ask "Where is token expiry checked?"
```

**Expected Output:**
```text
Question: Where is token expiry checked?

Answer:
**Facts:**
- Session token expiry is initialized in `UserSessionManager.__init__` with a default `token_expiry_seconds=3600` [1].
**Inferences:**
- None.

Sources:
  [1] auth.py:L22-L38 (class UserSessionManager)
```

Configure your LLM provider and model via environment variables in `.env`:
```bash
cp .env.example .env
# Set LLM_PROVIDER=openai, gemini, anthropic, or ollama
# Set your API key
```

---

## 🧪 Running Automated Tests

Run the full test suite with `pytest`:

```bash
pytest -v
```

All 31 unit and integration tests cover:
- Python function and class AST extraction with line numbers
- Markdown hierarchical heading section chunking
- Deterministic chunk hashing & ID generation
- `.gitignore` and sensitive file exclusions (`.env`, `credentials.json`)
- Syntax error resilience
- BM25 ranking and camelCase / snake_case tokenization
- Hybrid retrieval with Reciprocal Rank Fusion
- LLM generation with prompt injection defenses and strict grounding
- Citation verification, invalid citation stripping, and line-range validation
- Error handling: missing API keys, empty retrieval, and LLM provider failures
- Grounded citation evaluation suite benchmarking precision and recall
- CLI subcommands (`index`, `search`, `status`, `ask`)

---

## 🔮 Roadmap & Next Milestones

* ✅ **Phase 1 — AST Chunking & BM25 Search**: Structural code parsing and keyword retrieval.
* ✅ **Phase 2 — Hybrid Retrieval**: Reciprocal Rank Fusion combining lexical and dense search.
* ✅ **Step 3 — LLM-Powered Citation Assistant**: Grounded answer synthesis, citation validation, and CLI `ask`.
* **Phase 4 — Live Synchronization**: Automatically keep index up to date as commits are pushed.
* **Phase 5 — FastAPI Backend & Web UI**: REST API and interactive interface with code highlighting.

