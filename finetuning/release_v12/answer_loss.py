"""Equivalent next-token CE, materializing vocabulary logits only for supervised tokens."""
def answer_only_forward(model,ids,labels):
    import torch
    import torch.nn.functional as F
    if ids.shape!=labels.shape or ids.shape[0]!=1:raise ValueError('One same-shaped sequence required')
    positions=torch.nonzero(labels[0,1:]!=-100).flatten()
    if positions.numel()==0:raise ValueError('No supervised answer tokens')
    output=model(input_ids=ids,attention_mask=torch.ones_like(ids),logits_to_keep=positions)
    targets=labels[:,positions+1]
    loss=F.cross_entropy(output.logits.float().reshape(-1,output.logits.shape[-1]),targets.reshape(-1))
    return output,loss
