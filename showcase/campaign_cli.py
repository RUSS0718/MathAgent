"""Campaign CLI uses the same authenticated HTTP contract as Workbench."""

import json
from pathlib import Path


def add_campaign_parser(subparsers):
    parser = subparsers.add_parser("campaign", help="explicit paired experiment campaigns")
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create")
    create.add_argument(
        "input", type=Path, help="external campaign JSON; datasets are not shipped in Git"
    )
    create.add_argument("--idempotency-key", required=True)
    listing = actions.add_parser("list")
    listing.add_argument("--offset", type=int, default=0)
    listing.add_argument("--limit", type=int, default=20)
    detail = actions.add_parser("detail")
    detail.add_argument("campaign_id")


def run_campaign(client, args):
    path = "/api/experiments/campaigns"
    if args.action == "create":
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        return client.request(
            "POST", path, payload=payload, headers={"Idempotency-Key": args.idempotency_key}
        )
    if args.action == "detail":
        return client.request("GET", f"{path}/{args.campaign_id}")
    return client.request("GET", f"{path}?offset={args.offset}&limit={args.limit}")
