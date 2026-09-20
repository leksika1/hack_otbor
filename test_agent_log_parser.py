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
