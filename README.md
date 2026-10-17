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

GitContext is organized into a deterministic ingestion/indexing foundation, hybrid RAG retrieval, autonomous agent investigation, and a secure, citation-grounded LLM synthesis pipeline.

```mermaid
graph TD
    subgraph Ingestion and Storage
        GH["GitHub URL / Repository"] -->|"PAT Auth / Git Clone / Zipball"| GHService["GitHub Service"]
        GHService --> Ingest["Ingestion Engine"]
        Local["Local Repository"] --> Ingest
        Ingest -->|"Filter gitignore, secrets"| Files["Discovered .py and .md Files"]
        Files --> Chunker["AST and Markdown Chunker"]
        Chunker --> Chunks["CodeChunks: Code, Tests, Docs"]
        Chunks --> Qdrant[("Qdrant Vector Store: 384-dim")]
        Chunks --> Disk[("JSONL Archive: chunks.jsonl")]
    end

    subgraph Hybrid Retrieval and Grounding
        Query["Query / Question"] --> Hybrid["Hybrid Retriever: BM25 + Qdrant RRF"]
        Qdrant --> Hybrid
        Disk --> Hybrid
        Hybrid -->|"Top-K Evidence"| Grounding["Numbered Grounded Chunks"]
        Grounding --> Prompt["Prompt Construction Engine"]
        Prompt --> LLM["LLM Provider: OpenAI / Gemini / Claude / Mock"]
        LLM --> CitationVerifier["Citation Verifier: citations.py"]
        Grounding --> CitationVerifier
        CitationVerifier -->|"Valid Grounded Citations"| VerifiedAns["Verified Grounded Answer"]
        CitationVerifier -->|"Invented Citations"| StripH["Strip and Flag Hallucinations"]
    end

    subgraph Investigation and Copilot Workspace
        VerifiedAns --> WebUI["React 19 Copilot Workspace"]
        VerifiedAns --> CLI["GitContext CLI"]
        Investigator["Bug Investigator Agent"] --> Tools["RepoInspector + DependencyTracer + StaticAnalyzer + TestRunner"]
        Tools --> Pytest[("Isolated Pytest Sandbox")]
        Investigator --> PatchManager["Patch Manager: Unified Diffs and Rollback"]
        PatchManager --> WebUI
    end
```

> 📘 **Full Architecture Deep-Dive**: For detailed component interactions, data flow diagrams, and threat models, see the complete [System & LLM Architecture Specification](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/ARCHITECTURE.md).

### LLM Pipeline Core Principles

1. **Strict Evidence Grounding**: The LLM is instructed to answer *solely* from the provided code evidence. If the retrieved snippets do not contain the answer, the model is compelled to state `"Insufficient evidence"`.
2. **Untrusted Data Defense (Anti-Injection)**: Retrieved code and documentation are strictly treated as **untrusted data**, wrapped in isolated delimiters. Any instructions inside code comments (e.g., *"ignore previous instructions"*) are treated purely as passive text data.
3. **Mandatory Citations**: Every claim in the generated answer must cite the corresponding evidence chunk (e.g. `[1]`, `[2]`).
4. **Separation of Facts and Inferences**: Responses are partitioned into **Facts** (directly observed from code with citations) and **Inferences** (logical deductions or "None").
5. **Post-Generation Citation Verification**: A deterministic citations engine parses the LLM's references, validates that the referenced chunk actually exists, checks that the file path and line numbers are valid (`1 <= start_line <= end_line`), and strips or flags invented citations (e.g., `[99]`).
6. **Multi-Provider Switchboard**: Supports OpenAI, Google Gemini, Anthropic Claude, local Ollama, and Mock providers configured exclusively via environment variables (`.env`). No keys are hardcoded.

### Module Breakdown

