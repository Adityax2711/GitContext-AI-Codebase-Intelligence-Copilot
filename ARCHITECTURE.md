# GitContext System Architecture Document

## 1. High-Level System Overview

GitContext is an **AI-powered Codebase Intelligence Copilot and Automated Defect Investigation Platform**. It integrates lexical and dense semantic RAG, static and dynamic repository inspection tools, LLM answer grounding with strict citations, patch proposal and isolated test verification, and a modern web workspace with GitHub authentication and repository importing.

---

## 2. End-to-End System Architecture Diagram

```
+----------------------------------------------------------------------------------------------------+
|                                         PRESENTATION LAYER                                         |
|                                                                                                    |
|   +---------------------------------------+          +-----------------------------------------+   |
|   |         React 19 + Vite Web App       |          |               GitContext CLI            |   |
|   |   (Navbar, FileExplorer, CodeViewer,  |          |  (index, search, status, ask,           |   |
|   |    DiffViewer, InvestigationPanel,    |          |   investigate, import-repo, serve)      |   |
|   |    CopilotChat, GitHubModal)          |          |                                         |   |
|   +---------------------------------------+          +-----------------------------------------+   |
+-----------------------------------^----------------------------------------------------------------+
                                    | HTTP / JSON REST APIs
+-----------------------------------v----------------------------------------------------------------+
|                                    API & ORCHESTRATION LAYER                                       |
|                                                                                                    |
|   +--------------------------------------------------------------------------------------------+   |
|   |                                     FastAPI Server (Uvicorn)                               |   |
|   |  /api/status | /api/repository/* | /api/chat | /api/investigate | /api/patch/*             |   |
|   |  /api/test/run | /api/search | /api/symbols | /api/github/*                                |   |
|   +--------------------------------------------------------------------------------------------+   |
|                                    |                                                               |
|   +--------------------------------v-----------------------------------------------------------+   |
|   |                                  Agent Orchestrator                                        |   |
|   |  - ReAct Autonomous Loop (Thought -> Tool Call -> Observation -> Synthesis)                |   |
|   |  - Patch Lifecycle Manager (Staged, Verified, Applied, Rejected, Reverted)                 |   |
|   |  - Multi-Provider LLM Client (OpenAI / Anthropic / Gemini / Mock)                          |   |
|   +--------------------------------------------------------------------------------------------+   |
+-----------------------------------^----------------------------------------------------------------+
                                    |
+-----------------------------------v----------------------------------------------------------------+
|                                    AGENT TOOLS & VERIFICATION                                      |
|                                                                                                    |
|   +-------------------+  +--------------------+  +--------------------+  +---------------------+   |
|   |   RepoInspector   |  |  DependencyTracer  |  |   StaticAnalyzer   |  |     TestRunner      |   |
|   | (Safe AST bounds, |  |  (Call graph,      |  |  (Syntax errors,   |  | (Pytest sandbox,    |   |
|   |  traversal guard) |  |   cross-module)    |  |   symbol scopes)   |  |  traceback capture) |   |
|   +-------------------+  +--------------------+  +--------------------+  +---------------------+   |
+-----------------------------------^----------------------------------------------------------------+
                                    |
+-----------------------------------v----------------------------------------------------------------+
|                                      HYBRID RAG RETRIEVAL ENGINE                                   |
|                                                                                                    |
|               +----------------------------------------------------------------+                   |
|               |              Reciprocal Rank Fusion (RRF) Hybrid Search        |                   |
|               |         Score(d) = 1/(60 + Rank_BM25) + 1/(60 + Rank_Qdrant)   |                   |
|               +-----------------------+--------------------------------+-------+                   |
|                                       |                                |                           |
|                    +------------------v---------+       +--------------v---------------+           |
|                    |     BM25 Lexical Engine    |       |   Dense Vector Engine (Qdrant)  |         |
|                    |  - Tokenizer: snake_case,  |       |  - FastEmbed: bge-small-en   |           |
|                    |    camelCase, symbols      |       |  - Cosine Distance (384-dim) |           |
|                    |  - BM25Okapi scoring       |       |  - query_points API          |           |
|                    +----------------------------+       +------------------------------+           |
+-----------------------------------^----------------------------------------------------------------+
                                    |
+-----------------------------------v----------------------------------------------------------------+
|                                    INGESTION & CHUNKING PIPELINE                                   |
|                                                                                                    |
|   +-----------------------+      +-----------------------+      +------------------------------+   |
|   |    GitHub Service     |      |   Repository Ingest   |      |        Chunking Engine       |   |
|   | - Token Auth (PAT)    | ---> | - .gitignore parser   | ---> | - Python AST (Classes, Funcs)|   |
|   | - Git Clone / Zipball |      | - Security exclusions |      | - Markdown Hierarchical Headings|
|   | - Repos discovery     |      | - File discovery      |      | - Tests tagging (test chunks)|   |
|   +-----------------------+      +-----------------------+      +------------------------------+   |
+----------------------------------------------------------------------------------------------------+
```

