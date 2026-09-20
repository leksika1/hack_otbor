import json
import unittest
from agent_log_parser import AgentLogParser


class AgentLogParserTest(unittest.TestCase):
    def test_broken_and_unknown_logs_do_not_raise(self):
        p = AgentLogParser(idle_seconds=5)
        self.assertEqual(len(p.parse_lines(['{"type":"mystery","timestamp":"not-time"}', '{"type":'])), 2)
        self.assertTrue(p.analyze().parse_warnings)

    def test_local_metrics_and_chunking(self):
        rows = [
            {"type":"tool", "timestamp":"2026-01-01T00:00:00Z", "tool_name":"read", "arguments":{"path":"a.py"}, "status":"error"},
            {"type":"tool", "timestamp":"2026-01-01T00:00:10Z", "tool_name":"read", "arguments":{"path":"a.py"}, "status":"error"},
            {"type":"user", "timestamp":"2026-01-01T00:01:20Z", "content":"stop"},
        ]
        p = AgentLogParser(idle_seconds=30); p.parse_lines(map(json.dumps, rows)); m = p.analyze()
        self.assertTrue(m.loops and m.errors and m.human_interventions and m.idle_periods)
        self.assertGreaterEqual(p.get_llm_chunks(128)[0]["chunk_count"], 1)

    def test_codex_rollout_nested_events(self):
        rows = [
            {"timestamp": "2026-01-01T00:00:00Z", "type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "UserMessage", "content": [{"type": "text", "text": "help"}]}}},
            {"timestamp": "2026-01-01T00:00:01Z", "type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec", "input": "{\"cmd\":\"ls\"}", "status": "completed"}},
            {"timestamp": "2026-01-01T00:00:02Z", "type": "event_msg", "payload": {"type": "task_complete", "error": {"message": "limit"}}},
        ]
        p = AgentLogParser(); steps = p.parse_lines(map(json.dumps, rows)); m = p.analyze()
        self.assertEqual((steps[0].actor, steps[1].tool_name, steps[2].status), ("user", "exec", "error"))
        # The opening user request is the task, not an intervention (see _interventions).
        self.assertEqual(len(m.human_interventions), 0)
        self.assertEqual(len(m.errors), 1)
