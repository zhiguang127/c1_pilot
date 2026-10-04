"""Frozen, corpus-shared BM25 and dense retrieval for the four pilot baselines."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import re
from typing import Any


TOKEN_PATTERN = r"[^\W_]+(?:['-][^\W_]+)*"
TOKENIZER = re.compile(TOKEN_PATTERN, re.UNICODE)
RETRIEVAL_REVISION = "retrieval-v1"


def read_jsonl(path: str | Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: str | Path, value: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, records: list[dict]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def tokenize(text: str) -> list[str]:
    return TOKENIZER.findall(text.casefold())


def truncate_query(text: str, maximum_tokens: int) -> tuple[str, dict]:
    """Keep original prose, bounded by the same lexical-token rule for all methods."""
    matches = list(TOKENIZER.finditer(text))
    if maximum_tokens < 1:
        raise ValueError("query_max_tokens must be positive")
    truncated = text[:matches[maximum_tokens - 1].end()] if len(matches) > maximum_tokens else text
    return truncated, {"original_tokens": len(matches), "used_tokens": min(len(matches), maximum_tokens),
                       "truncated": len(matches) > maximum_tokens}


def rank_scores(knowledge_ids: list[str], scores: list[float], top_k: int) -> list[dict]:
    if len(knowledge_ids) != len(scores):
        raise ValueError("Document IDs and scores have different lengths")
    if any(not math.isfinite(float(score)) for score in scores):
        raise ValueError("Non-finite retrieval score")
    ordered = sorted(zip(knowledge_ids, scores), key=lambda pair: (-float(pair[1]), pair[0]))
    return [{"rank": position, "knowledge_id": item_id, "score": float(score)}
            for position, (item_id, score) in enumerate(ordered[:top_k], start=1)]


class BM25Retriever:
    def __init__(self, corpus: list[dict], k1: float = 1.5, b: float = 0.75):
        self.ids = [item["id"] for item in corpus]
        self.documents = [Counter(tokenize(item["title"] + "\n" + item["content"])) for item in corpus]
        self.lengths = [sum(document.values()) for document in self.documents]
        self.average_length = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        self.k1, self.b = k1, b
        frequencies: Counter = Counter()
        for document in self.documents:
            frequencies.update(document.keys())
        self.idf = {token: math.log(1 + (len(corpus) - count + 0.5) / (count + 0.5))
                    for token, count in frequencies.items()}

    def retrieve(self, query: str, top_k: int) -> list[dict]:
        query_terms = Counter(tokenize(query))
        if not query_terms:
            return []
        scores = []
        for document, length in zip(self.documents, self.lengths):
            normalization = self.k1 * (1 - self.b + self.b * length / (self.average_length or 1))
            score = sum(query_count * self.idf.get(term, 0.0) * document.get(term, 0) * (self.k1 + 1)
                        / (document.get(term, 0) + normalization)
                        for term, query_count in query_terms.items())
            scores.append(score)
        return rank_scores(self.ids, scores, top_k)


class DenseRetriever:
    def __init__(self, corpus: list[dict], config: dict, cache_dir: Path):
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise RuntimeError("Dense retrieval requires numpy, torch and sentence-transformers") from error
        self.np = np
        self.ids = [item["id"] for item in corpus]
        self.config = config
        model_name = config["model"]
        revision = config["revision"]
        if not re.fullmatch(r"[a-fA-F0-9]{40}", revision):
            raise ValueError("dense.revision must be an immutable 40-character model commit")
        if config.get("similarity", "cosine") != "cosine":
            raise ValueError("This implementation freezes dense similarity to cosine")
        self.model = SentenceTransformer(model_name, revision=revision, device=config.get("device", "cpu"),
                                         trust_remote_code=False)
        self.model.max_seq_length = config.get("max_length", 512)
        self.batch_size = config.get("batch_size", 32)
        self.query_prefix = config.get("query_prefix", "")
        self.document_prefix = config.get("document_prefix", "")
        documents = [self.document_prefix + item["title"] + "\n" + item["content"] for item in corpus]
        document_token_lengths = [len(self.model.tokenizer.encode(document, add_special_tokens=True, truncation=False))
                                  for document in documents]
        key = sha256_json({"ids": self.ids, "documents": documents, "model": model_name,
                           "revision": revision, "max_length": self.model.max_seq_length})
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"corpus_embeddings_{key}.npy"
        if cache_path.exists():
            self.embeddings = np.load(cache_path, allow_pickle=False)
        else:
            self.embeddings = self.model.encode(documents, batch_size=self.batch_size,
                                                normalize_embeddings=True, convert_to_numpy=True,
                                                show_progress_bar=True)
            np.save(cache_path, self.embeddings, allow_pickle=False)
        if self.embeddings.ndim != 2 or self.embeddings.shape[0] != len(corpus) or not np.all(np.isfinite(self.embeddings)):
            raise ValueError("Invalid dense corpus embeddings")
        if not np.allclose(np.linalg.norm(self.embeddings, axis=1), 1.0, atol=1e-4):
            raise ValueError("Dense corpus embeddings are not normalized")
        pooling_configs = [module.get_config_dict() for module in self.model
                           if type(module).__name__ == "Pooling"]
        self.metadata = {"embedding_cache_sha256": key, "embedding_dimension": int(self.embeddings.shape[1]),
                         "model": model_name, "revision": revision, "max_length": self.model.max_seq_length,
                         "similarity": "cosine", "normalized_embeddings": True,
                         "pooling": pooling_configs,
                         "document_model_token_counts": dict(zip(self.ids, document_token_lengths)),
                         "truncated_document_ids": [item_id for item_id, length in zip(self.ids, document_token_lengths)
                                                    if length > self.model.max_seq_length],
                         "runtime_versions": {package: version(package) for package in
                                              ("numpy", "torch", "sentence-transformers", "transformers")}}

    def retrieve_many(self, queries: list[str], top_k: int) -> tuple[list[list[dict]], list[dict]]:
        if not queries:
            return [], []
        texts = [self.query_prefix + query for query in queries]
        token_lengths = [len(self.model.tokenizer.encode(text, add_special_tokens=True, truncation=False))
                         for text in texts]
        query_embeddings = self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True,
                                             convert_to_numpy=True, show_progress_bar=False)
        scores = query_embeddings @ self.embeddings.T
        rankings = [rank_scores(self.ids, row.tolist(), top_k) for row in scores]
        diagnostics = [{"model_tokens_including_prefix": length,
                        "model_truncated": length > self.model.max_seq_length,
                        "model_max_length": self.model.max_seq_length} for length in token_lengths]
        return rankings, diagnostics


def reciprocal_rank_fusion(rankings: list[list[dict]], top_k: int, rank_constant: int = 60) -> list[dict]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for item in ranking:
            item_id = item["knowledge_id"]
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (rank_constant + item["rank"])
    return rank_scores(list(scores), list(scores.values()), top_k)


def representation_queries(record: dict) -> list[str]:
    if record.get("status", record.get("metadata", {}).get("status", "ok")) not in {"ok", "success", "completed"}:
        return []
    baseline = record["baseline_id"]
    if baseline == "B3":
        queries = record.get("queries")
        if not isinstance(queries, list) or len(queries) != 5 or any(not isinstance(query, str) or not query.strip()
                                                                  for query in queries):
            raise ValueError(f"{record['case_id']} B3 requires exactly five non-empty queries")
        return queries
    text = record.get("text", "")
    if not isinstance(text, str):
        raise ValueError("Representation text must be a string")
    return [text] if text.strip() else []


def normalize_config(config: dict) -> dict:
    result = dict(config)
    if result.get("indexed_fields", ["title", "content"]) != ["title", "content"]:
        raise ValueError("Only title + content may be indexed")
    result["indexed_fields"] = ["title", "content"]
    result.setdefault("top_k", 20)
    result.setdefault("query_max_tokens", 512)
    result.setdefault("bm25", {"k1": 1.5, "b": 0.75})
    result.setdefault("rrf_k", 60)
    result["tokenizer"] = {"pattern": TOKEN_PATTERN, "unicode": True, "casefold": True,
                           "stemming": False, "stopword_removal": False}
    result["tie_breaking"] = "knowledge_id ascending"
    result["b3_fusion"] = "RRF over five independently retrieved top-k lists"
    if result["top_k"] != 20 or result["rrf_k"] != 60:
        raise ValueError("Pilot top_k=20 and RRF k=60 are frozen")
    if not 0 <= result["bm25"]["b"] <= 1 or result["bm25"]["k1"] <= 0:
        raise ValueError("Invalid BM25 parameters")
    return result


def run(corpus_path: Path, representations_path: Path, config_path: Path, output_dir: Path,
        retrievers: list[str]) -> dict:
    corpus = sorted(read_jsonl(corpus_path), key=lambda item: item["id"])
    if not corpus or len({item["id"] for item in corpus}) != len(corpus):
        raise ValueError("Corpus must be nonempty and contain unique knowledge IDs")
    if any(item.get("status") != "verified" or not item.get("content", "").strip() for item in corpus):
        raise ValueError("Only verified nonempty knowledge items can enter retrieval")
    representations = read_jsonl(representations_path)
    keys = [(record["case_id"], record["baseline_id"], str(record["repeat_id"])) for record in representations]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate representation case/baseline/repeat key")
    if any(record["baseline_id"] not in {"B1", "B2", "B3", "B4"} for record in representations):
        raise ValueError("Unknown baseline ID")
    config = normalize_config(json.loads(config_path.read_text(encoding="utf-8-sig")))
    config_hash = sha256_json(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    corpus_hash = sha256_json(corpus)
    prepared = []
    all_queries = []
    for record in representations:
        original_queries = representation_queries(record)
        truncated = [truncate_query(query, config["query_max_tokens"]) for query in original_queries]
        start = len(all_queries)
        all_queries.extend(query for query, _ in truncated)
        prepared.append((record, truncated, start))
    manifest = {"revision": RETRIEVAL_REVISION, "config": config, "config_sha256": config_hash,
                "corpus_sha256": corpus_hash, "representations_sha256": sha256_json(representations),
                "corpus_count": len(corpus), "representation_count": len(representations),
                "bm25_idf": "log(1 + (N - df + 0.5) / (df + 0.5))",
                "bm25_query_term_frequency": "linear multiplicity, without k3 saturation",
                "retrievers_requested": retrievers, "retrievers_completed": []}
    write_json(output_dir / "manifest.json", manifest)
    for retriever_name in retrievers:
        if retriever_name == "bm25":
            retriever = BM25Retriever(corpus, **config["bm25"])
            all_rankings = [retriever.retrieve(query, config["top_k"]) for query in all_queries]
            dense_diagnostics = [{} for _ in all_queries]
        elif retriever_name == "dense":
            if "dense" not in config:
                raise ValueError("Config requires dense model and immutable revision")
            retriever = DenseRetriever(corpus, config["dense"], output_dir / "embedding_cache")
            all_rankings, dense_diagnostics = retriever.retrieve_many(all_queries, config["top_k"])
            manifest["dense_runtime"] = retriever.metadata
        else:
            raise ValueError(f"Unsupported retriever {retriever_name}")
        results = []
        for record, truncated, start in prepared:
            count = len(truncated)
            per_query_rankings = all_rankings[start:start + count]
            if record["baseline_id"] == "B3":
                ranking = reciprocal_rank_fusion(per_query_rankings, config["top_k"], config["rrf_k"])
            else:
                ranking = per_query_rankings[0] if per_query_rankings else []
            query_records = [{"query_index": index, "query": query, **diagnostic,
                              **dense_diagnostics[start + index], "ranking": per_query_rankings[index]}
                             for index, (query, diagnostic) in enumerate(truncated)]
            results.append({"case_id": record["case_id"], "baseline_id": record["baseline_id"],
                            "repeat_id": record["repeat_id"], "retriever": retriever_name,
                            "representation_status": record.get("status", record.get("metadata", {}).get("status", "ok")),
                            "representation_input_sha256": record.get("input_sha256"),
                            "config_sha256": config_hash, "corpus_sha256": corpus_hash,
                            "fusion": "five-query RRF" if record["baseline_id"] == "B3" else "single-query",
                            "ranking": ranking, "queries": query_records})
        write_jsonl(output_dir / f"{retriever_name}.jsonl", results)
        manifest["retrievers_completed"].append(retriever_name)
        write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--representations", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--retrievers", default="bm25,dense")
    args = parser.parse_args()
    manifest = run(args.corpus, args.representations, args.config, args.output_dir, args.retrievers.split(","))
    print(json.dumps({"completed": manifest["retrievers_completed"], "config_sha256": manifest["config_sha256"]}))


if __name__ == "__main__":
    main()
