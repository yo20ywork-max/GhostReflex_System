# GhostReflex Windows packaging

This packages the current `run_daemon.py` desktop HUD and its Paraformer voice
engine, with an independent pinned Ollama service. It does not package the old
`dist/GhostReflex_Portable/GhostReflex.exe`, start training, or alter weights.

Build on Windows x64, Python 3.12, using `BUILD_VERSIONS.json` from the release
report. The working runtime used torch / torchaudio 2.4.1 CPU, FunASR 1.4.13,
NumPy 1.26.4 and PyInstaller 6.22.2. ASR uses the CPU; Ollama selects supported
GPU acceleration or CPU fallback. Other hardware still needs its own validation.

The `--local` directory must contain the existing, verified
`dist/GhostReflex_Portable/models/paraformer-zh` and the `ollama_models` store.
The build is bounded to the user-approved delivery directory. Allow at least
25 GB free space and obtain permission before exceeding the workspace's
temporary-file limits. Do not replace pinned model digests with newly trained
weights or unverified downloads.

```powershell
$delivery = 'C:\path\to\approved-delivery'
python packaging/windows/build_release.py prepare --local C:\path\to\local-project --delivery $delivery
$env:GHOST_BUILD_SOURCE = "$delivery\work\source"
python -m PyInstaller --noconfirm --workpath "$delivery\work\build-agent" --distpath "$delivery\work\dist" packaging/windows/agent.spec
python packaging/windows/build_release.py models --local C:\path\to\local-project --delivery $delivery
python packaging/windows/build_release.py app --local C:\path\to\local-project --delivery $delivery
python packaging/windows/build_release.py manifest --local C:\path\to\local-project --delivery $delivery
$env:GHOST_RELEASE_MANIFEST = "$delivery\release\release.json"
python -m PyInstaller --noconfirm --workpath "$delivery\work\build-setup" --distpath "$delivery\release" packaging/windows/setup.spec
python -m unittest discover -s packaging/windows -p test_engine.py -v
```

Use a new release tag in `build_release.py` for a new build. Publish all assets
and verify their GitHub digests before making the draft visible. Do not replace
assets under an existing published tag: the bootstrap EXE embeds their hashes.

`GhostReflex-Setup.exe` installs per user at `%LOCALAPPDATA%\GhostReflex_System`,
downloads public GitHub assets without authentication, verifies SHA256,
extracts bounded paths, and creates a desktop shortcut. The base is split into
three files below GitHub's 2 GB limit and assembled automatically. The exact
original `ghost-brain` and `qwen2.5-coder:7b` manifests are preserved. This is
not a claim of new model training.
The standard `qwen2.5-coder:7b` configuration is the first planner/checker
candidate; the legacy `ghost-brain` configuration remains available as fallback.

The first run installs Playwright's Chromium. Subsequent normal starts use local
models and do not require model downloads. Web tasks naturally need network
access. Voice is never auto-executed: after recognition, press right Ctrl within
10 seconds. The control panel's close button and window close both stop only
the child processes in its Windows Job Object, including microphone capture.
Clipboard context and shell execution default to off. User workspace and logs
remain inside the install folder.

The release fixes a microphone VAD buffer bug that discarded the first two
candidate speech frames. Eight frames of pre-roll now include those frames,
without duplicating the activation frame. Pure greetings have conservative
handling: they produce a single reply instead of inferring desktop actions or
waiting for a second user message. Compound requests are not treated as pure
greetings. Model-generated plans and other reply formats still need review;
this preview does not establish the full product release gates.

For isolated acceptance testing, the bootstrap supports
`--root C:\approved-path\fresh-install --install-only --no-shortcuts`.
Then run `verify_frozen.py` against that root and a known Chinese WAV. The WAV
test is synthetic speech recognition, distinct from a live human microphone
transcription. The normal voice launch test actually opens and calibrates the
default microphone; no microphone recording is uploaded with the release.

The EXEs are not Authenticode signed. A Windows reputation prompt can appear.
Users should verify the published SHA256. Do not automate security prompts or
change Windows security/privacy settings. If microphone access is unavailable,
the controller reports the voice failure and keeps the text HUD available.