---

## 3. Detailed Component Breakdown

### A. Ingestion & Preprocessing
1. **GitHub Service (`src/gitcontext/github_service.py`)**:
   - Authenticates users with GitHub Personal Access Tokens or OAuth tokens via `https://api.github.com/user`.
   - Lists user repositories with stars, default branch, language, and privacy flags.
   - Clones or downloads repositories via two strategies:
     - Primary: System `git clone --depth 1` with embedded token credentials.
     - Fallback: GitHub API zipball extraction (`https://api.github.com/repos/{owner}/{repo}/zipball/{ref}`).
2. **File Discovery & Security Filter (`src/gitcontext/ingestion.py`)**:
   - Parses repository `.gitignore` specifications with wildcard and directory segment matching.
   - Enforces default exclusions: `.git`, `__pycache__`, virtual environments (`.venv`, `venv`, `env`), node_modules, build artifacts, `.env` files, credentials, and secrets.
   - Discovers supported source files: `.py` (code & tests) and `.md` (documentation).
3. **AST & Markdown Chunking (`src/gitcontext/chunking.py`)**:
   - **Python AST Chunker**: Parses code into AST nodes. Extracts classes, methods, top-level functions, and module preambles.
   - **Preserves Line Accuracy**: Tracks 1-based start and end line ranges.
   - **Syntax Error Resilient**: Falls back to file-level chunks on syntax errors rather than failing.
   - **Test File Tagging**: Classifies chunks from `tests/`, `test_*.py`, or `*_test.py` as `source_type="test"`.
   - **Markdown Chunker**: Tracks hierarchical heading paths (`H1 > H2 > H3`) and assigns contiguous sections.
   - **Deterministic IDs**: Generates stable SHA-256 chunk IDs based on content hash, file path, symbol, and line ranges.

### B. Hybrid RAG & Vector Engine
1. **BM25 Lexical Retriever (`src/gitcontext/retrieval.py`)**:
   - Uses `rank_bm25` (BM25Okapi).
   - Code-aware tokenizer splits camelCase (`getUserById` -> `get`, `user`, `by`, `id`) and snake_case (`process_order_data` -> `process`, `order`, `data`).
2. **Qdrant Dense Vector Store (`src/gitcontext/vector_store.py`)**:
   - Uses `qdrant-client` with local embedded persistence or in-memory mode.
   - Generates 384-dimensional dense vectors via FastEmbed (`BAAI/bge-small-en-v1.5`) or deterministic fallback.
   - Leverages modern Qdrant `query_points` API with cosine similarity distance.
   - Stores full `CodeChunk` payload in Qdrant points for fast reconstruction.
3. **Hybrid Reciprocal Rank Fusion (RRF)**:
   - Evaluates queries across both BM25 and Qdrant.
   - Fuses ranked candidate lists:
     $$\text{RRF Score}(d) = \sum_{m \in \{\text{BM25}, \text{Dense}\}} \frac{1}{k + \text{rank}_m(d)} \quad (k = 60)$$
   - Produces higher retrieval precision than BM25 or dense vectors alone.

### C. Citation Verification & Answer Generation
1. **Strict Citation Engine (`src/gitcontext/citations.py`)**:
   - Parses bracketed references: `[1]`, `[2]`.
   - Cross-references each cited index against actual retrieved chunk bounds (`file_path`, `start_line`, `end_line`, `symbol`).
   - Strips ungrounded/invented citations and generates citation warnings to prevent hallucinated claims.
2. **LLM Generation (`src/gitcontext/generation.py` & `llm.py`)**:
   - Provider abstraction supporting **OpenAI**, **Anthropic**, **Gemini**, and offline **Mock** clients.
   - Structured prompt assembly enforcing:
     - Section 1: Facts directly verified by cited code evidence.
     - Section 2: Inferences & hypotheses clearly separated.

### D. Bug Investigation & Tool Execution
1. **RepoInspector (`src/gitcontext/tools/repo_inspector.py`)**:
   - Reads exact file slices with line numbers.
   - Path traversal security guard prevents accessing files outside the repository root.
2. **DependencyTracer (`src/gitcontext/tools/dependency_tracer.py`)**:
   - AST visitor that extracts call graphs, caller functions, and cross-module references.
3. **StaticAnalyzer (`src/gitcontext/tools/static_analyzer.py`)**:
   - AST node visitor identifying syntax errors, undefined references, and risky patterns.
4. **TestRunner (`src/gitcontext/tools/test_runner.py`)**:
   - Subprocess executor that runs pytest in isolation and extracts structured test summaries, failure traces, and error types.
