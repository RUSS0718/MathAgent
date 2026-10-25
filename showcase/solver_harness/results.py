"""Shared stable identity handling, deliberately independent of fact validity."""


def stable_unique_results(results):
    """Keep the first record for each string result_id, in input order.

    Missing/non-string IDs never collapse (including identical records).
    Empty string is a string identity, matching historical snapshots. Do not
    merge contents, copy records, or choose a more valid/evidenced duplicate:
    callers own copying, eligibility and dependency semantics. In particular,
    finalization deduplicates before filtering, rescue only after filtering.
    """
    unique = []
    seen_ids = set()
    for item in results:
        key = item.get("result_id") if isinstance(item, dict) else None
        if isinstance(key, str):
            if key in seen_ids:
                continue
            seen_ids.add(key)
        unique.append(item)
    return unique
