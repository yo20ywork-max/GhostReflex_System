import math,unittest
import torch
from preference_math import completion_log_probability,dpo_loss

class PreferenceMath(unittest.TestCase):
    def test_reference_equal_loss_and_gradient_direction(self):
        chosen=torch.tensor(-2.,requires_grad=True);rejected=torch.tensor(-3.,requires_grad=True)
        loss=dpo_loss(chosen,rejected,-2.,-3.,0.1)
        self.assertAlmostEqual(float(loss),math.log(2),places=6)
        loss.backward();self.assertLess(float(chosen.grad),0);self.assertGreater(float(rejected.grad),0)
    def test_prompt_mask_and_next_token_shift(self):
        logits=torch.tensor([[[0.,0.],[1.,2.],[3.,1.],[0.,0.]]],requires_grad=True)
        labels=torch.tensor([[-100,-100,1,0]])
        total,mean=completion_log_probability(logits,labels)
        expected=torch.log_softmax(logits[0,1],0)[1]+torch.log_softmax(logits[0,2],0)[0]
        torch.testing.assert_close(total,expected);torch.testing.assert_close(mean,-expected/2)
        mean.backward();self.assertEqual(float(logits.grad[0,0].abs().sum()),0.)
    def test_improved_preference_reduces_loss(self):
        self.assertLess(float(dpo_loss(torch.tensor(-1.),torch.tensor(-4.),-2.,-3.)),float(dpo_loss(torch.tensor(-2.),torch.tensor(-3.),-2.,-3.)))

if __name__=='__main__':unittest.main()