5. **BugInvestigator & Agent Orchestrator (`src/gitcontext/investigator.py`, `agent/`)**:
   - Generates defect hypotheses, formulates investigation plans, executes tools iteratively, and compiles evidence-backed `BugInvestigationReport`s.

### E. Patch Lifecycle Management
1. **Patch Generation (`src/gitcontext/agent/patch_manager.py`)**:
   - Constructs unified diffs (`--- a/file`, `+++ b/file`, `@@ -start,len +start,len @@`).
   - Validates diff syntax before touching files.
2. **Patch Application & Rollback**:
   - In-memory backup of original file contents.
   - Rollback capability restores original files on demand.
3. **Isolated Test Verification**:
   - Re-runs test suite after patch application to verify if previously failing tests now pass.

### F. Web Workspace & Backend
1. **FastAPI Backend (`src/gitcontext/server/`)**:
   - Exposes REST endpoints for repository selection, file tree navigation, hybrid search, chat, investigation, patch management, and GitHub authentication/import.
   - Static file server mounts frontend production build for single-command deployment.
2. **React 19 Frontend (`frontend/src/`)**:
   - Modular UI components:
     - `Navbar`: Displays active repo, chunk count, LLM model, GitHub profile status.
     - `FileExplorer`: File tree with icons and language tags.
     - `CodeViewer`: Syntax-highlighted code with line numbers and citation highlight ranges.
     - `DiffViewer`: Side-by-side / unified diff inspector with Apply, Reject, Verify, and Rollback actions.
     - `InvestigationPanel`: Defect hypotheses, affected line numbers, confidence indicators, and test failure cards.
     - `CopilotChat`: Agent dialogue, thought steps, tool calls, and clickable source citations.
     - `GitHubModal`: Personal Access Token login, user repo browser, and 1-click import.

---

## 4. Technologies, Frameworks, and Libraries Used

| Category | Technology / Library | Purpose in GitContext |
| :--- | :--- | :--- |
| **Language** | Python 3.11+ | Core engine, RAG pipeline, agent tools, backend server |
| **Language** | TypeScript / JavaScript | Frontend logic, type safety, API bindings |
| **Frontend Framework** | React 19 | Reactive UI, workspace layout, component state |
| **Build Tool** | Vite | Frontend bundling, development server, static asset generation |
| **Styling** | Vanilla CSS (CSS3) | Custom glassmorphism dark-mode design system |
| **UI Icons** | Lucide React | Modern vector icon set |
| **Backend Framework** | FastAPI | High-performance asynchronous REST API server |
| **ASGI Server** | Uvicorn | Production-ready HTTP/ASGI server |
| **Validation** | Pydantic v2 | Strict schema validation for API requests, responses, and models |
| **Lexical RAG** | Rank-BM25 (BM25Okapi) | Code-aware keyword search over AST and Markdown chunks |
| **Dense Vector RAG** | Qdrant Client | Embedded / client dense vector store with cosine distance |
| **Embeddings** | FastEmbed (`bge-small-en-v1.5`) | Local, lightweight transformer dense embedding generation |
| **Code Parsing** | Python `ast` (Standard Library) | AST function, class, method parsing, call graph tracing |
| **Testing** | Pytest | Test suite runner and automated verification sandbox |
| **HTTP Client** | `httpx` / `urllib.request` | API communication and GitHub zipball / REST integration |
| **LLM APIs** | OpenAI, Anthropic, Gemini | Generation, reasoning, and defect investigation |

---

## 5. End-to-End Data Flow

```
1. INGESTION & IMPORT:
   GitHub URL / Local Directory -> Git / API Download -> .gitignore Filter -> AST / Heading Chunker
   -> Generates CodeChunk objects (classes, methods, functions, tests, docs).

2. INDEXING:
   CodeChunk -> BM25 Tokenizer -> Inverted Index
   CodeChunk -> FastEmbed (384-dim) -> Qdrant Collection (gitcontext_chunks)
   CodeChunk -> data/index/chunks.jsonl & metadata.json

3. HYBRID RETRIEVAL:
   User Query -> BM25 Search (Scores 1..N)
   User Query -> Qdrant Search (Scores 1..N)
   Scores -> Reciprocal Rank Fusion (RRF) -> Top-K Grounded Evidence Chunks

4. ASSISTANT GENERATION:
   Grounded Chunks + Prompt -> LLM Provider -> Raw Answer with [1], [2] citations
   Raw Answer -> Citation Verifier -> Cleaned Answer + Validated Sources

5. DEFECT INVESTIGATION:
   Bug Description -> Agent Orchestrator -> RepoInspector / DependencyTracer / StaticAnalyzer / TestRunner
   -> Collects Evidence -> BugInvestigationReport -> Proposes Patch Diff -> Runs Pytest Verification

6. USER WORKSPACE:
   FastAPI Server <-> React 19 Frontend (Code Viewer, Diff Viewer, Copilot Chat, GitHub Modal)
```
