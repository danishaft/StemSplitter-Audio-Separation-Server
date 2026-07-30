from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from contract_ledger import (
    ContractLedger,
    DispatchIntent,
    run_with_bounded_retries,
)


class ContractLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temporary_directory.name) / "proof.sqlite3"
        self.ledger = ContractLedger(self.db_path)
        self.intent = DispatchIntent(
            job_id="job_01JTEST",
            tenant_id="tenant_alpha",
            attempt_number=1,
            priority="high",
            max_tenant_concurrency=2,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def reserve(self) -> str:
        return self.ledger.reserve_dispatch(
            self.intent,
            proposed_external_run_id="hatchet_run_primary",
        )

    def test_stable_product_and_attempt_identifiers(self) -> None:
        self.assertEqual(self.intent.attempt_id, "job_01JTEST:attempt:1")
        self.assertEqual(
            self.intent.dispatch_key,
            "stem-separation:job_01JTEST:attempt:1",
        )
        self.assertEqual(self.intent, DispatchIntent(job_id="job_01JTEST", tenant_id="tenant_alpha", attempt_number=1, priority="high", max_tenant_concurrency=2))

    def test_dispatch_is_idempotent(self) -> None:
        def reserve(index: int) -> str:
            return self.ledger.reserve_dispatch(
                self.intent,
                proposed_external_run_id=f"candidate_{index}",
            )

        with ThreadPoolExecutor(max_workers=10) as executor:
            run_ids = set(executor.map(reserve, range(100)))

        self.assertEqual(len(run_ids), 1)
        self.assertEqual(self.ledger.count("dispatches"), 1)
        self.assertEqual(self.ledger.count("attempts"), 1)

    def test_priority_and_concurrency_metadata_are_explicit(self) -> None:
        metadata = self.intent.metadata()
        self.assertEqual(metadata["priority"], "high")
        self.assertEqual(metadata["concurrency_key"], "tenant:tenant_alpha")
        self.assertEqual(metadata["max_tenant_concurrency"], 2)
        self.assertEqual(metadata["attempt_id"], self.intent.attempt_id)

    def test_bounded_retry_recovers_without_duplicate_effects(self) -> None:
        self.reserve()

        def fail_twice(retry_count: int) -> None:
            if retry_count < 2:
                raise RuntimeError("injected_worker_failure")

        final_retry = run_with_bounded_retries(
            self.ledger,
            self.intent,
            fail_twice,
            retries=2,
        )

        self.assertEqual(final_retry, 2)
        self.assertEqual(self.ledger.count("executions"), 3)
        self.assertEqual(self.ledger.count("terminal_effects"), 1)
        self.assertEqual(self.ledger.count("usage_effects"), 1)
        self.assertEqual(self.ledger.count("artifacts"), 1)

    def test_retry_exhaustion_has_no_economic_effect(self) -> None:
        self.reserve()

        def always_fail(_retry_count: int) -> None:
            raise RuntimeError("injected_permanent_failure")

        final_retry = run_with_bounded_retries(
            self.ledger,
            self.intent,
            always_fail,
            retries=2,
        )

        self.assertEqual(final_retry, 2)
        self.assertEqual(self.ledger.count("executions"), 3)
        self.assertEqual(self.ledger.count("terminal_effects"), 1)
        self.assertEqual(self.ledger.count("usage_effects"), 0)
        self.assertEqual(self.ledger.count("artifacts"), 0)

    def test_callback_replay_has_one_terminal_and_economic_effect(self) -> None:
        self.reserve()

        def replay(_index: int) -> bool:
            return self.ledger.apply_callback(
                callback_id="callback_completed_1",
                intent=self.intent,
                status="completed",
                artifact_key="jobs/job_01JTEST/stems.zip",
                gpu_seconds=12.5,
                amount_microunits=750,
            )

        with ThreadPoolExecutor(max_workers=10) as executor:
            applied = list(executor.map(replay, range(100)))

        self.assertEqual(applied.count(True), 1)
        self.assertEqual(self.ledger.count("callback_events"), 1)
        self.assertEqual(self.ledger.count("terminal_effects"), 1)
        self.assertEqual(self.ledger.count("usage_effects"), 1)
        self.assertEqual(self.ledger.count("artifacts"), 1)

    def test_distinct_competing_terminal_callbacks_do_not_duplicate_effects(self) -> None:
        self.reserve()
        self.ledger.apply_callback(
            callback_id="callback_completed_first",
            intent=self.intent,
            status="completed",
            artifact_key="jobs/job_01JTEST/stems.zip",
            gpu_seconds=12.5,
            amount_microunits=750,
        )
        self.ledger.apply_callback(
            callback_id="callback_failed_late",
            intent=self.intent,
            status="failed",
        )

        self.assertEqual(self.ledger.count("callback_events"), 2)
        self.assertEqual(self.ledger.count("terminal_effects"), 1)
        self.assertEqual(self.ledger.count("usage_effects"), 1)
        self.assertEqual(
            self.ledger.value(
                "SELECT status FROM jobs WHERE job_id = ?",
                (self.intent.job_id,),
            ),
            "completed",
        )

    def test_cancellation_wins_over_late_completion(self) -> None:
        self.reserve()
        self.ledger.request_cancel(self.intent.job_id)
        self.ledger.apply_callback(
            callback_id="callback_completed_after_cancel",
            intent=self.intent,
            status="completed",
            artifact_key="jobs/job_01JTEST/stems.zip",
            gpu_seconds=12.5,
            amount_microunits=750,
        )

        self.assertEqual(
            self.ledger.value(
                "SELECT status FROM jobs WHERE job_id = ?",
                (self.intent.job_id,),
            ),
            "cancelled",
        )
        self.assertEqual(self.ledger.count("terminal_effects"), 1)
        self.assertEqual(self.ledger.count("usage_effects"), 0)
        self.assertEqual(self.ledger.count("artifacts"), 0)

    def test_fault_claim_is_process_safe_and_one_shot(self) -> None:
        claims = [
            self.ledger.claim_fault(f"{self.intent.attempt_id}:crash")
            for _ in range(10)
        ]
        self.assertEqual(claims, [True] + [False] * 9)


if __name__ == "__main__":
    unittest.main()
