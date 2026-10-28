"""Isolated public #102 fixtures; never use provider or sockets."""
import time


def plan(phase="O", count=2):
    return dict(registration_id="diagnostic-test", phase=phase, seed=17, endpoint="offline://socket-free",
                window=dict(start=time.time() - 10, end=time.time() + 1800),
                conditions_met=True, requests=[dict(
                    question="Prove 1+1=2", prompt="Give a complete proof.",
                    schema={"type": "object"}, arm=f"arm-{i}", question_id=f"q-{i}",
                    timeout_seconds=1800 if phase != "P" else 900, stream=False,
                ) for i in range(count)])
