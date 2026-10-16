"""E1 on real P1 cases, using frozen legacy retrievers and official MedCPT classes."""
import sys
import time

from .common import LOCAL, REPO, ROOT, digest, private_path, read, write, write_rows
from .data import inputs, representation
from .upstream import checkout, load_module, versions


def query(case, mode):
    view = representation(case, mode)
    if mode == "full":
        import json
        return json.dumps(view, separators=(",", ":"))
    lines = ["Adult wearable health records. Sleep minutes, sleep timing, Fitbit activity minutes, resting heart rate bpm."]
    for phase, content in view["statistics"].items():
        lines.append(phase + " days " + str(content["day_range"]))
        for metric, stats in content["metrics"].items():
            if "mean" in stats:
                def fmt(v):
                    return "unknown" if v is None else str(round(v, 2))
                lines.append(metric.replace("_", " ") + ": n=" + str(stats["n"]) +
                             " mean=" + fmt(stats["mean"]) + " sd=" + fmt(stats["sd"]) +
                             " slope/day=" + fmt(stats["slope_per_day"]))
            elif "circular_mean_minute" in stats:
                lines.append(metric.replace("_", " ") + ": n=" + str(stats["n"]) +
                             " circular mean minute=" + str(stats["circular_mean_minute"]) +
                             " concentration=" + str(stats["circular_resultant_length"]))
    lines.append("Symptoms, diagnoses, individual age, work schedule, wear time, true activity intensity and timezone unknown. Missing data are unknown; zero RHR is excluded from physiology.")
    return "\n".join(lines)


def run(method, output, *, limit=48, mode="statistics"):
    output = private_path(output)
    if output.exists():
        raise ValueError("Retrieval run exists; choose new version or inspect existing cache")
    cases, corpus = inputs()
    cases = sorted(cases, key=lambda c: c["case_id"])[:limit]
    legacy = load_module(REPO / "src/retrieval.py", "experiment_a_legacy_retrieval")
    prepared = [legacy.truncate_query(query(c, mode), 512) for c in cases]
    texts = [q for q, _ in prepared]
    started = time.monotonic()
    runtime, diagnostics = {}, [{} for _ in texts]
    if method == "bm25":
        retriever = legacy.BM25Retriever(corpus, k1=1.5, b=0.75)
        rankings = [retriever.retrieve(q, len(corpus)) for q in texts]
    elif method == "bge_m3":
        config = read(REPO / "config/retrieval.json")["dense"]
        # Reuse legacy model, revision, pooling, cosine, prefixes and length without tuning.
        retriever = legacy.DenseRetriever(corpus, config, LOCAL / "embeddings/bge")
        rankings, diagnostics = retriever.retrieve_many(texts, len(corpus))
        runtime = retriever.metadata
    elif method in ("medcpt", "medcpt_cross"):
        import numpy as np
        official = load_module(checkout("medcpt") / "evals/models.py", "official_medcpt_models")
        models = read(LOCAL / "medcpt-models.json")
        retriever = official.DenseRetriever(models["Query-Encoder"]["path"], models["Article-Encoder"]["path"],
                                            models["Query-Encoder"]["path"], "cpu")
        key = digest({"corpus": corpus, "models": models})
        cache = LOCAL / "embeddings" / ("medcpt-" + key + ".npy")
        cache.parent.mkdir(parents=True, exist_ok=True)
        if cache.exists():
            embeds = np.load(cache, allow_pickle=False)
        else:
            embeds = retriever.encode_corpus([{"title": k["title"], "text": k["content"]} for k in corpus], batch_size=8).numpy()
            np.save(cache, embeds, allow_pickle=False)
        queries = retriever.encode_queries(texts, batch_size=8).numpy()
        scores = queries @ embeds.T  # Official unnormalized CLS / inner product.
        rankings = [legacy.rank_scores([k["id"] for k in corpus], row.tolist(), len(corpus)) for row in scores]
        diagnostics = [{"model_tokens": len(retriever.tokenizer.encode(q, truncation=False)),
                        "model_max_length": 512,
                        "model_truncated": len(retriever.tokenizer.encode(q, truncation=False)) > 512} for q in texts]
        if method == "medcpt_cross":
            cross = official.CrossEncoder(models["Cross-Encoder"]["path"], models["Cross-Encoder"]["path"], "cpu")
            by_id = {k["id"]: k for k in corpus}
            updated, cross_diag = [], []
            for text, ranking in zip(texts, rankings):
                pool = ranking[:20]
                pairs = [[text, by_id[r["knowledge_id"]]["title"] + "\n" + by_id[r["knowledge_id"]]["content"]] for r in pool]
                lengths = [len(cross.tokenizer.encode(*p, truncation=False)) for p in pairs]
                reranked = legacy.rank_scores([r["knowledge_id"] for r in pool], cross.predict(pairs, batch_size=8), 20)
                # This arm returns only the 20 reranked candidates. Cross and dense scores are not fused.
                updated.append(reranked)
                cross_diag.append({"pool_size": 20, "pair_token_lengths": lengths,
                                   "truncated_pairs": sum(n > 512 for n in lengths), "max_length": 512})
            rankings = updated
            diagnostics = [{**d, "cross_encoder": ce} for d, ce in zip(diagnostics, cross_diag)]
        runtime = {"official_module_sha256": __import__("hashlib").sha256((checkout("medcpt") / "evals/models.py").read_bytes()).hexdigest(),
                   "similarity": "inner_product_not_cosine", "query_max_length": 512,
                   "query_length_note": "evals/models.py uses 512; README standalone query example uses 64",
                   "models": {s: {k: v for k, v in m.items() if k != "path"} for s, m in models.items()}}
    else:
        raise ValueError("Unknown local retriever")
    duration = time.monotonic() - started
    output.mkdir(parents=True)
    predictions = [{"case_id": c["case_id"], "method": method, "information_view": mode,
                    "query": text, "lexical_budget": truncation, "tokenization": diag, "ranking": ranking,
                    "predicted_applicability": None, "score_semantics": "retrieval_relevance_only"}
                   for c, (text, truncation), diag, ranking in zip(cases, prepared, diagnostics, rankings)]
    write_rows(output / "rankings.jsonl", predictions)
    metadata = {"status": "RETRIEVAL_EXECUTED_UNSCORED", "method": method, "cases": len(cases),
                "participants": len({c["subject_id"] for c in cases}), "corpus": len(corpus),
                "information_view": mode, "query_lexical_budget": 512, "full_context": False,
                "lexically_truncated_cases": sum(t["truncated"] for _, t in prepared),
                "model_truncated_cases": sum(bool(d.get("model_truncated")) for d in diagnostics),
                "duration_seconds": duration, "seconds_per_case_amortized": duration/len(cases),
                "llm_calls": 0, "tool_calls": 0, "tokens": None, "api_cost": 0,
                "formal_metrics": None, "gold_status": "PENDING_HUMAN_ANNOTATION",
                "input_fingerprint": digest({"cases": cases, "corpus": corpus, "mode": mode}),
                "runtime": runtime, "versions": versions()}
    write(output / "manifest.json", metadata)
    return metadata
