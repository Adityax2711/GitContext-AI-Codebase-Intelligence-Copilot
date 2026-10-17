"""Command-line interface for GitContext."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from gitcontext.assistant import ask_codebase
from gitcontext.indexing import get_default_index_dir, index_repository, load_index
from gitcontext.investigator import BugInvestigator
from gitcontext.llm import LLMError
from gitcontext.retrieval import search_index


def format_preview(content: str, max_lines: int = 8, max_chars: int = 400) -> str:
    """Format a clean snippet preview of the chunk."""
    lines = content.strip().splitlines()
    truncated = False

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True

    preview = "\n".join(f"    {line}" for line in lines)
    if len(preview) > max_chars:
        preview = preview[:max_chars].rstrip() + "..."
        truncated = True

    if truncated:
        preview += "\n    [... truncated ...]"
    return preview


def cmd_index(repo_path_str: str, index_dir_str: Optional[str] = None) -> int:
    """Handle the 'index' subcommand."""
    repo_path = Path(repo_path_str)
    if not repo_path.exists():
        print(f"Error: Repository path does not exist: '{repo_path_str}'", file=sys.stderr)
        return 1
    if not repo_path.is_dir():
        print(f"Error: Path is not a directory: '{repo_path_str}'", file=sys.stderr)
        return 1

    index_dir = Path(index_dir_str) if index_dir_str else get_default_index_dir()

    print(f"Indexing repository: {repo_path.resolve()}")
    try:
        metadata = index_repository(repo_path=repo_path, index_dir=index_dir)
    except Exception as e:
        print(f"Error during indexing: {e}", file=sys.stderr)
        return 1

    print("\n--- Indexing Completed Successfully ---")
    print(f"Repository  : {metadata.repository_name} ({metadata.repository_path})")
    print(f"Files       : {metadata.total_files} file(s) ingested")
    print(f"Chunks      : {metadata.total_chunks} chunk(s) stored")
    dense_desc = f"Enabled ({metadata.dense_vectors_count} vectors in Qdrant)" if metadata.dense_indexed else "BM25 keyword index"
    print(f"Dense Store : {dense_desc}")
    print(f"Saved to    : {index_dir.resolve() / 'chunks.jsonl'}")
    print(f"Indexed at  : {metadata.last_indexed_at}")
    return 0


def cmd_search(query: str, top_k: int = 5, index_dir_str: Optional[str] = None) -> int:
    """Handle the 'search' subcommand with hybrid retrieval support."""
    query = query.strip()
    if not query:
        print("Error: Search query cannot be empty.", file=sys.stderr)
        return 1

    index_dir = Path(index_dir_str) if index_dir_str else get_default_index_dir()
    chunks, metadata = load_index(index_dir)

    if not chunks:
        print("No index found or index is empty.", file=sys.stderr)
        print("Please index a repository first: python -m gitcontext index <repository_path>", file=sys.stderr)
        return 1

    vstore = None
    qdrant_dir = index_dir / "qdrant"
    if qdrant_dir.exists():
        try:
            from gitcontext.vector_store import QdrantVectorStore

            vstore = QdrantVectorStore(storage_path=qdrant_dir, in_memory=False)
        except Exception:
            vstore = None

    if vstore and vstore.is_available():
        from gitcontext.retrieval import hybrid_search

        results = hybrid_search(query=query, chunks=chunks, top_k=top_k, vector_store=vstore)
        mode_label = "Hybrid Search (BM25 + Qdrant Dense)"
    else:
        results = search_index(query=query, chunks=chunks, top_k=top_k)
        mode_label = "BM25 Keyword Search"

    print(f"\nQuery: \"{query}\" [{mode_label}]")
    if metadata:
        print(f"Searching in: {metadata.repository_name} ({len(chunks)} chunks)")
    print("=" * 70)

    if not results:
        print("No relevant results found for your query.")
        return 0

    for res in results:
        chunk = res.chunk
        type_badge = f"[{chunk.source_type.upper()}]"
        print(f"\nResult #{res.rank} (Score: {res.score:.2f}) {type_badge}")
        print(f"  File     : {chunk.file_path}")
        print(f"  Symbol   : {chunk.symbol_or_heading}")
        print(f"  Lines    : L{chunk.start_line} - L{chunk.end_line} ({chunk.programming_language})")
        print(f"  Chunk ID : {chunk.chunk_id}")
        print("  Preview  :")
        print(format_preview(chunk.content))
        print("-" * 70)

    return 0


def cmd_status(index_dir_str: Optional[str] = None) -> int:
    """Handle the 'status' subcommand."""
    index_dir = Path(index_dir_str) if index_dir_str else get_default_index_dir()
    chunks, metadata = load_index(index_dir)

    print("\n=== GitContext Index Status ===")
    if not metadata or not chunks:
        print("Status: No repository currently indexed.")
        print("Run 'python -m gitcontext index <repository_path>' to get started.\n")
        return 0

    print(f"Repository     : {metadata.repository_name}")
    print(f"Source Path    : {metadata.repository_path}")
    print(f"Files Ingested : {metadata.total_files}")
    print(f"Chunks Stored  : {metadata.total_chunks}")
    dense_status = f"Enabled ({metadata.dense_vectors_count} vectors in Qdrant)" if metadata.dense_indexed else "BM25 keyword only"
    print(f"Dense Vector   : {dense_status}")
    print(f"Index Path     : {index_dir.resolve() / 'chunks.jsonl'}")
    print(f"Last Indexed   : {metadata.last_indexed_at}\n")
    return 0


def cmd_ask(
    question: str,
    top_k: int = 5,
    index_dir_str: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> int:
    """Handle the 'ask' subcommand."""
    question = question.strip()
    if not question:
        print("Error: Question cannot be empty.", file=sys.stderr)
        return 1

    index_dir = Path(index_dir_str) if index_dir_str else get_default_index_dir()

    try:
        response = ask_codebase(
            question=question,
            index_dir=index_dir,
            top_k=top_k,
            provider=provider,
            model=model,
        )
    except LLMError as e:
        print(f"LLM Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error answering question: {e}", file=sys.stderr)
        return 1

    print(response.format_cli_output())
    return 0


def cmd_investigate(
    query: str,
    repo_path_str: str = ".",
    target_file: Optional[str] = None,
    target_symbol: Optional[str] = None,
    run_tests: bool = False,
    test_path: Optional[str] = None,
    index_dir_str: Optional[str] = None,
    format_type: str = "terminal",
    json_output: bool = False,
) -> int:
    """Handle the 'investigate' subcommand."""
    repo_path = Path(repo_path_str)
    if not repo_path.exists():
        print(f"Error: Repository path does not exist: '{repo_path_str}'", file=sys.stderr)
        return 1
    if not repo_path.is_dir():
        print(f"Error: Path is not a directory: '{repo_path_str}'", file=sys.stderr)
        return 1

    index_dir = Path(index_dir_str) if index_dir_str else get_default_index_dir()
    investigator = BugInvestigator(repo_path=repo_path, index_dir=index_dir)

    try:
        report = investigator.investigate(
            query=query,
            target_file=target_file,
            target_symbol=target_symbol,
            run_tests=run_tests,
            test_path=test_path,
        )
    except Exception as e:
        print(f"Error during bug investigation: {e}", file=sys.stderr)
        return 1

    if json_output or format_type == "json":
        import json
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.format_cli_output())

    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="gitcontext",
        description="GitContext: AI-powered codebase intelligence copilot.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # index subcommand
    index_parser = subparsers.add_parser("index", help="Index a local code repository")
    index_parser.add_argument("repository_path", type=str, help="Path to the local repository directory")
    index_parser.add_argument("--index-dir", type=str, default=None, help="Custom directory to store the index")

    # search subcommand
    search_parser = subparsers.add_parser("search", help="Search the indexed codebase with a question")
    search_parser.add_argument("query", type=str, help="Question or keywords to search for")
    search_parser.add_argument("--top-k", type=int, default=5, help="Number of results to return (default: 5)")
    search_parser.add_argument("--index-dir", type=str, default=None, help="Custom directory containing the index")

    # status subcommand
    status_parser = subparsers.add_parser("status", help="Show current index information and metadata")
    status_parser.add_argument("--index-dir", type=str, default=None, help="Custom index directory to inspect")

    # ask subcommand
    ask_parser = subparsers.add_parser("ask", help="Ask a question about the indexed codebase and get grounded answers with citations")
    ask_parser.add_argument("question", type=str, help="Question to ask about the codebase")
    ask_parser.add_argument("--top-k", type=int, default=5, help="Number of evidence chunks to retrieve (default: 5)")
    ask_parser.add_argument("--index-dir", type=str, default=None, help="Custom directory containing the index")
    ask_parser.add_argument("--provider", type=str, default=None, help="LLM provider (e.g. openai, gemini, anthropic, ollama, mock)")
    ask_parser.add_argument("--model", type=str, default=None, help="LLM model name")

    # investigate subcommand
    inv_parser = subparsers.add_parser(
        "investigate",
        help="Investigate potential bugs, test failures, and root causes with grounded citations",
    )
    inv_parser.add_argument(
        "--repo",
        "-r",
        dest="repo_path",
        type=str,
        default=".",
        help="Path to repository to investigate (default: current directory)",
    )
    inv_parser.add_argument(
        "--query",
        "-q",
        type=str,
        required=True,
        help="Bug report, symptom, or error message to investigate",
    )
    inv_parser.add_argument(
        "--target-file",
        type=str,
        default=None,
        help="Specific repository file to inspect",
    )
    inv_parser.add_argument(
        "--target-symbol",
        type=str,
        default=None,
        help="Specific function or class name to trace",
    )
    inv_parser.add_argument(
        "--test-path",
        type=str,
        default=None,
        help="Specific test file or test node to execute",
    )
    inv_parser.add_argument(
        "--run-tests",
        action="store_true",
        default=False,
        help="Run tests in an isolated, timeout-guarded environment",
    )
    inv_parser.add_argument(
        "--format",
        choices=["terminal", "json"],
        default="terminal",
        help="Report output format (default: terminal)",
    )
    inv_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        default=False,
        help="Output machine-readable JSON (alias for --format json)",
    )
    inv_parser.add_argument(
        "--index-dir",
        type=str,
        default=None,
        help="Custom directory containing codebase index",
    )

    # Subcommand: serve
    serve_parser = subparsers.add_parser(
        "serve",
        help="Launch the GitContext Copilot FastAPI backend and web workspace",
    )
    serve_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host interface to bind (default: 127.0.0.1)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port number to listen on (default: 8000)",
    )

    # Subcommand: import-repo
    import_parser = subparsers.add_parser(
        "import-repo",
        help="Import and index a repository directly from GitHub",
    )
    import_parser.add_argument(
        "repository_url",
        type=str,
        help="GitHub repository URL or identifier (e.g. https://github.com/owner/repo or owner/repo)",
    )
    import_parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="GitHub Personal Access Token for private repository access",
    )
    import_parser.add_argument(
        "--branch",
        type=str,
        default=None,
        help="Specific branch or tag to import",
    )
    import_parser.add_argument(
        "--index-dir",
        type=str,
        default=None,
        help="Target index directory path",
    )

    return parser


def cmd_import_repo(
    repository_url: str,
    token: Optional[str] = None,
    branch: Optional[str] = None,
    index_dir_str: Optional[str] = None,
) -> int:
    """Handle the 'import-repo' subcommand."""
    from gitcontext.github_service import GitHubService

    service = GitHubService(token=token)
    print(f"Connecting to GitHub to import: {repository_url} ...")
    try:
        dest_path = service.import_repository(identifier=repository_url, branch=branch)
    except Exception as e:
        print(f"Error importing repository: {e}", file=sys.stderr)
        return 1

    print(f"Repository successfully cloned/downloaded to: {dest_path}")
    print("Indexing codebase with hybrid RAG...")
    return cmd_index(str(dest_path), index_dir_str=index_dir_str)


def cmd_serve(host: str = "127.0.0.1", port: int = 8000) -> int:
    """Handle the 'serve' subcommand."""
    print(f"Starting GitContext Copilot server at http://{host}:{port} ...")
    from gitcontext.server.app import start_server

    start_server(host=host, port=port)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "index":
        return cmd_index(args.repository_path, args.index_dir)
    elif args.command == "search":
        return cmd_search(args.query, top_k=args.top_k, index_dir_str=args.index_dir)
    elif args.command == "status":
        return cmd_status(args.index_dir)
    elif args.command == "ask":
        return cmd_ask(
            question=args.question,
            top_k=args.top_k,
            index_dir_str=args.index_dir,
            provider=args.provider,
            model=args.model,
        )
    elif args.command == "investigate":
        return cmd_investigate(
            query=args.query,
            repo_path_str=args.repo_path,
            target_file=args.target_file,
            target_symbol=args.target_symbol,
            run_tests=args.run_tests,
            test_path=args.test_path,
            index_dir_str=args.index_dir,
            format_type=args.format,
            json_output=args.json_output,
        )
    elif args.command == "import-repo":
        return cmd_import_repo(
            repository_url=args.repository_url,
            token=args.token,
            branch=args.branch,
            index_dir_str=args.index_dir,
        )
    elif args.command == "serve":
        return cmd_serve(host=args.host, port=args.port)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())

