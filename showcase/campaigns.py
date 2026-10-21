"""Paired orchestration delegates all execution and control to Workspace Jobs."""

import uuid

from .adapters import AdapterError
from .campaign_contract import digest, source_identity, validate_campaign
from .campaign_store import CampaignStore
from .run_budget import RunBudgetLimits
from .run_service import RunNotFoundError
from .workspace import WorkspaceError


class CampaignService:
    def __init__(self, workspace, runs, database_path, archive_root, *, live_enabled=False):
        self.workspace, self.runs = workspace, runs
        self.store = CampaignStore(database_path, archive_root)
        self.live_enabled = live_enabled

    def create(self, user_id, key, body):
        try:
            if str(uuid.UUID(key, version=4)) != key or uuid.UUID(key).version != 4:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise WorkspaceError("idempotency_key_invalid") from None
        config = validate_campaign(body)
        self._check_execution(config["common"])
        with self.store.lock:
            document, existing = self.store.claim(user_id, key, config, source_identity())
            if existing:
                return document
            document["mode"] = getattr(self.workspace.pipeline, "execution_mode", "fake")
            for pair, problem in zip(document["pairs"], config["problems"], strict=True):
                for arm_name, arm in pair["arms"].items():
                    try:
                        session_id = self.workspace.create_session(user_id)
                        job, _ = self.workspace.create_job(
                            user_id=user_id,
                            session_id=session_id,
                            problem=problem["problem"],
                            idempotency_key=arm["idempotency_key"],
                            verification_mode=config["strategies"][arm_name]["verification_mode"],
                            budget_limits=RunBudgetLimits(**config["common"]["budget"]),
                        )
                        arm.update(
                            job_id=job["job_id"],
                            status=job["status"],
                            strategy_status="applied",
                            applied_fields=config["strategies"][arm_name],
                            strategy_hash=digest(config["strategies"][arm_name]),
                        )
                    except WorkspaceError as exc:
                        arm.update(status="failed", error=exc.code)
                    self.store.save(document, user_id)
            return document

    def _check_execution(self, common):
        workspace = self.workspace
        if not common["allow_network"]:
            if workspace.execution_mode != "fake" or workspace.pipeline is not None:
                raise WorkspaceError("campaign_network_disabled", status=409)
            return
        if (
            not self.live_enabled
            or workspace.execution_mode != "live"
            or workspace.pipeline is None
        ):
            raise WorkspaceError("campaign_live_unavailable", status=503)
        model = workspace.pipeline.model
        try:
            client = model._get_client()
        except AdapterError:
            raise WorkspaceError("campaign_live_unavailable", status=503) from None
        if model.model_id != "intern-s2" or getattr(client, "model", None) != "intern-s2":
            raise WorkspaceError("campaign_model_mismatch", status=409)
        conditions = common["conditions"]
        if (
            model.max_tokens != conditions["max_tokens"]
            or model.thinking_mode is not conditions["thinking_mode"]
        ):
            raise WorkspaceError("campaign_conditions_mismatch", status=409)

    def detail(self, campaign_id, user_id):
        with self.store.lock:
            document = self.store.get(campaign_id, user_id)
            for pair in document["pairs"]:
                for arm in pair["arms"].values():
                    if arm["job_id"]:
                        self._refresh_arm(arm, user_id)
                pair["status"] = (
                    "completed"
                    if all(
                        a["status"] in {"succeeded", "failed", "canceled"}
                        for a in pair["arms"].values()
                    )
                    else "incomplete"
                )
            document["status"] = (
                "completed"
                if all(p["status"] == "completed" for p in document["pairs"])
                else "incomplete"
            )
            document["summary"] = {
                "total_pairs": len(document["pairs"]),
                "completed_pairs": sum(p["status"] == "completed" for p in document["pairs"]),
                "successful_pairs": sum(
                    all(a["status"] == "succeeded" for a in p["arms"].values())
                    for p in document["pairs"]
                ),
                "mathematical_improvement": "not_evaluated",
            }
            arms = [a for p in document["pairs"] for a in p["arms"].values()]
            document["consumption"] = {
                "scope": "this_campaign_only",
                "project_total": None,
                "deployment_total": None,
                "http_attempts": sum(a["usage"]["http_attempts"] or 0 for a in arms),
                "unknown_attempts": sum(a["usage"]["unknown_attempts"] or 0 for a in arms),
                "incomplete_arms": sum(
                    a["status"] not in {"succeeded", "failed", "canceled"} for a in arms
                ),
                "cost": None,
                "deterministic_tool_cost": None,
                "tool_wall_time_seconds": sum(
                    (a.get("budget") or {}).get("tool_wall_time_seconds", 0) for a in arms
                ),
            }
            document.pop("archive", None)
            document["archive"] = self.store.archive(campaign_id, "report", document)
            return document

    def _refresh_arm(self, arm, user_id):
        job_id = arm["job_id"]
        try:
            # Flask's Run and Workspace repositories share one SQLite connection.
            # Read the public projections under its existing writer lock.
            with self.workspace.store._lock:
                job = self.workspace.get_job(job_id, user_id)
                snapshot = self.runs.get_run(job_id)
                events = self.runs.get_events(job_id)
        except (WorkspaceError, RunNotFoundError):
            arm.update(status="unknown", error="child_unavailable")
            return
        result = job.get("result", {})
        attempts = result.get("request_attempts", [])
        budget = result.get("budget") or {}
        verification = result.get("verification", {"status": "unknown"})
        arm.update(
            status=job["status"],
            error=job.get("error"),
            quality=verification,
            requested_model="intern-s2",
            returned_models=sorted(
                {a["returned_model"] for a in attempts if a.get("returned_model")}
            ),
            request_attempts=attempts,
            budget=budget,
            cost=None,
            usage={
                "http_attempts": budget.get("http_attempts", len(attempts)),
                "provider_known": budget.get("provider_known"),
                "provider_unknown_fields": budget.get("provider_unknown_fields"),
                "unknown_attempts": budget.get("unknown_attempts"),
            },
            latency_seconds=budget.get("wall_time_seconds"),
            report_url=f"/api/agent/jobs/{job_id}/report",
            evidence_url=f"/api/runs/{job_id}/evidence",
            run_hash=digest(snapshot),
            events_hash=digest(events),
        )
        if job["status"] in {"succeeded", "failed", "canceled"}:
            exporter = self._exporter()
            evidence = exporter.export(snapshot, events=events, verification=verification)
            arm["evidence_hash"] = digest(evidence)
            arm["artifacts"] = [
                self.store.archive(arm["job_id"], "run", snapshot),
                self.store.archive(arm["job_id"], "evidence", evidence),
            ]

    @staticmethod
    def _exporter():
        from .evidence import EvidencePackExporter

        return EvidencePackExporter()
