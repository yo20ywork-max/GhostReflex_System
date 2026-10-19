"""Standard reference-relative DPO loss, with torch imported only at execution."""
def dpo_loss(chosen,rejected,ref_chosen,ref_rejected,beta=0.1):
    import torch.nn.functional as F
    margin=(chosen-rejected)-(ref_chosen-ref_rejected)
    return -F.logsigmoid(beta*margin)

def completion_log_probability(logits,labels):
    import torch.nn.functional as F
    targets=labels[:,1:];mask=targets!=-100
    selected=logits[:,:-1,:][mask].float()
    target=targets[mask]
    if not target.numel():raise ValueError('No answer tokens')
    token_logp=F.log_softmax(selected,dim=-1).gather(-1,target[:,None]).squeeze(-1)
    return token_logp.sum(),-token_logp.mean()
