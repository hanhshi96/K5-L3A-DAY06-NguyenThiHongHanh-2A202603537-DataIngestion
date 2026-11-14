"""Evaluate retrieval evidence; keep human assessment separate."""

import unicodedata


def normalized(text: str) -> str:
    """Normalize Unicode and ignore whitespace from PDF extraction."""
    return "".join(
        unicodedata.normalize("NFC", text).split()
    )


def evaluate_query(question: dict, hits: list[dict]) -> dict:
    """A hit requires the correct document/page and complete evidence."""

    golds = [{
        "source_id": question["gold_source_id"],
        "page": question["gold_page"],
        "evidence_quote": question["evidence_quote"],
    }] + question.get("alternative_gold", [])

    for gold in golds:
        if not gold["evidence_quote"].strip():
            raise ValueError("Gold evidence cannot be empty.")

    flags = []

    for hit in hits[:3]:
        matched = any(
            hit["document_id"] == gold["source_id"]
            and hit["page"] == gold["page"]
            and normalized(gold["evidence_quote"])
            in normalized(hit["text"])
            for gold in golds
        )
        flags.append(matched)

    return {
        "hit_at_1": int(bool(flags and flags[0])),
        "evidence_hit_at_3": int(any(flags)),
        "hit_flags": flags,
        "method": (
            "Correct document/page and complete normalized "
            "gold evidence within one chunk."
        ),
        "human_equivalent_evidence_review": "pending",
    }


def summarize(traces: list[dict]) -> list[dict]:
    """Aggregate results separately by strategy and dev/test split."""

    results = []

    for strategy in ["A", "B", "C"]:
        for split in ["dev", "test"]:
            group = [
                trace for trace in traces
                if trace["strategy"] == strategy
                and trace["split"] == split
            ]

            if not group:
                continue

            filtered = [
                trace for trace in group
                if trace["question"].get("filter")
            ]

            compliant = 0

            for trace in filtered:
                requested_filter = trace["question"]["filter"]
                hits = trace["hits"][:3]

                # Empty retrieval is not counted as filter success.
                if hits and all(
                    all(
                        str(hit["metadata"].get(key)) == str(value)
                        for key, value in requested_filter.items()
                    )
                    for hit in hits
                ):
                    compliant += 1

            results.append({
                "strategy": strategy,
                "split": split,
                "n": len(group),
                "hit1_count": sum(
                    trace["evaluation"]["hit_at_1"]
                    for trace in group
                ),
                "hit3_count": sum(
                    trace["evaluation"]["evidence_hit_at_3"]
                    for trace in group
                ),
                "filter_queries": len(filtered),
                "filter_compliant_queries": compliant,
                "filter_rate": (
                    compliant / len(filtered)
                    if filtered else None
                ),
            })

    return results