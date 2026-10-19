import torch
import torch.nn as nn
import torch.nn.functional as F

class ParallelMicroGLRCell(nn.Module):
    def __init__(self, dim=128, state_dim=24):
        super().__init__()
        self.dim = dim
        self.state_dim = state_dim
        self.kernel_size = 4
        self.conv1d = nn.Conv1d(dim, dim, kernel_size=self.kernel_size, groups=dim, padding=self.kernel_size - 1)
        self.q_proj = nn.Linear(dim, state_dim, bias=False)
        self.k_proj = nn.Linear(dim, state_dim, bias=False)
        self.v_proj = nn.Linear(dim, state_dim, bias=False)
        self.decay_proj = nn.Linear(dim, state_dim, bias=True)
        self.out_proj = nn.Linear(state_dim, dim, bias=False)

    def forward(self, x):
        B, T, D = x.shape
        conv_out = self.conv1d(x.transpose(1, 2))[:, :, :T].transpose(1, 2)
        h = x + conv_out

        q = F.relu6(self.q_proj(h)) / 6.0
        k = F.relu6(self.k_proj(h)) / 6.0
        v = self.v_proj(h)
        decay = torch.sigmoid(self.decay_proj(h))

        states = torch.zeros(B, self.state_dim, self.state_dim, device=x.device, dtype=x.dtype)
        outputs = []
        for t in range(T):
            q_t = q[:, t, :]
            k_t = k[:, t, :]
            v_t = v[:, t, :]
            d_t = decay[:, t, :].unsqueeze(-1)
            kv_t = torch.bmm(k_t.unsqueeze(-1), v_t.unsqueeze(1))
            states = states * d_t + kv_t
            out_t = torch.bmm(q_t.unsqueeze(1), states).squeeze(1)
            outputs.append(out_t)

        out_stacked = torch.stack(outputs, dim=1)
        return self.out_proj(out_stacked)

class MicroGLRBlock(nn.Module):
    def __init__(self, dim=128, state_dim=24):
        super().__init__()
        self.norm1 = nn.LayerNorm(dim)
        self.cell = ParallelMicroGLRCell(dim=dim, state_dim=state_dim)
        self.norm2 = nn.LayerNorm(dim)
        self.ffn = nn.Sequential(
            nn.Linear(dim, dim * 2, bias=False),
            nn.Hardswish(),
            nn.Linear(dim * 2, dim, bias=False)
        )

    def forward(self, x):
        x = x + self.cell(self.norm1(x))
        x = x + self.ffn(self.norm2(x))
        return x

class MicroGLRNet(nn.Module):
    def __init__(self, vocab_size, dim=128, state_dim=24, num_layers=4):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, dim, padding_idx=0)
        self.layers = nn.ModuleList([MicroGLRBlock(dim=dim, state_dim=state_dim) for _ in range(num_layers)])
        self.norm_f = nn.LayerNorm(dim)
        self.lm_head = nn.Linear(dim, vocab_size, bias=False)
        self.embedding.weight = self.lm_head.weight

    def forward(self, input_ids):
        x = self.embedding(input_ids)
        for layer in self.layers:
            x = layer(x)
        x = self.norm_f(x)
        return self.lm_head(x)
