"""Small fixture checks for correlation/target safety; not native runtime proof."""
import json
import unittest

from fixture import child_response, decision, parent_response, returned_child_ids, validate_decision


class DecisionFixtureTests(unittest.TestCase):
    def test_only_actual_returned_ids_are_targets(self):
        text = "Started jobs\n- `7-decision_1` (job `7-decision_1`) — Decision req_1\n- `9-decision_2` (job `9-decision_2`) — Decision req_2"
        self.assertEqual(returned_child_ids(text), ["7-decision_1", "9-decision_2"])
        self.assertEqual(returned_child_ids("Try the guessed id 0-decision_1"), [])

    def test_wrong_request_or_checkpoint_does_not_consume_answer(self):
        for change in [{"request_id": "req_2"}, {"checkpoint": "different"}, {"selected_answer": "unknown"}]:
            payload = {"request_id": "req_1", "checkpoint": "checkpoint-req_1", "selected_answer": "Continue with A", **change}
            body = {"messages": [{"role": "user", "content": "[DECISION_RESUME] " + json.dumps(payload)}]}
            actions, _ = child_response(body, "req_1", False, lambda _: None)
            self.assertEqual(actions[0][1]["result"]["data"]["status"], "correlation_error")
            self.assertIs(actions[0][1]["result"]["data"]["answer_consumed"], False)

    def test_valid_resume_consumes_the_matching_answer(self):
        body = {"messages": [{"role": "user", "content": '[DECISION_RESUME] {"request_id":"req_1","checkpoint":"checkpoint-req_1","selected_answer":"Continue with B"}'}]}
        records = []
        actions, _ = child_response(body, "req_1", False, records.append)
        self.assertIs(actions[0][1]["result"]["data"]["answer_consumed"], True)
        self.assertNotIn("Continue with B", json.dumps(records))

    def test_payload_validation_does_not_accept_partial_or_other_requests(self):
        self.assertTrue(validate_decision(decision("req_1"), "req_1"))
        self.assertFalse(validate_decision(decision("req_2"), "req_1"))
        self.assertFalse(validate_decision({"status": "needs_user_decision", "request_id": "req_1"}, "req_1"))

    def test_two_child_requests_have_distinct_persistent_ids(self):
        actions, _ = parent_response({"messages": []}, "two", lambda _: None)
        assignments = [task["assignment"] for task in actions[0][1]["tasks"]]
        self.assertEqual(assignments, ["[DECISION_CHILD:req_1]", "[DECISION_CHILD:req_2]"])


if __name__ == "__main__":
    unittest.main()
