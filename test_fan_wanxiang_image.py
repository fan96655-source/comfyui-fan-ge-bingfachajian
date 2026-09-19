"""Offline regression checks for the Wanxiang route adapter.

These tests never contact a real provider and never require an API key.
"""

from __future__ import annotations

import base64
import io
import itertools
import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from PIL import Image

import fan_wanxiang_image as node


class _FakeResponse:
    def __init__(self, content: bytes, status: int = 200) -> None:
        self._content = content
        self.content = content
        self.status_code = status
        self.headers: dict[str, str] = {}
        self.text = content.decode("utf-8", errors="replace")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def iter_content(self, chunk_size: int = 1):
        for value in self._content:
            yield bytes((value,))
        raise AssertionError("parser waited beyond a complete acknowledgement")


def _png_data_uri(width: int, height: int, color: tuple[int, int, int]) -> str:
    image = Image.new("RGB", (width, height), color)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


class SubmitParserTests(unittest.TestCase):
    def test_complete_json_returns_before_connection_eof(self) -> None:
        payload = json.dumps({"code": 0, "data": {"id": "json-id"}}).encode()
        with patch.object(node.requests, "request", return_value=_FakeResponse(payload)):
            result = node._post_grsai_submit("https://unit.test/submit", {}, {})
        self.assertEqual(result["data"]["id"], "json-id")

    def test_multiline_sse_returns_before_connection_eof(self) -> None:
        payload = (
            b'data: {"code":0,\n'
            b'data: "data":{"id":"sse-id"}}\n\n'
        )
        with patch.object(node.requests, "request", return_value=_FakeResponse(payload)):
            result = node._post_grsai_submit("https://unit.test/submit", {}, {})
        self.assertEqual(result["data"]["id"], "sse-id")

    def test_read_timeout_keeps_unknown_submit_semantics(self) -> None:
        with patch.object(
            node.requests,
            "request",
            side_effect=node.requests.ReadTimeout("unit timeout"),
        ):
            with self.assertRaises(node.WanXiangNetworkError) as caught:
                node._post_grsai_submit("https://unit.test/submit", {}, {})
        self.assertTrue(caught.exception.timed_out)


class GrsaiStateTests(unittest.TestCase):
    def test_submit_timeout_is_not_retried(self) -> None:
        def unknown(*_: object, **__: object):
            raise node.WanXiangNetworkError("timeout", timed_out=True)

        with patch.object(node, "_post_grsai_submit", side_effect=unknown):
            with self.assertRaises(node.WanXiangError) as caught:
                node.FanWanXiangImage._grsai(
                    "key", node.MODELS[0], [], "prompt", "1:1", "1K"
                )
        self.assertIn("没有自动重提", str(caught.exception))

    def test_poll_retries_network_and_transient_http(self) -> None:
        responses: list[object] = [
            node.WanXiangNetworkError("temporary"),
            node.WanXiangHTTPError("HTTP 503", status_code=503),
            {"code": 0, "data": {"status": "running"}},
        ]

        def fake_post(*_: object, **__: object):
            value = responses.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        with (
            patch.object(node, "_post_json", side_effect=fake_post),
            patch.object(node.time, "sleep", return_value=None),
        ):
            result = node.FanWanXiangImage._poll_grsai_task(
                {}, "poll-id", 1, node.time.monotonic() + 100
            )
        self.assertEqual(result["code"], 0)
        self.assertEqual(responses, [])

    def test_running_then_succeeded(self) -> None:
        responses = iter(
            [
                {"code": 0, "data": {"id": "task-1", "status": "running", "results": []}},
                {
                    "code": 0,
                    "data": {
                        "id": "task-1",
                        "status": "succeeded",
                        "results": [{"url": "https://img.test/1.png"}],
                    },
                },
            ]
        )
        with (
            patch.object(
                node,
                "_post_grsai_submit",
                return_value={"code": 0, "data": {"id": "task-1"}},
            ),
            patch.object(
                node.FanWanXiangImage,
                "_poll_grsai_task",
                side_effect=lambda *_: next(responses),
            ),
            patch.object(node, "GRSAI_POLL_INTERVAL", 0),
        ):
            values, task_id, _ = node.FanWanXiangImage._grsai(
                "key", node.MODELS[0], [], "prompt", "1:1", "1K"
            )
        self.assertEqual(task_id, "task-1")
        self.assertEqual(values, ["https://img.test/1.png"])

    def test_failed_status_wins_over_stray_url(self) -> None:
        response = {
            "code": 0,
            "data": {
                "id": "task-f",
                "status": "failed",
                "results": [{"url": "https://img.test/wrong.png"}],
                "error": "failed",
            },
        }
        with patch.object(node, "_post_grsai_submit", return_value=response):
            with self.assertRaises(node.WanXiangError):
                node.FanWanXiangImage._grsai(
                    "key", node.MODELS[0], [], "prompt", "1:1", "1K"
                )

    def test_succeeded_without_result_fails_clearly(self) -> None:
        response = {
            "code": 0,
            "data": {"id": "task-empty", "status": "succeeded", "results": []},
        }
        with patch.object(node, "_post_grsai_submit", return_value=response):
            with self.assertRaisesRegex(node.WanXiangError, "没有 results"):
                node.FanWanXiangImage._grsai(
                    "key", node.MODELS[0], [], "prompt", "1:1", "1K"
                )

    def test_persistent_minus_22_stops_after_grace(self) -> None:
        with (
            patch.object(
                node,
                "_post_grsai_submit",
                return_value={"code": 0, "data": {"id": "missing-id"}},
            ),
            patch.object(
                node.FanWanXiangImage,
                "_poll_grsai_task",
                return_value={"code": -22, "msg": "not found"},
            ),
            patch.object(node, "GRSAI_POLL_INTERVAL", 0),
            patch.object(node, "GRSAI_NOT_FOUND_GRACE", 0),
        ):
            with self.assertRaisesRegex(node.WanXiangError, "code=-22"):
                node.FanWanXiangImage._grsai(
                    "key", node.MODELS[0], [], "prompt", "1:1", "1K"
                )


