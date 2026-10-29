"""Offline measurement contracts; no server/provider calls."""
import unittest

import httpx

from evals.measure_evals import ObservedClient, p95, summarise


class MeasurementTests(unittest.TestCase):
    def client(self, body):
        return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)))

    def test_missing_or_unknown_usage_is_not_zero_cost(self):
        for body in [{"reply": "hello"}, {"usage": {"cost_usd": None, "confirmed_cost_usd": .001, "unknown_reserved_usd": .002}}]:
            with self.client(body) as raw:
                client = ObservedClient(raw)
                response = client.post("http://app/api/chat", json={})
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(client.turns[0]["cost_usd"])
                report = summarise([{"wall_seconds": 1., "passed": False, "cost_usd": None, "turns": client.turns}])
                self.assertIsNone(report["average_cost_per_attempted_case_usd"])
                self.assertFalse(report["usage_complete"])

    def test_zero_reported_usage_is_known_zero_and_no_reply_is_retained(self):
        with self.client({"reply": "private test content", "usage": {"cost_usd": 0, "unknown_reserved_usd": 0}}) as raw:
            client = ObservedClient(raw)
            client.post("http://app/api/approve", json={})
            turn = client.turns[0]
            self.assertEqual(turn["cost_usd"], 0)
            self.assertNotIn("private test content", str(turn))
            report = summarise([{"wall_seconds": 3., "passed": True, "cost_usd": 0, "turns": client.turns}])
            self.assertEqual(report["average_cost_per_attempted_case_usd"], 0)
            self.assertEqual(report["case_wall_p95_seconds"], 3.)

    def test_case_time_and_turn_time_have_separate_denominators(self):
        turn = {"wall_seconds": 1., "cost_usd": .002, "usage_missing": False, "usage_unknown": False, "usage": {}}
        report = summarise([{"wall_seconds": 3., "passed": True, "cost_usd": .004, "turns": [turn, turn]},
                            {"wall_seconds": 4., "passed": False, "cost_usd": .002, "turns": [turn]}])
        self.assertEqual(report["success_rate"], .5)
        self.assertEqual(report["case_wall_avg_seconds"], 3.5)
        self.assertEqual(report["turn_wall_avg_seconds"], 1.)
        self.assertAlmostEqual(report["average_cost_per_attempted_case_usd"], .003)
        self.assertEqual(p95([1, 2, 3]), 3)


if __name__ == "__main__":
    unittest.main()
