"""Incomplete backend streams must never produce successful latency evidence."""
import json
import unittest
from finetuning.release_v4.benchmark_target import consume


def lines(*events):
    return [json.dumps(event).encode()+b'\n' for event in events]


class TargetBenchmark(unittest.TestCase):
    def test_length_limited_response_is_preserved_but_incomplete(self):
        result = consume(lines({'message': {'content': '部分文字'}, 'done': False},
                               {'done': True, 'done_reason': 'length'}), 0, clock=lambda: 1)
        self.assertFalse(result['generation_complete'])
        self.assertEqual(result['text'], '部分文字')
        self.assertFalse(result['quality_verified'])

    def test_connection_end_without_done_is_failure(self):
        with self.assertRaisesRegex(ValueError, 'without completion'):
            consume(lines({'message': {'content': '看似完成'}, 'done': False}), 0, clock=lambda: 1)

    def test_extra_response_after_done_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'after terminal'):
            consume(lines({'done': True, 'done_reason': 'stop'}, {'message': {'content': '舊工作'}}), 0, clock=lambda: 1)

    def test_first_content_is_not_empty_metadata(self):
        times = iter([1, 2, 2.1, 3, 3.5])
        result = consume(lines({'message': {'content': ''}, 'done': False},
                               {'message': {'content': '結果'}, 'done': False},
                               {'done': True, 'done_reason': 'stop'}), 0, clock=lambda: next(times))
        self.assertEqual(result['first_content_seconds'], 2.1)
        self.assertEqual(result['wall_seconds'], 3.5)
        self.assertTrue(result['generation_complete'])


if __name__ == '__main__': unittest.main()
