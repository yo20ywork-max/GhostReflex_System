import math
import torch
import torch.nn as nn

class LoRALinear(nn.Module):
    def __init__(self, original_linear: nn.Linear, r: int = 4, lora_alpha: float = 8.0):
        super().__init__()
        self.original = original_linear
        self.original.weight.requires_grad = False
        if self.original.bias is not None:
            self.original.bias.requires_grad = False

        in_dim = original_linear.in_features
        out_dim = original_linear.out_features
        self.r = r
        self.scaling = lora_alpha / r

        # 隨機初始化 A，零初始化 B 保證剛載入時增量為 0
        self.lora_A = nn.Parameter(torch.zeros(r, in_dim))
        self.lora_B = nn.Parameter(torch.zeros(out_dim, r))
        nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))
        nn.init.zeros_(self.lora_B)

    def forward(self, x):
        base_out = self.original(x)
        lora_out = (x @ self.lora_A.T @ self.lora_B.T) * self.scaling
        return base_out + lora_out

def inject_lora_to_model(model, r=4):
    """凍結主幹，僅在每個 Block 的核心投影矩陣掛載 LoRA 參數"""
    for param in model.parameters():
        param.requires_grad = False

    trainable_params = 0
    for block in model.layers:
        cell = block.cell
        cell.q_proj = LoRALinear(cell.q_proj, r=r)
        cell.v_proj = LoRALinear(cell.v_proj, r=r)
        cell.out_proj = LoRALinear(cell.out_proj, r=r)
        trainable_params += (cell.q_proj.lora_A.numel() + cell.q_proj.lora_B.numel()) * 3

    print(f"[LoRA 注入完成] 基礎權重已凍結，可訓練參數僅：{trainable_params} 個 (極低資源開銷)")
    return model