| Module | Location | Purpose |
|---|---|---|
| **Models** | [`src/gitcontext/models.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/models.py) | Defines `CodeChunk`, `SearchResult`, and `IndexMetadata` dataclasses with SHA-256 deterministic IDs and test source typing. |
| **Ingestion** | [`src/gitcontext/ingestion.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/ingestion.py) | Safely scans local directory trees, filters ignored/sensitive files (`.gitignore`, `.env`, `node_modules`, `venv`), and reads UTF-8 files safely. |
| **GitHub Service** | [`src/gitcontext/github_service.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/github_service.py) | GitHub authentication (PAT/OAuth), repository discovery, and dual-strategy clone / API zipball archive downloader. |
| **Chunking** | [`src/gitcontext/chunking.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/chunking.py) | Uses Python AST (`ast.parse`) to extract functions, classes, and test cases with 1-based line bounds; splits Markdown by heading hierarchy. |
| **Indexing** | [`src/gitcontext/indexing.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/indexing.py) | Serializes and loads chunks to/from `data/index/chunks.jsonl` and metadata to `metadata.json`, and coordinates Qdrant indexing. |
| **Vector Store** | [`src/gitcontext/vector_store.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/vector_store.py) | Dense vector store powered by Qdrant (`query_points`) and FastEmbed (`BAAI/bge-small-en-v1.5`) with offline deterministic fallback. |
| **Retrieval** | [`src/gitcontext/retrieval.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/retrieval.py) | BM25 Okapi retriever and `HybridRetriever` using Reciprocal Rank Fusion (RRF) combining lexical and dense search. |
| **LLM Provider** | [`src/gitcontext/llm.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/llm.py) | Configurable multi-provider LLM abstraction (OpenAI, Gemini, Anthropic, Ollama, Mock) without hardcoded keys. |
| **Generation** | [`src/gitcontext/generation.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/generation.py) | Builds grounded prompts with numbered evidence chunks, security guardrails, and calls the LLM. |
| **Citations** | [`src/gitcontext/citations.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/citations.py) | Parses bracket citations, validates source paths and line bounds, flags or removes hallucinated references. |
| **Assistant** | [`src/gitcontext/assistant.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/assistant.py) | Core orchestration service decoupled from CLI, returning structured responses for CLI and FastAPI with hybrid RAG. |
| **Bug Models** | [`src/gitcontext/bug_models.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/bug_models.py) | Pydantic models for structured findings, severity/confidence rationales, test summaries, and reports. |
| **Investigation Tools** | [`src/gitcontext/tools/`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/tools/) | Reusable tools: `RepoInspector` (safe file & symbol read), `DependencyTracer` (AST callers), `StaticAnalyzer` (Ruff/AST), `TestRunner` (isolated pytest). |
| **Investigator** | [`src/gitcontext/investigator.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/investigator.py) | Step 4 orchestration engine combining retrieval, AST tracing, static linting, and isolated test execution. |
| **Patch Manager** | [`src/gitcontext/agent/patch_manager.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/agent/patch_manager.py) | Unified diff construction, syntax validation, file application, and automatic `.bak` rollback. |
| **Evaluation** | [`src/gitcontext/evaluation.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/evaluation.py) | Automated citation precision, recall, and validity rate evaluation suite. |
| **CLI** | [`src/gitcontext/cli.py`](file:///c:/Users/Aditya%20Raj/OneDrive/Documents/Desktop/Git%20Context/src/gitcontext/cli.py) | Command-line interface supporting `index`, `search`, `status`, `ask`, `investigate`, `import-repo`, and `serve`. |

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

### 5. Investigate Bugs with Grounded Root Cause Analysis (Step 4)
Run automated investigations across code, call trees, static analyzers (Ruff & AST), and isolated pytest execution:

```bash
python -m gitcontext investigate --repo fixtures/synthetic_bug_repo --query "Investigate zero division in divide_numbers" --run-tests
```

**Expected Output:**
```text
==============================================================================
GITCONTEXT BUG INVESTIGATION REPORT
==============================================================================
Query      : Investigate zero division in divide_numbers
Repository : fixtures/synthetic_bug_repo
Summary    : Investigation completed: 5 finding(s) identified (1 reproduced, 4 suspected).
------------------------------------------------------------------------------
[TEST EXECUTION - ISOLATED RUN]:
  Total: 2 | Passed: 1 | Failed: 1 | Errors: 0
  [1] test_divide_zero_division_failing (ZeroDivisionError): float division by zero
      Traceback points to: math_ops.py:L11 (divide_numbers)
------------------------------------------------------------------------------
[STATIC ANALYSIS FINDINGS] (10 detected):
  [RUFF:UP035] math_ops.py:L3-L3 - `typing.List` is deprecated, use `list` instead
  [AST_INSPECTOR:AST:ZERO_DIVISION] math_ops.py:L17-L17 - Division, floor division, or modulo by literal zero detected.
------------------------------------------------------------------------------
[IDENTIFIED BUG FINDINGS] (5):

[1] BUG-001: Test failure: test_divide_zero_division_failing raised ZeroDivisionError
    Category      : zero_division
    Severity      : HIGH (Verified by executing automated test suite in isolated environment.)
    Confidence    : HIGH (High confidence: Defect was directly reproduced by test runner and localized via stack trace.)
    Evidence Type : test_failure
    Location      : math_ops.py:L9-L13
    Status        : REPRODUCED
    Root Cause    : Unhandled condition in divide_numbers triggered by test input.
    Expected      : Test test_divide_zero_division_failing should pass without raising unhandled ZeroDivisionError.
    Observed      : ZeroDivisionError: float division by zero
    Fix Direction : Implement input validation or guard clause handling the failing edge case.
    Next Step     : Inspect variables leading to math_ops.py:L11 during test execution.
    Reproduction  :
      - Run test suite: pytest tests/test_math.py
      - Observe ZeroDivisionError at line 11

------------------------------------------------------------------------------
[GROUNDED SOURCE CITATIONS]:
  [1] math_ops.py:L9-L13 (divide_numbers)
  [2] math_ops.py:L17-L17 (AST:ZERO_DIVISION)
==============================================================================
```

Output machine-readable JSON:
```bash
python -m gitcontext investigate --repo fixtures/synthetic_bug_repo --query "Investigate zero division" --run-tests --json
```

---

### 6. Import Repository from GitHub
Import and automatically index any public or private GitHub repository using Git or the GitHub REST API:

```bash
# Import a public repository via URL
python -m gitcontext import-repo https://github.com/pallets/flask --branch main

# Import using owner/repo syntax with a Personal Access Token (for private repos)
python -m gitcontext import-repo octocat/Hello-World --token ghp_yourPersonalAccessToken
```

---

## 🧪 Running Automated Tests

Run the full test suite with `pytest`:

```bash
pytest -v
```

All 68 unit, integration, and end-to-end tests cover:
- Python function and class AST extraction with 1-based line bounds
- Test file detection and test chunk categorization (`source_type="test"`)
- Markdown hierarchical heading section chunking
- Deterministic chunk hashing & SHA-256 ID generation
- `.gitignore` and sensitive file exclusions (`.env`, `credentials.json`, `node_modules`)
- Syntax error resilience & UTF-8 decoding fallback
- BM25 ranking and camelCase / snake_case tokenization
- **Dense Qdrant Vector Store**: FastEmbed `BAAI/bge-small-en-v1.5`, modern `query_points` API, collection management, and offline fallback
- **Hybrid Retrieval**: Reciprocal Rank Fusion (RRF) blending BM25 lexical and Qdrant dense vector rankings
- **GitHub Service**: Authentication, repository discovery, authenticated git clone, and API zipball archive downloader
- **GitHub REST API**: Login, logout, user profile, repo listing, and 1-click import endpoints
- LLM generation with prompt injection defenses and strict grounding
- Citation verification, invalid citation stripping, and line-range validation (`1 <= start_line <= end_line`)
- Error handling: missing API keys, empty retrieval, and LLM provider failures
- Grounded citation evaluation suite benchmarking precision and recall
- **Bug Investigation Tools**: `RepoInspector` (safe file reading & path traversal defense), `DependencyTracer` (call graphs), `StaticAnalyzer` (Ruff/AST), `TestRunner` (isolated pytest)
- **Patch Manager**: Unified diff generation, syntax verification, `.bak` file backups, and safe rollback
- CLI subcommands (`index`, `search`, `status`, `ask`, `investigate`, `import-repo`, `serve`)

---

## 🔮 Roadmap & Architecture Milestones

* ✅ **Phase 1 — Core Engine**: Structural AST parsing (functions, classes), Markdown hierarchical chunking, deterministic SHA-256 chunk hashing, and safe UTF-8 ingestion with `.gitignore` and security exclusions.
* ✅ **Phase 2 — Dense Vector Search & Hybrid RAG**: Qdrant vector store (`query_points`), FastEmbed embedding model (`BAAI/bge-small-en-v1.5`), BM25 Okapi lexical retrieval, Reciprocal Rank Fusion (RRF), and test-aware chunk tagging.
* ✅ **Phase 3 — Grounded LLM Synthesis & Citation Verification**: Multi-provider switchboard (OpenAI, Gemini, Anthropic, Ollama, Mock), strict anti-injection prompt guardrails, and deterministic post-generation citation verification (`1 <= start_line <= end_line`).
* ✅ **Phase 4 — Bug Investigation Agent**: Multi-tool autonomous agent (`RepoInspector`, `DependencyTracer`, `StaticAnalyzer`, `TestRunner`), AST call graph analysis, Ruff & AST rule linting, isolated pytest runner, and Pydantic bug reports.
* ✅ **Phase 5 — AI Fix Proposals & Patch Manager**: Synthesizes verified unified diffs, syntax validation, sandboxed test verification, safe file application with `.bak` backups, and rollback capabilities.
* ✅ **Phase 6 — Full-Stack Web Workspace & GitHub Integration**: React 19 + TypeScript Copilot workspace, monaco-style code viewer, diff review, interactive GitHub authentication modal, repository browser, and 1-click cloud repository import.

---

## 🌐 Web Workspace & Copilot Interface

GitContext includes a full-featured web-based coding assistant workspace inspired by GitHub Copilot.

### Launch the Workspace:

#### Option 1: Full-Stack FastAPI Production Server
```bash
python -m gitcontext serve --port 8000
```
Open [http://localhost:8000](http://localhost:8000) in your browser. The single-page React frontend is automatically served by FastAPI.

#### Option 2: Live Development Mode
1. **Start FastAPI Backend:**
   ```bash
   python -m gitcontext serve --port 8000
   ```
2. **Start Vite Dev Server with HMR:**
   ```bash
   cd frontend
   npm run dev
   ```
   Open [http://localhost:5173](http://localhost:5173).

---

## 🛠️ FastAPI REST API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/status` | `GET` | System health, active repository info, index metrics, and LLM configuration. |
| `/api/repositories` | `GET` | List available workspaces and fixtures (`synthetic_bug_repo`, etc.). |
| `/api/repository/select` | `POST` | Switch active repository and re-index. |
| `/api/repository/tree` | `GET` | Recursive repository file tree with directory structures. |
| `/api/repository/file` | `GET` | Safe file reader with 1-based line bounds for the Code Viewer. |
| `/api/chat` | `POST` | Conversational AI Copilot agent with multi-step tool calls, thoughts, and citations. |
| `/api/investigate` | `POST` | Automated bug-to-fix workflow combining test runner, static analysis, and patch synthesis. |
| `/api/patch/apply` | `POST` | Explicitly apply an approved patch to disk with an automatic `.bak` backup. |
| `/api/patch/reject` | `POST` | Mark proposed patch rejected without modifying code. |
| `/api/patch/verify` | `POST` | Execute isolated tests on proposed patch in a sandbox and report results. |
| `/api/patch/rollback` | `POST` | Restore repository file from backup or original state. |
| `/api/test/run` | `POST` | Run isolated test suite and parse failures. |
| `/api/search` | `GET` | BM25 + dense hybrid search with Reciprocal Rank Fusion. |
| `/api/symbols` | `GET` | AST function and class symbol finder. |
| `/api/github/user` | `GET` | Retrieve authenticated GitHub user identity and avatar. |
| `/api/github/login` | `POST` | Authenticate with GitHub using a Personal Access Token (PAT). |
| `/api/github/logout` | `POST` | Discard active GitHub session credentials. |
| `/api/github/repos` | `GET` | List accessible personal and organization repositories. |
| `/api/github/import` | `POST` | Clone or download (dual-strategy) a GitHub repo into workspace and index it. |
