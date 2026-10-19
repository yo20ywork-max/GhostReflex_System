"""Explicit synchronous data-parallel updates for the selective-logit loop.

Each rank backpropagates its local sequence-mean losses as a SUM. Gradients are
then summed and divided by the true global number of sequences, including the
uneven final batch. No duplicated padding examples or implicit DDP averaging.
This helper alone is not a complete distributed trainer.
"""


def rank_batch(global_indices, rank, world_size):
    if type(world_size) is not int or world_size<1 or type(rank) is not int or not 0<=rank<world_size:
        raise ValueError('Invalid distributed rank')
    return global_indices[rank::world_size]


def synchronize_gradients(parameters, *, local_samples, global_samples, bucket_bytes=8*1024*1024):
    import torch
    import torch.distributed as dist
    parameters=list(parameters)
    if not parameters:raise ValueError('No trainable parameters')
    if type(local_samples) is not int or local_samples<0 or type(global_samples) is not int or global_samples<1:
        raise ValueError('Invalid sample count')
    if type(bucket_bytes) is not int or bucket_bytes<1:raise ValueError('Invalid bucket size')
    active=dist.is_available() and dist.is_initialized()
    device=parameters[0].device
    if any(p.device!=device for p in parameters):raise ValueError('One device per rank required')
    bad=any(p.grad is not None and not torch.isfinite(p.grad).all().item() for p in parameters)
    checks=torch.tensor([local_samples,int(bad)],device=device,dtype=torch.int64)
    if active:dist.all_reduce(checks,op=dist.ReduceOp.SUM)
    if checks[0].item()!=global_samples:raise RuntimeError('Distributed sample count mismatch')
    if checks[1].item():raise RuntimeError('Non-finite local gradient; no optimizer update permitted')
    bucket=[];size=0;dtype=None
    def flush():
        if not bucket:return
        flat=torch.cat([(p.grad if p.grad is not None else torch.zeros_like(p)).reshape(-1) for p in bucket])
        if active:dist.all_reduce(flat,op=dist.ReduceOp.SUM)
        flat.div_(global_samples)
        offset=0
        for p in bucket:
            gradient=flat[offset:offset+p.numel()].view_as(p)
            if p.grad is None:p.grad=gradient.clone()
            else:p.grad.copy_(gradient)
            offset+=p.numel()
    for p in parameters:
        if not p.requires_grad:raise ValueError('Only trainable parameters may be synchronized')
        needed=p.numel()*p.element_size()
        if bucket and (dtype!=p.dtype or size+needed>bucket_bytes):
            flush();bucket=[];size=0
        bucket.append(p);size+=needed;dtype=p.dtype
    flush()
