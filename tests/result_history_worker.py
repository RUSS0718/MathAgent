"""Seed a real reviewed Job, then exit at its committed classified review."""
from tests import star_recovery_worker as worker

STATEMENTS = ["HISTORY-LEGACY-A", "HISTORY-LEGACY-B", "HISTORY-FIRST",
              "HISTORY-SECOND", "HISTORY-INVALID-FIRST", "HISTORY-VALID-LATER",
              "HISTORY-ARCHIVED", "HISTORY-DEPENDENT", "HISTORY-CONJECTURE",
              "HISTORY-UNSELECTED"]


def main():
    worker.CLASSIFIED_CHALLENGE = {
        **worker.CLASSIFIED_CHALLENGE,
        "classified_outcomes": [
            {"category": "Conjecture" if index == 8 else "Lemma",
             "statement": statement, "scope": "boundary case", "claim_indexes": []}
            for index, statement in enumerate(STATEMENTS)
        ],
    }
    worker.main()


if __name__ == "__main__":
    main()
