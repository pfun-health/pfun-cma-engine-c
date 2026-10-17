#!/usr/bin/env python3
"""Interactive semantic search over the precomputed CMA scenario database.

Each scenario is rendered as a short natural-language document (descriptor
labels + physiological descriptions + headline glucose summary), embedded
with BAAI/bge-small-en-v1.5 (via fastembed/ONNX, no torch required), and
queried by cosine similarity (embeddings are L2-normalised, so cosine ==
dot product).  bge models are retrieval-tuned: queries get an instruction
prefix, documents do not.

Usage:
    python demos/py/scenario_embeddings_demo.py [--db PATH] [--top-k N]
        [--model NAME] [--query TEXT]   # --query runs once, non-interactive
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

from fastembed import TextEmbedding
import numpy as np

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_DB = os.path.join(ROOT, "data", "scenario_buffer.sqlite")


def fmt_clock(hour: float) -> str:
    """Format an hour-of-day value as HH:MM."""
    total = int(round((hour % 24.0) * 60))
    return f"{total // 60 % 24:02d}:{total % 60:02d}"


def collate_query(descriptors: dict[str, object], meal_times: list[float]) -> str:
    """Render a selected state exactly as a scenario corpus document."""
    from scenariogen.descriptors import DIMENSION_ORDER

    parts = []
    for dim in DIMENSION_ORDER:
        desc = descriptors[dim]
        label = desc["label"] if isinstance(desc, dict) else desc.label
        description = (
            desc.get("description") if isinstance(desc, dict) else desc.description
        )
        text = f"{dim.replace('_', ' ')}: {label.replace('_', ' ')}"
        if description:
            text += f" ({description})"
        parts.append(text)
    parts.append("estimated meal times: " + ", ".join(fmt_clock(t) for t in meal_times))
    return ". ".join(parts) + "."


def load_scenarios(db_path: str) -> list[dict]:
    """Load base scenarios (meal-shift variants are excluded from the corpus)."""
    if not os.path.exists(db_path):
        sys.exit(f"Scenario DB not found: {db_path} (run `make scenario-db`)")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    desc = {r["descriptor_id"]: r for r in conn.execute("SELECT * FROM descriptors")}
    out = []
    for r in conn.execute(
        "SELECT scenario_id, slug, title, descriptor_set, params, summary FROM scenarios"
        " WHERE meal_shift IS NULL ORDER BY scenario_id"
    ):
        dset = json.loads(r["descriptor_set"])
        params = json.loads(r["params"])
        summ = json.loads(r["summary"]) if r["summary"] else {}
        descriptor_rows = {
            dim: dict(desc[dset[dim]]) for dim in dset
        }
        doc = collate_query(descriptor_rows, [float(t) for t in params["tM"]])
        if summ:
            doc += (
                f" Mean glucose {summ.get('G_mean', float('nan')):.2f},"
                f" peak {summ.get('G_max', float('nan')):.2f}."
            )
        out.append(
            {
                "id": r["scenario_id"],
                "slug": r["slug"],
                "title": r["title"],
                "descriptors": dset,
                "summary": summ,
                "doc": doc,
            }
        )
    conn.close()
    return out


def embed_corpus(model: TextEmbedding, docs: list[str]) -> np.ndarray:
    """Embed a list of documents and L2-normalize the resulting vectors."""
    vecs = np.asarray(list(model.embed(docs)), dtype=np.float32)
    return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)


def search(model: TextEmbedding, matrix: np.ndarray, query: str, k: int):
    """Search for the top-k most similar scenarios to the given query.
    Args:
        model: The embedding model to use.
        matrix: The L2-normalized document embeddings.
        query: The query string to search for.
        k: The number of top results to return.

    Returns:
        A list of tuples (scenario_index, similarity_score) for the top-k matches.
    """
    # Embed the query and L2-normalize it.
    q = np.asarray(list(model.embed([QUERY_PREFIX + query])), dtype=np.float32)[0]
    q /= np.linalg.norm(q)
    # Compute cosine similarity between the query and all document vectors.
    sims = matrix @ q  # cosine similarity
    idx = np.argsort(-sims)[:k]
    return [(int(i), float(sims[i])) for i in idx]


def show(scenarios, hits) -> None:
    """Display the search results for the given scenarios and hits."""
    for rank, (i, score) in enumerate(hits, 1):
        s = scenarios[i]
        g = s["summary"]
        print(f"{rank}. [{score:.3f}] #{s['id']} {s['title']}")
        if rank == 1:
            print(f"   slug: {s['slug']}")
            if g:
                print(
                    f"   G mean={g.get('G_mean', 0):.3f} "
                    f"max={g.get('G_max', 0):.3f} "
                    f"max meal excursion={g.get('max_meal_excursion', 0):.3f}"
                )
            print(f"   {s['doc']}")


def main() -> None:
    """Main entry point for the scenario embeddings demo.

    This script demonstrates:
        - Loading scenarios from a database.
        - Embedding scenario documents using a text embedding model.
        - Searching for the most similar scenarios to a given query.
        - Recommending the healthiest alternative meal timing based on the search results.

    Arguments:
        --db: Path to the database containing scenarios.
        --model: Name of the embedding model to use.
        --top-k: Number of top results to return for each query.
        --query: Run a single query and exit.
    """
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])  # type: ignore
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--query", help="Run a single query and exit")
    args = ap.parse_args()

    try:
        from fastembed import TextEmbedding
    except ImportError:
        sys.exit("fastembed missing: run `uv sync --group demo`")

    # Load scenarios from the database and embed their documents.
    scenarios = load_scenarios(args.db)
    print(f"Loaded {len(scenarios)} scenarios; loading model {args.model} ...")
    model = TextEmbedding(model_name=args.model)
    matrix = embed_corpus(model, [s["doc"] for s in scenarios])
    print(f"Embedded corpus: {matrix.shape[0]} x {matrix.shape[1]}")

    if args.query:
        show(scenarios, search(model, matrix, args.query, args.top_k))
        return

    print(
        "Describe a day/state (e.g. 'anxious, skipped breakfast, slept badly'). "
        "Empty line or 'quit' exits."
    )
    while True:
        try:
            q = input("\nquery> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q or q.lower() in {"q", "quit", "exit"}:
            break
        show(scenarios, search(model, matrix, q, args.top_k))


if __name__ == "__main__":
    main()