class GrsaiAsyncGPTTests(unittest.TestCase):
    def test_145_second_generation_polls_one_task_for_each_gpt_model(self) -> None:
        for model in (
            "gpt-image-2", "gpt-image-2-vip", "gpt-image-2.5",
            "gpt-image-2.5-flare", "gpt-image-2.5-sunburst",
        ):
            with self.subTest(model=model):
                clock = [0.0]
                task_id = "16-task with space&suffix"
                result_url = "https://img.test/finished.png"
                reference = _png_data_uri(8, 8, (0, 0, 0))
                submissions = []
                queries = []

                def advance(seconds):
                    clock[0] += seconds

                def transport(method, url, **kwargs):
                    parsed = urlsplit(url)
                    if method == "POST":
                        self.assertEqual(parsed.path, "/v1/api/generate")
                        payload = json.loads(kwargs["data"])
                        submissions.append(payload)
                        # JSON mode waits for the 145-second result, exceeding
                        # the submit reader's 60-second idle timeout.
                        if payload.get("replyType") != "async":
                            raise node.requests.ReadTimeout("generation takes 145 seconds")
                        self.assertEqual(payload["images"], [reference])
                        self.assertEqual(payload["model"], model)
                        self.assertNotIn("webHook", payload)
                        self.assertNotIn("urls", payload)
                        response = {"id": task_id, "status": "running"}
                    else:
                        self.assertEqual(method, "GET")
                        self.assertEqual(parsed.path, "/v1/api/result")
                        self.assertEqual(parse_qs(parsed.query), {"id": [task_id]})
                        self.assertIsNone(kwargs.get("data"))
                        queries.append(clock[0])
                        response = {"id": task_id, "status": "running", "results": []}
                        if clock[0] >= 145:
                            response.update(status="succeeded", results=[{"url": result_url}])
                    self.assertEqual(
                        {key.lower(): value for key, value in kwargs["headers"].items()}["authorization"],
                        "Bearer offline-key",
                    )
                    self.assertTrue(kwargs["verify"])
                    return _FakeResponse(json.dumps(response).encode())

                with (
                    patch.object(node.requests, "request", side_effect=transport),
                    patch.object(node.time, "monotonic", side_effect=lambda: clock[0]),
                    patch.object(node.time, "sleep", side_effect=advance),
                ):
                    values, returned_id, _ = node.FanWanXiangImage._grsai(
                        "offline-key", model, [], "prompt", "1:1", "1K", [reference]
                    )
                self.assertEqual(values, [result_url])
                self.assertEqual(returned_id, task_id)
                self.assertEqual(len(submissions), 1)
                self.assertGreater(len(queries), 1)
                self.assertEqual(clock[0], 145)

    def test_gpt_terminal_responses_stop_without_resubmitting(self) -> None:
        for terminal, expected in (
            ({"status": "failed", "error": "generation failed"}, "generation failed"),
            ({"status": "violation", "error": "input rejected"}, "input rejected"),
            ({"status": "succeeded", "results": []}, "没有 results"),
        ):
            for immediate in (True, False):
                with self.subTest(status=terminal["status"], immediate=immediate):
                    response = {"id": "terminal-task", **terminal}
                    if terminal["status"] != "succeeded":
                        response["results"] = [{"url": "https://img.test/stray.png"}]
                    with (
                        patch.object(node, "_post_grsai_submit", return_value=(
                            response if immediate else {"id": "terminal-task", "status": "running"}
                        )) as submit,
                        patch.object(node, "_get_json", return_value=response) as query,
                        patch.object(node, "GRSAI_POLL_INTERVAL", 0),
                    ):
                        with self.assertRaisesRegex(node.WanXiangError, expected) as caught:
                            node.FanWanXiangImage._grsai(
                                "key", "gpt-image-2.5-sunburst", [], "prompt", "1:1", "1K"
                            )
                    self.assertIn("terminal-task", str(caught.exception))
                    submit.assert_called_once()
                    self.assertEqual(query.call_count, 0 if immediate else 1)

    def test_gpt_query_retries_only_transient_failures(self) -> None:
        success = {"id": "retry-task", "status": "succeeded", "results": [{"url": "https://img.test/x.png"}]}
        for errors, expected_calls in (
            ([node.WanXiangNetworkError("network"), node.WanXiangHTTPError("busy", status_code=503), success], 3),
            ([node.WanXiangHTTPError("unauthorized", status_code=401)], 1),
        ):
            with (
                self.subTest(expected_calls=expected_calls),
                patch.object(node, "_post_grsai_submit", return_value={"id": "retry-task", "status": "running"}) as submit,
                patch.object(node, "_get_json", side_effect=errors) as query,
                patch.object(node.time, "sleep", return_value=None),
            ):
                if expected_calls == 1:
                    with self.assertRaises(node.WanXiangHTTPError):
                        node.FanWanXiangImage._grsai("key", "gpt-image-2.5", [], "prompt", "1:1", "1K")
                else:
                    values, _, _ = node.FanWanXiangImage._grsai("key", "gpt-image-2.5", [], "prompt", "1:1", "1K")
                    self.assertEqual(values, ["https://img.test/x.png"])
            submit.assert_called_once()
            self.assertEqual(query.call_count, expected_calls)

    def test_gpt_submit_timeout_never_resubmits(self) -> None:
        with (
            patch.object(node.requests, "request", side_effect=node.requests.ReadTimeout("timeout")) as request,
            patch.object(node, "_get_json") as query,
        ):
            with self.assertRaisesRegex(node.WanXiangError, "没有自动重提"):
                node.FanWanXiangImage._grsai("key", "gpt-image-2.5", [], "prompt", "1:1", "1K")
        request.assert_called_once()
        query.assert_not_called()

    def test_three_gpt_outputs_use_three_distinct_tasks(self) -> None:
        sequence = itertools.count(1)
        queried_ids = []

        def submit(url, payload, headers):
            self.assertEqual(payload["replyType"], "async")
            return {"id": f"task-{next(sequence)}", "status": "running"}

        def query(url, headers, **kwargs):
            task_id = parse_qs(urlsplit(url).query)["id"][0]
            queried_ids.append(task_id)
            return {"id": task_id, "status": "succeeded", "results": [{"url": f"https://img.test/{task_id}.png"}]}

        with (
            patch.object(node, "_post_grsai_submit", side_effect=submit) as submission,
            patch.object(node, "_get_json", side_effect=query),
            patch.object(node, "GRSAI_POLL_INTERVAL", 0),
        ):
            values, first_id, remote = node.FanWanXiangImage._grsai_parallel(
                "key", "gpt-image-2.5-sunburst", [], "prompt", "1:1", "1K", 3
            )
        self.assertEqual(submission.call_count, 3)
        self.assertEqual(len(values), 3)
        self.assertEqual(set(queried_ids), {"task-1", "task-2", "task-3"})
        self.assertIn(first_id, queried_ids)
        self.assertEqual(remote["parallel"]["succeeded"], 3)

    def test_gemini_still_uses_legacy_submit_and_post_query(self) -> None:
        for model, remote_model in (
            ("gemini-3.1-flash-image-preview", "nano-banana-2"),
            ("gemini-3-pro-image-preview", "nano-banana-pro"),
        ):
            with (
                self.subTest(model=model),
                patch.object(node, "_post_grsai_submit", return_value={"code": 0, "data": {"id": "legacy"}}) as submit,
                patch.object(node, "_post_json", return_value={"code": 0, "data": {
                    "id": "legacy", "status": "succeeded", "results": [{"url": "https://img.test/legacy.png"}]
                }}) as poll,
                patch.object(node, "_get_json") as gpt_query,
                patch.object(node, "GRSAI_POLL_INTERVAL", 0),
            ):
                node.FanWanXiangImage._grsai("key", model, [], "prompt", "2:3", "2K")
            self.assertEqual(submit.call_args.args[0], node.GRSAI_BASE_URL + "/v1/draw/nano-banana")
            self.assertEqual(submit.call_args.args[1], {
                "model": remote_model, "prompt": "prompt", "urls": [], "webHook": "-1", "aspectRatio": "2:3", "imageSize": "2K"
            })
            self.assertEqual(poll.call_args.args[:2], (node.GRSAI_BASE_URL + "/v1/draw/result", {"id": "legacy"}))
            gpt_query.assert_not_called()


