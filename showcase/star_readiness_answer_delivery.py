"""Explicit, exclusive output for public answers, separate from sanitized archives."""

import json
from pathlib import Path


class AnswerOutput:
    """Reserve an ignored JSONL file before dispatch and flush each collected answer."""

    def __init__(self, path, *, artifacts, archive):
        self.path = Path(path).resolve()
        root, archive = Path(artifacts).resolve(), Path(archive).resolve()
        answer_dir = (root / "issue-97-answers").resolve()
        if (answer_dir.parent != root or self.path.parent != answer_dir
                or self.path.is_relative_to(archive) or archive.is_relative_to(self.path)
                or any((answer_dir / name).exists()
                       for name in ("registration.json", "result.json", "hashes.json"))):
            raise ValueError("star_readiness_answer_path_invalid")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.stream = self.path.open("x", encoding="utf-8", newline="\n")
        except FileExistsError:
            raise ValueError("star_readiness_answer_already_exists") from None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stream.close()

    def __call__(self, question_id, job_id, final_response):
        """Copy only the public final response and its batch identity."""
        if not isinstance(final_response, str) or not final_response.strip():
            return
        self.stream.write(json.dumps({
            "question_id": question_id, "job_id": job_id, "final_response": final_response,
        }, ensure_ascii=False) + "\n")
        self.stream.flush()
