import unittest
class FusionDeltaTest(unittest.TestCase):
    def test_peft_cat_preserves_weighted_delta(self):
        import torch
        from transformers import Qwen2Config,Qwen2ForCausalLM
        from peft import LoraConfig,get_peft_model
        from fuse_adapters import check_delta_sum
        torch.manual_seed(8)
        config=Qwen2Config(vocab_size=32,hidden_size=16,intermediate_size=32,num_hidden_layers=1,num_attention_heads=2,num_key_value_heads=1)
        model=get_peft_model(Qwen2ForCausalLM(config),LoraConfig(r=2,lora_alpha=4,target_modules=['q_proj','v_proj']),adapter_name='left')
        model.add_adapter('right',LoraConfig(r=3,lora_alpha=9,target_modules=['q_proj','v_proj']))
        with torch.no_grad():
            for n,p in model.named_parameters():
                if 'lora_' in n:p.uniform_(-0.2,0.2)
        model.add_weighted_adapter(['left','right'],[0.5,0.5],'fusion',combination_type='cat')
        self.assertEqual(model.peft_config['fusion'].r,5)
        report=check_delta_sum(model,['left','right'],[0.5,0.5],'fusion')
        self.assertEqual(report['layers_checked'],2)
        self.assertTrue(report['all_sampled_delta_sums_passed'])
if __name__=='__main__':unittest.main()
