# Windows distribution records

GhostReflex's original project source and brand retain the terms in LICENSE.txt.
Third-party components retain their own licenses. Copies of dependency notices
are distributed in this directory; model notices are also preserved separately
from conversation input. This directory may contain notices for optional build
dependencies; presence of a notice alone does not imply a feature is enabled.

- Ollama 0.32.9: https://github.com/ollama/ollama/tree/v0.32.9 (MIT).
  The installer downloads the official Windows amd64 archive, with pinned SHA256.
- Qwen2.5-Coder-7B Q4_K_M: https://ollama.com/library/qwen2.5-coder:7b
  and https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct (Apache 2.0).
  The exact cached GGUF and original license layer are preserved without retraining.
  The ghost-brain tag shares the same base GGUF and preserves its existing
  system/template/parameter/message layers; it is not a newly trained weight set.
- Paraformer Chinese model: iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch
  (Apache 2.0 according to the supplied model README). The original README,
  configuration, tokens and weights are preserved without conversion.
- FunASR 1.4.13: https://github.com/modelscope/FunASR (MIT).
- PyTorch / torchaudio 2.4.1 CPU, Python 3.12, NumPy, SciPy, sounddevice,
  OpenCC, pynput, Pillow, Ollama Python client and Playwright are included in
  the frozen application. Their available distribution notices accompany it.
- Playwright installs its pinned Chromium build on first installation. Browser
  notices remain in that installation's browser directory.

The packaging changes configure local model paths, offline ASR loading and
per-process environments. No model training or weight editing is performed.