class ParallelAndOutputTests(unittest.TestCase):
    def test_reference_adaptation_parallelism_is_independent_of_output_count(self) -> None:
        normal = [SimpleNamespace(shape=(2300, 2300, 3)) for _ in range(4)]
        huge = [SimpleNamespace(shape=(5000, 5000, 3)) for _ in range(2)]
        self.assertEqual(node._reference_worker_count(normal), 3)
        self.assertEqual(node._reference_worker_count(huge), 1)
        self.assertEqual(
            node._ordered_parallel_map(
                [3, 1, 2], lambda item: item * 2, enabled=True, max_workers=2
            ),
            [6, 2, 4],
        )

    def test_two_four_and_twelve_jobs_are_bounded(self) -> None:
        for requested in (2, 4, 12):
            lock = threading.Lock()
            counter = itertools.count()
            state = {"active": 0, "maximum": 0}

            def fake_grsai(*_: object, **__: object):
                index = next(counter)
                with lock:
                    state["active"] += 1
                    state["maximum"] = max(state["maximum"], state["active"])
                time.sleep(0.004 * (3 - index % 3))
                with lock:
                    state["active"] -= 1
                return [f"value-{index}"], f"id-{index}", {"index": index}

            with patch.object(node.FanWanXiangImage, "_grsai", side_effect=fake_grsai):
                values, first_id, remote = node.FanWanXiangImage._grsai_parallel(
                    "key",
                    node.MODELS[0],
                    [b"x" * 1024],
                    "prompt",
                    "1:1",
                    "1K",
                    requested,
                )
            self.assertEqual(len(values), requested)
            self.assertLessEqual(state["maximum"], 3)
            self.assertLessEqual(remote["parallel"]["active_workers"], 3)
            self.assertEqual(first_id, "id-0")

    def test_partial_decode_keeps_success(self) -> None:
        value = _png_data_uri(8, 8, (255, 0, 0))
        output, kept, failures = node._to_tensor(
            [value, "!!!invalid!!!"], parallel=True
        )
        self.assertEqual(tuple(output.shape), (1, 8, 8, 3))
        self.assertEqual(kept, [value])
        self.assertEqual(len(failures), 1)

    def test_mixed_dimensions_are_not_silently_dropped(self) -> None:
        with self.assertRaisesRegex(node.WanXiangError, "未静默丢图"):
            node._to_tensor(
                [
                    _png_data_uri(8, 8, (0, 0, 0)),
                    _png_data_uri(9, 8, (0, 0, 0)),
                ],
                parallel=True,
            )

    def test_ui_range_and_default(self) -> None:
        schema = node.FanWanXiangImage.INPUT_TYPES()["required"]["num_images"]
        self.assertEqual(schema[0][0], "1")
        self.assertEqual(schema[0][-1], "12")
        self.assertEqual(schema[1]["default"], "1")


if __name__ == "__main__":
    unittest.main()
