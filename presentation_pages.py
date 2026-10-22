"""Render local presentation pages using the frontend's single design token source.

This module uses only the standard library and is never imported by user_agent.
The legacy servers remain usable without a Node build or Showcase dependencies.
"""

from pathlib import Path

FRONTEND = Path(__file__).resolve().parent / "showcase" / "frontend"


def render_presentation_page(kind: str) -> str:
    """Build one fixed local page; callers supply a code-owned page name."""
    titles = {
        "demo": "数学推理智能体 Demo",
        "showcase": "MathAgent Showcase Workbench",
        "unbuilt": "MathAgent Showcase Workbench",
    }
    styles = FRONTEND / "chat-frontend" / "src" / "styles"
    css = "\n".join(
        (styles / name).read_text(encoding="utf-8")
        for name in ("tokens.css", "reset.css", "primitives.css", "review.css")
    )
    legacy = FRONTEND / "legacy"
    css += (legacy / "legacy.css").read_text(encoding="utf-8")
    body = (legacy / f"{kind}.html").read_text(encoding="utf-8")
    script = "" if kind == "unbuilt" else (legacy / "solve.js").read_text(encoding="utf-8")
    title = titles[kind]
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title><style>{css}</style></head>"
        f'<body data-page="{kind}"><a class="skip-link" href="#main-content">跳到主要内容</a>'
        f'<header class="app-header"><strong>MathAgent</strong><span class="muted">本地展示</span></header>'
        f'<main id="main-content" class="page-content legacy-content"><h1>{title}</h1>{body}</main>'
        '<footer class="page-footer">本地展示入口 · 不代表独立数学能力评测</footer>'
        f"<script>{script}</script></body></html>"
    )
