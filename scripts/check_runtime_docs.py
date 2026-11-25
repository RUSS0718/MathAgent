"""Check local file links in the active Runtime documents."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    "AGENTS.md",
    "README.md",
    "README.zh-CN.md",
    "docs/README.md",
    "docs/agents/issue-tracker.md",
    "docs/engineering/development-gates.md",
    "docs/evals/runtime-deepseek-paired-pilot.md",
    "docs/evals/runtime-deepseek-smoke.md",
    "docs/evals/runtime-minimax-smoke.md",
)
LINK = re.compile(r"\]\((<[^>]+>|[^\s)]+)\)")


def main() -> int:
    errors = []
    for name in DOCUMENTS:
        document = ROOT / name
        for number, line in enumerate(document.read_text(encoding="utf-8").splitlines(), 1):
            for match in LINK.finditer(line):
                url = urlsplit(match[1].strip("<>"))
                if url.scheme or url.netloc or not url.path:
                    continue
                target = unquote(url.path)
                path = (document.parent / target).resolve()
                if not path.is_relative_to(ROOT) or not path.exists():
                    errors.append(f"{name}:{number}: missing repository link {target}")
    if errors:
        print("\n".join(errors))
        return 1
    print(f"Checked local links in {len(DOCUMENTS)} Runtime documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
