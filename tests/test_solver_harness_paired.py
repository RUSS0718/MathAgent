"""Public paired-run contracts: isolation, equal conditions and retained failures."""

import tempfile
import unittest
from pathlib import Path

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort

CONDITIONS = {
    "models": {
        "reasoner": {"model_id": "scripted", "revision": "fixture-1"},
        "verifier": {"model_id": "scripted", "revision": "fixture-1"},
    },
    "transport": {
        "max_output_tokens": 1024,
        "timeout_seconds": 30,
        "physical_attempts_per_call": 1,
    },
}
BASE = {
    "profile": "paired-offline",
    "max_model_calls": 2,
    "max_tool_calls": 0,
    "max_total_duration_seconds": 60,
    "features": {"skills": False},
}


def ports(source="scripted"):
    return {
        "model_port": ScriptedModelPort([{"assessment": "SOLVED", "solution_candidate": "4"}]),
        "verifier_port": ScriptedVerifierPort([{"verdict": "ACCEPT"}]),
        "source": source,
    }


class PairedRunTest(unittest.TestCase):
    def test_pair_uses_independent_runs_and_recovers_exact_report_without_dispatch(self):
        from showcase.solver_harness.paired import PairedRunner

        control, variant = ports(), ports()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pairs.sqlite3"
            with PairedRunner(database_path=path) as runner:
                report = runner.run_pair(
                    "2+2",
                    pair_id="pair",
                    control_config=BASE,
                    variant_config={**BASE, "features": {"skills": True}},
                    conditions=CONDITIONS,
                    control_ports=control,
                    variant_ports=variant,
                )
                self.assertEqual(report, runner.get_report("pair"))
            with PairedRunner(database_path=path) as recovered:
                self.assertEqual(report, recovered.get_report("pair"))
        arms = report["arms"]
        self.assertNotEqual(arms["control"]["run_id"], arms["variant"]["run_id"])
        self.assertEqual("completed_llm_reviewed", arms["control"]["result"]["state"]["status"])
        self.assertEqual("completed_llm_reviewed", arms["variant"]["result"]["state"]["status"])
        self.assertIsNone(arms["control"]["usage"]["total_tokens"])
        self.assertIsNone(arms["control"]["cost"])
        self.assertEqual("monotonic_wall_clock", arms["control"]["duration_source"])
        self.assertEqual("needs_review", report["live_gate"])
        self.assertEqual(
            "SH21_live_tool_loop_unavailable; paired_live_not_run",
            report["live_gate_reason"],
        )
        self.assertNotIn("prompt_layers", str(report))

    def test_provider_live_source_requires_pinned_provider_transport(self):
        from showcase.solver_harness.paired import PairedRunner

        control, variant = ports("provider_live"), ports("provider_live")
        with (
            tempfile.TemporaryDirectory() as directory,
            PairedRunner(database_path=Path(directory) / "pair.db") as runner,
        ):
            with self.assertRaisesRegex(ValueError, "pinned_transport"):
                runner.run_pair(
                    "2+2",
                    control_config=BASE,
                    variant_config={**BASE, "features": {"skills": True}},
                    conditions=CONDITIONS,
                    control_ports=control,
                    variant_ports=variant,
                )

        self.assertEqual([], control["model_port"].requests)
        self.assertEqual([], variant["model_port"].requests)

    def test_provider_adapter_cannot_claim_offline_injected_source(self):
        import os
        from copy import deepcopy
        from unittest.mock import patch

        from llm_client import InternChatClient
        from showcase.adapters import InternModelAdapter
        from showcase.solver_harness.intern_port import InternModelPort
        from showcase.solver_harness.paired_conditions import validate_conditions

        conditions = deepcopy(CONDITIONS)
        conditions["models"]["reasoner"] = {
            "model_id": "intern-s2",
            "revision": "service-label-only",
        }

        def provider_ports():
            client = InternChatClient(timeout=30, retry=1)
            return {
                "model_port": InternModelPort(
                    InternModelAdapter(
                        client,
                        model_id="intern-s2",
                        max_tokens=1024,
                        client_timeout=30,
                        client_retry=1,
                    )
                ),
                "source": "offline_injected",
            }

        config = {**BASE, "features": {"skills": False, "stream_recovery": True}}
        with patch.dict(os.environ, {"INTERN_API_KEY": "test-key", "INTERN_MODEL": "intern-s2"}):
            control, variant = provider_ports(), provider_ports()
            with self.assertRaisesRegex(ValueError, "offline"):
                validate_conditions(
                    config,
                    {**config, "features": {"skills": True, "stream_recovery": True}},
                    conditions,
                    (control, variant),
                    "skills",
                )

    def test_provider_live_source_accepts_only_pinned_intern_transport(self):
        import os
        from copy import deepcopy
        from unittest.mock import patch

        from llm_client import InternChatClient
        from showcase.adapters import InternModelAdapter
        from showcase.request_transport import INTERN_S2_LIVE_ENDPOINT
        from showcase.solver_harness.intern_port import InternModelPort
        from showcase.solver_harness.paired_conditions import validate_conditions

        conditions = deepcopy(CONDITIONS)
        conditions["models"]["reasoner"] = {
            "model_id": "intern-s2",
            "revision": "service-label-only",
        }
        config = {**BASE, "features": {"skills": False, "stream_recovery": True}}

        def provider_ports():
            client = InternChatClient(
                timeout=30, retry=1, provider_endpoint_only=True
            )
            self.assertEqual(INTERN_S2_LIVE_ENDPOINT, client.api_base)
            return {
                "model_port": InternModelPort(
                    InternModelAdapter(
                        client,
                        model_id="intern-s2",
                        max_tokens=1024,
                        client_timeout=30,
                        client_retry=1,
                    )
                ),
                "source": "provider_live",
            }

        with patch.dict(os.environ, {"INTERN_API_KEY": "test-key", "INTERN_MODEL": "intern-s2"}):
            validation = validate_conditions(
                config,
                {**config, "features": {"skills": True, "stream_recovery": True}},
                conditions,
                (provider_ports(), provider_ports()),
                "skills",
            )
        self.assertEqual("observed", validation["identity_status"])

    def test_provider_live_requires_a_model_port_on_both_arms(self):
        import os
        from copy import deepcopy
        from unittest.mock import patch

        from llm_client import InternChatClient
        from showcase.adapters import InternModelAdapter
        from showcase.request_transport import INTERN_S2_LIVE_ENDPOINT
        from showcase.solver_harness.intern_port import InternModelPort
        from showcase.solver_harness.paired_conditions import validate_conditions

        conditions = deepcopy(CONDITIONS)
        conditions["models"]["verifier"] = {
            "model_id": "intern-s2",
            "revision": "service-label-only",
        }
        config = {**BASE, "features": {"skills": False, "stream_recovery": True}}

        def verifier_port():
            client = InternChatClient(timeout=30, retry=1, provider_endpoint_only=True)
            self.assertEqual(INTERN_S2_LIVE_ENDPOINT, client.api_base)
            return InternModelPort(InternModelAdapter(
                client, model_id="intern-s2", max_tokens=1024,
                client_timeout=30, client_retry=1,
            ))

        with patch.dict(os.environ, {"INTERN_API_KEY": "test-key", "INTERN_MODEL": "intern-s2"}):
            control = {"model_port": None, "verifier_port": verifier_port(), "source": "provider_live"}
            variant = {"model_port": None, "verifier_port": verifier_port(), "source": "provider_live"}
            with self.assertRaisesRegex(ValueError, "model_port"):
                validate_conditions(
                    config,
                    {**config, "features": {"skills": True, "stream_recovery": True}},
                    conditions,
                    (control, variant),
                    "skills",
                )

    def test_offline_injected_source_rejects_ports_without_verified_loopback_adapter(self):
        from copy import deepcopy

        from showcase.solver_harness.paired_conditions import validate_conditions

        class UnverifiedPort:
            model_id = "intern-s2"

        conditions = deepcopy(CONDITIONS)
        conditions["models"]["reasoner"] = {
            "model_id": "intern-s2",
            "revision": "service-label-only",
        }
        config = {**BASE, "features": {"skills": False, "stream_recovery": True}}
        control = {"model_port": UnverifiedPort(), "source": "offline_injected"}
        variant = {"model_port": UnverifiedPort(), "source": "offline_injected"}

        with self.assertRaisesRegex(ValueError, "offline_source"):
            validate_conditions(
                config,
                {**config, "features": {"skills": True, "stream_recovery": True}},
                conditions,
                (control, variant),
                "skills",
            )

    def test_offline_injected_source_accepts_only_strict_ipv4_loopback_urls(self):
        import os
        from copy import deepcopy
        from unittest.mock import patch

        from llm_client import InternChatClient
        from showcase.adapters import InternModelAdapter
        from showcase.solver_harness.intern_port import InternModelPort
        from showcase.solver_harness.paired_conditions import validate_conditions

        conditions = deepcopy(CONDITIONS)
        conditions["models"]["reasoner"] = {
            "model_id": "intern-s2",
            "revision": "service-label-only",
        }
        config = {**BASE, "features": {"skills": False, "stream_recovery": True}}

        for api_base in (
            "http://localhost:8765/v1/chat/completions",
            "http://[::1]:8765/v1/chat/completions",
            "http://user:secret@127.0.0.1:8765/v1/chat/completions",
        ):
            with self.subTest(api_base=api_base), patch.dict(
                os.environ,
                {
                    "INTERN_API_KEY": "test-key",
                    "INTERN_MODEL": "intern-s2",
                    "INTERN_API_BASE": api_base,
                },
            ):
                def port():
                    client = InternChatClient(timeout=30, retry=1, loopback_only=True)
                    return InternModelPort(
                        InternModelAdapter(
                            client,
                            model_id="intern-s2",
                            max_tokens=1024,
                            client_timeout=30,
                            client_retry=1,
                        )
                    )

                control = {"model_port": port(), "source": "offline_injected"}
                variant = {"model_port": port(), "source": "offline_injected"}
                with self.assertRaisesRegex(ValueError, "offline_source"):
                    validate_conditions(
                        config,
                        {**config, "features": {"skills": True, "stream_recovery": True}},
                        conditions,
                        (control, variant),
                        "skills",
                    )

    def test_source_labels_reject_custom_adapters_wrapping_pinned_clients(self):
        import os
        from copy import deepcopy
        from unittest.mock import patch

        from llm_client import InternChatClient
        from showcase.adapters import InternModelAdapter
        from showcase.solver_harness.intern_port import InternModelPort
        from showcase.solver_harness.paired_conditions import validate_conditions

        class CustomAdapter(InternModelAdapter):
            def complete(self, *args, **kwargs):
                raise AssertionError("validation must not call an adapter")

        config = {**BASE, "features": {"skills": False, "stream_recovery": True}}
        for source, api_base, transport_flag in (
            (
                "offline_injected",
                "http://127.0.0.1:8765/v1/chat/completions",
                {"loopback_only": True},
            ),
            (
                "provider_live",
                "https://chat.intern-ai.org.cn/api/v1/chat/completions",
                {"provider_endpoint_only": True},
            ),
        ):
            with self.subTest(source=source), patch.dict(
                os.environ,
                {
                    "INTERN_API_KEY": "test-key",
                    "INTERN_MODEL": "intern-s2",
                    "INTERN_API_BASE": api_base,
                },
            ):
                conditions = deepcopy(CONDITIONS)
                conditions["models"]["reasoner"] = {
                    "model_id": "intern-s2",
                    "revision": "service-label-only",
                }

                def port():
                    client = InternChatClient(timeout=30, retry=1, **transport_flag)
                    return InternModelPort(
                        CustomAdapter(
                            client,
                            model_id="intern-s2",
                            max_tokens=1024,
                            client_timeout=30,
                            client_retry=1,
                        )
                    )

                control = {"model_port": port(), "source": source}
                variant = {"model_port": port(), "source": source}
                with self.assertRaisesRegex(ValueError, "transport"):
                    validate_conditions(
                        config,
                        {**config, "features": {"skills": True, "stream_recovery": True}},
                        conditions,
                        (control, variant),
                        "skills",
                    )

    def test_source_labels_reject_ports_that_override_dispatch(self):
        import os
        from copy import deepcopy
        from unittest.mock import patch

        from llm_client import InternChatClient
        from showcase.adapters import InternModelAdapter
        from showcase.solver_harness.intern_port import InternModelPort
        from showcase.solver_harness.paired_conditions import validate_conditions

        class SpoofPort(InternModelPort):
            def complete(self, _request):
                return {"assessment": "SOLVED", "solution_candidate": "scripted"}

        config = {**BASE, "features": {"skills": False, "stream_recovery": True}}
        for source, api_base, transport_flag, error in (
            (
                "offline_injected",
                "http://127.0.0.1:8765/v1/chat/completions",
                {"loopback_only": True},
                "offline_source",
            ),
            (
                "provider_live",
                "https://chat.intern-ai.org.cn/api/v1/chat/completions",
                {"provider_endpoint_only": True},
                "pinned_transport",
            ),
        ):
            with self.subTest(source=source), patch.dict(
                os.environ,
                {
                    "INTERN_API_KEY": "test-key",
                    "INTERN_MODEL": "intern-s2",
                    "INTERN_API_BASE": api_base,
                },
            ):
                conditions = deepcopy(CONDITIONS)
                conditions["models"]["reasoner"] = {
                    "model_id": "intern-s2",
                    "revision": "service-label-only",
                }

                def port():
                    client = InternChatClient(timeout=30, retry=1, **transport_flag)
                    adapter = InternModelAdapter(
                        client,
                        model_id="intern-s2",
                        max_tokens=1024,
                        client_timeout=30,
                        client_retry=1,
                    )
                    return SpoofPort(adapter)

                arms = (
                    {"model_port": port(), "source": source},
                    {"model_port": port(), "source": source},
                )
                with self.assertRaisesRegex(ValueError, error):
                    validate_conditions(
                        config,
                        {**config, "features": {"skills": True, "stream_recovery": True}},
                        conditions,
                        arms,
                        "skills",
                    )

    def test_source_labels_reject_overridden_adapter_dispatch_methods(self):
        import os
        from copy import deepcopy
        from unittest.mock import patch

        from llm_client import InternChatClient
        from showcase.adapters import InternModelAdapter, InternStreamAdapter
        from showcase.solver_harness.intern_port import InternModelPort
        from showcase.solver_harness.paired_conditions import validate_conditions

        config = {**BASE, "features": {"skills": False, "stream_recovery": True}}
        for source, api_base, transport_flag, expected_error in (
            (
                "offline_injected",
                "http://127.0.0.1:8765/v1/chat/completions",
                {"loopback_only": True},
                "offline_source",
            ),
            (
                "provider_live",
                "https://chat.intern-ai.org.cn/api/v1/chat/completions",
                {"provider_endpoint_only": True},
                "pinned_transport",
            ),
        ):
            for adapter_type, override_layer, method in (
                (InternModelAdapter, "port", "_complete_stream"),
                (InternModelAdapter, "adapter", "complete"),
                (InternStreamAdapter, "adapter", "stream_complete"),
                (InternModelAdapter, "adapter", "_get_client"),
                (InternModelAdapter, "client", "chat_response"),
            ):
                with self.subTest(
                    source=source, adapter=adapter_type.__name__, method=method
                ), patch.dict(
                    os.environ,
                    {
                        "INTERN_API_KEY": "test-key",
                        "INTERN_MODEL": "intern-s2",
                        "INTERN_API_BASE": api_base,
                    },
                ):
                    conditions = deepcopy(CONDITIONS)
                    conditions["models"]["reasoner"] = {
                        "model_id": "intern-s2",
                        "revision": "service-label-only",
                    }

                    def port():
                        client = InternChatClient(timeout=30, retry=1, **transport_flag)
                        adapter = adapter_type(
                            client,
                            model_id="intern-s2",
                            max_tokens=1024,
                            client_timeout=30,
                            client_retry=1,
                        )
                        result = InternModelPort(adapter)
                        target = {
                            "port": result,
                            "adapter": adapter,
                            "client": client,
                        }[override_layer]
                        setattr(target, method, lambda *_args, **_kwargs: None)
                        return result

                    arms = (
                        {"model_port": port(), "source": source},
                        {"model_port": port(), "source": source},
                    )
                    with self.assertRaisesRegex(ValueError, expected_error):
                        validate_conditions(
                            config,
                            {**config, "features": {"skills": True, "stream_recovery": True}},
                            conditions,
                            arms,
                            "skills",
                        )

    def test_common_budget_permission_and_observable_model_mismatch_reject_before_dispatch(self):
        from copy import deepcopy

        from showcase.solver_harness.paired import PairedRunner

        class IdentifiedPort(ScriptedModelPort):
            model_id = "actual-model"

        for change in ("budget", "permission", "model"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                control, variant = ports(), ports()
                config = {**BASE, "features": {"skills": True}}
                conditions = deepcopy(CONDITIONS)
                if change == "budget":
                    config["max_model_calls"] = 3
                elif change == "permission":
                    config["allowed_tools"] = ["python_math"]
                else:
                    variant["model_port"] = IdentifiedPort([])
                with PairedRunner(database_path=Path(directory) / "pair.db") as runner:
                    with self.assertRaises(ValueError):
                        runner.run_pair(
                            "2+2",
                            control_config=BASE,
                            variant_config=config,
                            conditions=conditions,
                            control_ports=control,
                            variant_ports=variant,
                        )
                self.assertEqual([], control["model_port"].requests)
                self.assertEqual([], variant["model_port"].requests)

    def test_failed_arm_does_not_erase_other_arm_and_errors_are_sanitized(self):
        from showcase.solver_harness.paired import PairedRunner

        class FailedPort(ScriptedModelPort):
            def complete(self, request):
                raise RuntimeError("Authorization=do-not-retain")

        control, variant = ports(), ports()
        control["model_port"] = FailedPort([])
        with (
            tempfile.TemporaryDirectory() as directory,
            PairedRunner(database_path=Path(directory) / "pair.db") as runner,
        ):
            report = runner.run_pair(
                "2+2",
                control_config=BASE,
                variant_config={**BASE, "features": {"skills": True}},
                conditions=CONDITIONS,
                control_ports=control,
                variant_ports=variant,
            )
        self.assertEqual("failed", report["arms"]["control"]["status"])
        self.assertEqual("RuntimeError", report["arms"]["control"]["failure"]["category"])
        self.assertEqual(
            "completed_llm_reviewed", report["arms"]["variant"]["result"]["state"]["status"]
        )
        self.assertNotIn("do-not-retain", str(report))

    def test_interrupted_pair_recovers_unknown_arm_without_dispatching_again(self):
        from showcase.solver_harness.paired import PairedRunner

        class ProcessGone(BaseException):
            pass

        class InterruptedPort(ScriptedModelPort):
            def complete(self, request):
                raise ProcessGone()

        control, variant = ports(), ports()
        control["model_port"] = InterruptedPort([])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pair.db"
            with PairedRunner(database_path=path) as runner:
                with self.assertRaises(ProcessGone):
                    runner.run_pair(
                        "2+2",
                        pair_id="lost",
                        control_config=BASE,
                        variant_config={**BASE, "features": {"skills": True}},
                        conditions=CONDITIONS,
                        control_ports=control,
                        variant_ports=variant,
                    )
            with PairedRunner(database_path=path) as recovered:
                report = recovered.get_report("lost")
        self.assertEqual("incomplete", report["status"])
        self.assertEqual("unknown_outcome", report["arms"]["control"]["status"])
        self.assertEqual("EXPLORE", report["arms"]["control"]["result"]["state"]["phase"])
        self.assertEqual("not_dispatched", report["arms"]["variant"]["status"])
        self.assertEqual([], variant["model_port"].requests)

    def test_shared_ports_rejected_and_solver_returned_failure_is_retained(self):
        from showcase.solver_harness.paired import PairedRunner

        class FailedVerifier(ScriptedVerifierPort):
            def verify(self, request):
                raise RuntimeError("private")

        with (
            tempfile.TemporaryDirectory() as directory,
            PairedRunner(database_path=Path(directory) / "pair.db") as runner,
        ):
            control, variant = ports(), ports()
            variant["model_port"] = control["model_port"]
            with self.assertRaisesRegex(ValueError, "independent"):
                runner.run_pair(
                    "2+2",
                    control_config=BASE,
                    variant_config={**BASE, "features": {"skills": True}},
                    conditions=CONDITIONS,
                    control_ports=control,
                    variant_ports=variant,
                )
            control, variant = ports(), ports()
            control["verifier_port"] = FailedVerifier([])
            report = runner.run_pair(
                "2+2",
                control_config=BASE,
                variant_config={**BASE, "features": {"skills": True}},
                conditions=CONDITIONS,
                control_ports=control,
                variant_ports=variant,
            )
        arm = report["arms"]["control"]
        self.assertEqual("failed", arm["status"])
        self.assertEqual("failed_runtime", arm["failure"]["category"])
        self.assertEqual("failed_runtime", arm["result"]["state"]["status"])

    def test_adapter_attempts_unknown_usage_and_declared_identity_are_checked(self):
        import json
        import os
        from copy import deepcopy
        from unittest.mock import patch

        from llm_client import InternChatClient
        from showcase.adapters import InternModelAdapter
        from showcase.solver_harness.intern_port import InternModelPort
        from showcase.solver_harness.paired import PairedRunner

        class Response:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "id": "test-attempt",
                    "model": "intern-s2",
                    "choices": [{"finish_reason": "length", "message": {"content": "{truncated"}}],
                }

        class LoopbackSession:
            trust_env = True

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def post(self, _url, **_kwargs):
                return Response()

        conditions = deepcopy(CONDITIONS)
        conditions["models"] = {
            "reasoner": {"model_id": "intern-s2", "revision": "service-label-only"}
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ,
                {
                    "INTERN_API_KEY": "fake-key",
                    "INTERN_MODEL": "intern-s2",
                    "INTERN_API_BASE": "http://127.0.0.1:8765",
                },
            ),
            patch("showcase.request_transport.requests.Session", LoopbackSession),
        ):

            def transport():
                client = InternChatClient(timeout=30, retry=1, loopback_only=True)
                return {
                    "model_port": InternModelPort(
                        InternModelAdapter(
                            client,
                            model_id="intern-s2",
                            max_tokens=1024,
                            client_timeout=30,
                            client_retry=1,
                        )
                    ),
                    "source": "offline_injected",
                }

            config = {**BASE, "features": {"skills": False, "stream_recovery": True}}
            with PairedRunner(database_path=Path(directory) / "pair.db") as runner:
                report = runner.run_pair(
                    "2+2",
                    control_config=config,
                    variant_config={
                        **config,
                        "features": {"skills": True, "stream_recovery": True},
                    },
                    conditions=conditions,
                    control_ports=transport(),
                    variant_ports=transport(),
                )
        for arm in report["arms"].values():
            # ALIGN-04: a finish_reason=length reply is a known protocol
            # failure (the provider definitively stopped), so the run ends
            # partial_aborted instead of an interrupted unknown outcome.
            self.assertEqual("failed", arm["status"])
            self.assertEqual(1, arm["physical_attempt_count"])
            self.assertEqual("length", arm["provider_attempts"][0]["finish_reason"])
            self.assertEqual("truncated_response", arm["invocations"][0]["error_category"])
            self.assertEqual(1, arm["transport_budget"]["http_attempts"])
            self.assertIsNone(arm["usage"]["total_tokens"])
            self.assertIsNone(arm["cost"])
            self.assertTrue(arm["unknown_calls"])
        self.assertNotIn("{truncated", json.dumps(report))

    def test_same_pair_id_cannot_be_rebound_to_different_problem(self):
        from showcase.solver_harness.paired import PairedRunner

        with (
            tempfile.TemporaryDirectory() as directory,
            PairedRunner(database_path=Path(directory) / "pair.db") as runner,
        ):
            common = {
                "pair_id": "fixed",
                "control_config": BASE,
                "variant_config": {**BASE, "features": {"skills": True}},
                "conditions": CONDITIONS,
                "control_ports": ports(),
                "variant_ports": ports(),
            }
            report = runner.run_pair("2+2", **common)
            self.assertEqual(report, runner.run_pair("2+2", **common))
            with self.assertRaisesRegex(ValueError, "identity_conflict"):
                runner.run_pair("3+3", **common)
