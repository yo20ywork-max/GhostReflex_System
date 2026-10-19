"""Exact low-rank arithmetic for standard Linear LoRA, without dense weights."""
import math
import torch


def combine(updates):
    """Return A, B with B@A == sum(coefficient * scale * B_i@A_i).

    Each entry is (A_i, B_i, scale, coefficient). Put a negative coefficient
    on the error adapter. Never negate both factors: that cancels the sign.
    The returned rank is the sum of ranks; no lossy SVD is performed.
    """
    if not updates:
        raise ValueError("At least one update is required")
    factors_a, factors_b = [], []
    reference = updates[0][0]
    dimensions = None
    for a, b, scale, coefficient in updates:
        if a.ndim != 2 or b.ndim != 2 or a.shape[0] != b.shape[1]:
            raise ValueError("Invalid Linear LoRA shapes")
        if not a.is_floating_point() or not b.is_floating_point():
            raise ValueError("Use floating point adapter factors")
        if any(t.device != reference.device or t.dtype != reference.dtype for t in (a, b)):
            raise ValueError("All factors must share dtype and device")
        shape = (b.shape[0], a.shape[1])
        if dimensions is not None and shape != dimensions:
            raise ValueError("Adapter modules do not match")
        dimensions = shape
        if not math.isfinite(scale) or not math.isfinite(coefficient):
            raise ValueError("Non-finite scale")
        if not torch.isfinite(a).all() or not torch.isfinite(b).all():
            raise ValueError("Non-finite factors")
        factors_a.append(a)
        factors_b.append(b * (scale * coefficient))
    return torch.cat(factors_a, dim=0), torch.cat(factors_b, dim=1)
