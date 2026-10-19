import unittest
import torch
from counter_lora import combine


class CounterUpdateTests(unittest.TestCase):
    def test_signed_update_matches_dense_and_preserves_inputs(self):
        generator = torch.Generator().manual_seed(42)
        a = torch.randn(2, 7, generator=generator, dtype=torch.float64)
        b = torch.randn(5, 2, generator=generator, dtype=torch.float64)
        c = torch.randn(3, 7, generator=generator, dtype=torch.float64)
        d = torch.randn(5, 3, generator=generator, dtype=torch.float64)
        originals = [x.clone() for x in (a, b, c, d)]
        aa, bb = combine([(a, b, 2, 1), (c, d, 3, -0.1)])
        torch.testing.assert_close(bb @ aa, 2 * (b @ a) - 0.3 * (d @ c))
        for value, original in zip((a, b, c, d), originals):
            self.assertTrue(torch.equal(value, original))

    def test_identical_updates_cancel(self):
        a, b = torch.ones(2, 4), torch.ones(3, 2)
        aa, bb = combine([(a, b, 2, 1), (a, b, 2, -1)])
        torch.testing.assert_close(bb @ aa, torch.zeros(3, 4))

    def test_invalid_shape_rejected(self):
        with self.assertRaises(ValueError):
            combine([(torch.ones(2, 4), torch.ones(3, 1), 1, -1)])


if __name__ == "__main__":
    unittest.main()
