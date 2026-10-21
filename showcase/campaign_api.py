"""Campaign HTTP routes share the Workspace authentication and CSRF boundary."""

from flask import Blueprint, g, jsonify, request

from .campaigns import CampaignService
from .workspace import WorkspaceError


def register_campaigns(app, workspace, runs, database_path, storage_root):
    service = CampaignService(
        workspace,
        runs,
        database_path,
        storage_root / "campaigns",
        live_enabled=app.config.get("SHOWCASE_CAMPAIGNS_LIVE_ENABLED", False) is True,
    )
    app.extensions["showcase_campaign_service"] = service
    routes = Blueprint("campaigns", __name__, url_prefix="/api/experiments/campaigns")

    def user_id():
        if g.auth_session is None:
            raise WorkspaceError("auth_required", status=401)
        return g.auth_session.user_id

    @routes.post("")
    def create():
        body = request.get_json(silent=True)
        document = service.create(user_id(), request.headers.get("Idempotency-Key"), body)
        return jsonify(document), 202

    @routes.get("")
    def list_campaigns():
        try:
            offset, limit = int(request.args.get("offset", 0)), int(request.args.get("limit", 20))
            if offset < 0 or not 1 <= limit <= 100:
                raise ValueError()
        except ValueError:
            raise WorkspaceError("pagination_invalid") from None
        documents = service.store.list(user_id(), offset, limit)
        summaries = []
        for item in documents:
            item = service.detail(item["campaign_id"], user_id())
            summaries.append(
                {
                    key: item[key]
                    for key in ("campaign_id", "mode", "status", "summary", "common_hash")
                }
            )
        return jsonify({"campaigns": summaries, "offset": offset, "limit": limit})

    @routes.get("/<campaign_id>")
    def detail(campaign_id):
        return jsonify(service.detail(campaign_id, user_id()))

    app.register_blueprint(routes)
