"""Re-evaluate serial routes after additive graph evolution, without reviving losses."""

from copy import deepcopy


def refreshed_routes(state):
    graph = state.get("proof_graph") or {}
    snapshots = {item["graph_version"]: item for item in graph.get("snapshots", [])}
    current = snapshots.get(graph.get("current_version"))
    if current is None or any(item.get("kind") == "problem_spec_change"
                              for item in state.get("failure_records", [])):
        return None
    routes = deepcopy(state.get("route_registry", []))
    changed = False
    for route in routes:
        if not route.get("needs_reevaluation") or route.get("status") != "active":
            continue
        previous = snapshots.get(route.get("graph_version"))
        if previous is None:
            continue
        # A new conflict or withdrawn support requires the
        # existing hard stop. Mere bootstrap/additional support does not.
        history = [item for version, item in snapshots.items()
                   if route.get("graph_version") < version <= graph["current_version"]]
        if any(item.get("conflict") or item.get("status") in {"invalidated", "refuted"}
               for snapshot in history for item in snapshot.get("propositions", {}).values()):
            continue
        if any(item.get("status") == "invalidated"
               for snapshot in history for collection in ("attempts", "derivations")
               for item in snapshot.get(collection, {}).values()):
            continue
        chain = [previous, *sorted(history, key=lambda item: item["graph_version"])]
        if any(after.get(collection, {}).get(key, {}).get("status") != status
               for before, after in zip(chain, chain[1:])
               for collection, status in (("attempts", "accepted"), ("derivations", "accepted"),
                                          ("propositions", "supported"))
               for key, item in before.get(collection, {}).items()
               if item.get("status") == status):
            continue
        previous_rejections = previous.get("not_imported_records", [])
        current_rejections = current.get("not_imported_records", [])
        previous_sources = {item.get("result_id") for item in previous.get("derivations", {}).values()}
        if (any(item not in current_rejections for item in previous_rejections)
                or any(item not in previous_rejections
                       and (item.get("reason") != "conjecture_not_importable"
                            or item.get("source_id") in previous_sources)
                       for item in current_rejections)):
            continue
        preserved = all(
            current.get(collection, {}).get(key, {}).get("status") == "accepted"
            for collection in ("attempts", "derivations")
            for key, item in previous.get(collection, {}).items()
            if item.get("status") == "accepted"
        ) and all(
            current.get("propositions", {}).get(key, {}).get("status") == "supported"
            for key, item in previous.get("propositions", {}).items()
            if item.get("status") == "supported"
        )
        if preserved:
            route["needs_reevaluation"] = False
            changed = True
    return routes if changed else None
