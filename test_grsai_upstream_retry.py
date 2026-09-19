"""Offline checks for confirmed Grsai GPT upstream task failures."""

import itertools
import unittest
from unittest.mock import patch

import fan_wanxiang_image as node


RATE_LIMIT = "Upstream rate limit exceeded. Please retry later."
UNAVAILABLE = "Upstream service is temporarily unavailable. Please retry later."
MODEL = "gpt-image-2.5-sunburst"
SUCCESS = {"id": "success-id", "status": "succeeded", "results": [{"url": "https://img.test/ok.png"}]}


def failed(task_id, message=RATE_LIMIT, **extra):
    return {"id": task_id, "status": "failed", "error": message, **extra}


class UpstreamRetryTests(unittest.TestCase):
    def test_both_upstream_failures_recover_after_backoff(self):
        for immediate in (True, False):
            with self.subTest(immediate=immediate):
                failures = [failed("rate-id"), failed("unavailable-id", UNAVAILABLE)]
                responses = failures + [SUCCESS]
                submissions = responses if immediate else [{"id": item["id"], "status": "running"} for item in responses]
                with (
                    patch.object(node, "_post_grsai_submit", side_effect=submissions) as submit,
                    patch.object(node, "_get_json", side_effect=responses) as poll,
                    patch.object(node.time, "sleep") as sleep,
                    patch.object(node.secrets, "randbelow", return_value=0),
                ):
                    values, task_id, remote = node.FanWanXiangImage._grsai(
                        "key", MODEL, [], "prompt", "1:1", "1K", ["data:image/png;base64,eA=="]
                    )
                self.assertEqual(values, ["https://img.test/ok.png"])
                self.assertEqual(task_id, "success-id")
                self.assertEqual(submit.call_count, 3)
                self.assertEqual(poll.call_count, 0 if immediate else 3)
                delays = [call.args[0] for call in sleep.call_args_list if call.args[0] >= 30]
                self.assertEqual(delays, [30, 60])
                payloads = [call.args[1] for call in submit.call_args_list]
                self.assertTrue(all(payload == payloads[0] for payload in payloads))
                history = remote["generation_retry"]
                self.assertEqual(history["attempts"], 3)
                self.assertEqual([item["task_id"] for item in history["failed_tasks"]], ["rate-id", "unavailable-id"])

    def test_persistent_failures_stop_after_three_attempts(self):
        with (
            patch.object(node, "_post_grsai_submit", side_effect=[failed(f"failure-{i}", UNAVAILABLE) for i in range(3)]) as submit,
            patch.object(node.time, "sleep") as sleep,
        ):
            with self.assertRaises(node.WanXiangError) as caught:
                node.FanWanXiangImage._grsai("key", MODEL, [], "prompt", "1:1", "1K")
        self.assertEqual(submit.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertIn("上游", str(caught.exception))
        for index in range(3):
            self.assertIn(f"failure-{index}", str(caught.exception))

    def test_nonretryable_or_unconfirmed_results_are_not_resubmitted(self):
        cases = [
            failed("bad-params", "Invalid input parameters"),
            failed("quota", "Insufficient balance. Please retry later."),
            failed("policy", RATE_LIMIT, status="violation"),
            failed("moderation", RATE_LIMIT, failure_reason="input_moderation"),
            failed("unknown-status", RATE_LIMIT, status="error"),
            failed("", RATE_LIMIT),
            {"id": "empty", "status": "succeeded", "results": []},
            node.WanXiangNetworkError("timeout", timed_out=True),
            node.WanXiangHTTPError(RATE_LIMIT, status_code=429),
        ]
        for response in cases:
            with (
                self.subTest(response=response),
                patch.object(node, "_post_grsai_submit", side_effect=[response]) as submit,
                patch.object(node.time, "sleep") as sleep,
            ):
                with self.assertRaises(node.WanXiangError):
                    node.FanWanXiangImage._grsai("key", MODEL, [], "prompt", "1:1", "1K")
            submit.assert_called_once()
            sleep.assert_not_called()

    def test_later_submit_timeout_stops_and_keeps_failed_task_id(self):
        with (
            patch.object(node, "_post_grsai_submit", side_effect=[failed("known-failure"), node.WanXiangNetworkError("timeout", timed_out=True)]) as submit,
            patch.object(node.time, "sleep"),
        ):
            with self.assertRaises(node.WanXiangError) as caught:
                node.FanWanXiangImage._grsai("key", MODEL, [], "prompt", "1:1", "1K")
        self.assertEqual(submit.call_count, 2)
        self.assertIn("known-failure", str(caught.exception))
        self.assertIn("没有自动重提", str(caught.exception))

    def test_poll_exhaustion_does_not_create_a_new_task(self):
        with (
            patch.object(node, "_post_grsai_submit", return_value={"id": "still-running", "status": "running"}) as submit,
            patch.object(node, "_get_json", side_effect=node.WanXiangNetworkError("network")) as poll,
            patch.object(node.time, "sleep"),
        ):
            with self.assertRaises(node.WanXiangError) as caught:
                node.FanWanXiangImage._grsai("key", MODEL, [], "prompt", "1:1", "1K")
        submit.assert_called_once()
        self.assertEqual(poll.call_count, node.GRSAI_POLL_RETRIES)
        self.assertIn("still-running", str(caught.exception))

    def test_gemini_keeps_existing_failure_behavior(self):
        with (
            patch.object(node, "_post_grsai_submit", return_value=failed("gemini-failure")) as submit,
            patch.object(node.time, "sleep") as sleep,
        ):
            with self.assertRaises(node.WanXiangError):
                node.FanWanXiangImage._grsai("key", node.MODELS[0], [], "prompt", "1:1", "1K")
        submit.assert_called_once()
        sleep.assert_not_called()

    def test_running_task_deadline_does_not_resubmit(self):
        with (
            patch.object(node, "_post_grsai_submit", return_value={"id": "running-id", "status": "running"}) as submit,
            patch.object(node, "GRSAI_TASK_TIMEOUT", 0),
            patch.object(node.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(node.WanXiangError, "running-id.*超时"):
                node.FanWanXiangImage._grsai("key", MODEL, [], "prompt", "1:1", "1K")
        submit.assert_called_once()
        sleep.assert_not_called()

    def test_retry_exhaustion_keeps_other_successful_outputs(self):
        with (
            patch.object(node, "_post_grsai_submit", side_effect=[
                {**SUCCESS, "id": "first-ok"},
                failed("bad-1"), failed("bad-2"), failed("bad-3"),
                {**SUCCESS, "id": "last-ok"},
            ]) as submit,
            patch.object(node.time, "sleep"),
        ):
            values, first_id, remote = node.FanWanXiangImage._grsai_parallel("key", MODEL, [], "prompt", "1:1", "1K", 3)
        self.assertEqual(submit.call_count, 5)
        self.assertEqual(len(values), 2)
        self.assertEqual(first_id, "first-ok")
        self.assertEqual(remote["parallel"]["succeeded"], 2)
        self.assertEqual(remote["parallel"]["failed"], 1)
        for task_id in ("bad-1", "bad-2", "bad-3"):
            self.assertIn(task_id, remote["parallel"]["errors"][0]["message"])

    def test_three_outputs_retry_each_failure_without_repeating_success(self):
        sequence = itertools.count()
        attempted_ids = []

        def submit(*args):
            index = next(sequence)
            task_id = f"batch-{index}"
            attempted_ids.append(task_id)
            if index % 2 == 0:
                return failed(task_id, RATE_LIMIT if index == 0 else UNAVAILABLE)
            return {**SUCCESS, "id": task_id, "results": [{"url": f"https://img.test/{index}.png"}]}

        with (
            patch.object(node, "_post_grsai_submit", side_effect=submit),
            patch.object(node.time, "sleep"),
        ):
            values, _, remote = node.FanWanXiangImage._grsai_parallel("key", MODEL, [], "prompt", "1:1", "1K", 3)
        self.assertEqual(len(attempted_ids), 6)
        self.assertEqual(len(set(values)), 3)
        self.assertEqual(remote["parallel"]["succeeded"], 3)
        self.assertEqual(remote["parallel"]["active_workers"], 1)
        self.assertTrue(all(task["response"]["generation_retry"]["attempts"] == 2 for task in remote["tasks"]))


if __name__ == "__main__":
    unittest.main()
