import unittest
from answer_loss import answer_only_forward
class AnswerLoss(unittest.TestCase):
    def test_same_loss_and_parameter_gradients_as_masked_full_logits(self):
        import torch
        from transformers import Qwen2Config,Qwen2ForCausalLM
        torch.manual_seed(9)
        model=Qwen2ForCausalLM(Qwen2Config(vocab_size=29,hidden_size=16,intermediate_size=32,num_hidden_layers=1,num_attention_heads=2,num_key_value_heads=1,attention_dropout=0.0))
        model.eval()
        ids=torch.tensor([[1,5,9,12,15,19,3]]);labels=ids.clone();labels[:,:4]=-100
        reference=model(input_ids=ids,labels=labels).loss;reference.backward()
        gradients={n:p.grad.clone() for n,p in model.named_parameters() if p.grad is not None}
        model.zero_grad(set_to_none=True)
        output,actual=answer_only_forward(model,ids,labels);actual.backward()
        self.assertEqual(output.logits.shape[1],3)
        torch.testing.assert_close(actual,reference,rtol=1e-6,atol=1e-6)
        for n,p in model.named_parameters():
            if n in gradients:torch.testing.assert_close(p.grad,gradients[n],rtol=1e-5,atol=1e-6)
    def test_missing_answer_is_rejected(self):
        import torch
        with self.assertRaises(ValueError):answer_only_forward(None,torch.tensor([[1,2]]),torch.tensor([[-100,-100]]))
if __name__=='__main__':unittest.main()
