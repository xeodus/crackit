# Feasibility lab

This lab tests the highest-risk parts of the proposed product before committing to the full application stack. Read [the reliability implementation and results](RELIABILITY.md) for the current stage. [The original feasibility results](RESULTS.md) remain the historical baseline. The [research baseline](../research/README.md) covers feature parity, independent architecture, economics, and the delivery plan.

## Interview-first native capture bridge

`live_native.py` now connects explicit macOS ScreenCaptureKit system/microphone buffers to the v2 local source router. The native process converts each source to 16 kHz mono PCM, emits timestamped frames over a local Unix socket, and reports measured RMS and capture gaps. The Python side validates frame sizes, separates sources, resets only the affected source after a timestamp jump, and persists transcript/health metrics without storing raw PCM or uploading audio. LaunchServices starts the app so macOS applies its Screen Recording grant to the capture process. It is a diagnostic, not an installer or finished assistant.

Build with `make native` and `make local-engine`. Recreate the ignored short fixture with local macOS speech synthesis:

```sh
mkdir -p spikes/results/local/native
say -v Samantha -o spikes/results/local/native/interview-probe.aiff \
  'Explain the difference between a process and a thread. Then describe one race condition and how a mutex prevents it.'
.build/CrackitProbe.app/Contents/MacOS/CrackitProbe --convert-audio \
  spikes/results/local/native/interview-probe.aiff \
  spikes/results/local/native/interview-probe.wav
```

For a controlled 15-second system-audio check, play that known WAV after capture starts:

```sh
python3 -m spikes.live_native --seconds 15 \
  --play-wav spikes/results/local/native/interview-probe.wav \
  --expect-phrase 'difference between a process and a thread' \
  --out spikes/results/local/native/live-15s.json
```

macOS may require Screen Recording permission for this rebuilt app and a restart. Ad-hoc signing invalidates that permission after each rebuild; use a stable `CRACKIT_CODESIGN_IDENTITY` when available. The `--mic` flag additionally requests microphone access. A `completed` report requires no reported source gap or transport error; `controlled_signal_verified` also requires successful known playback, measurable system audio, and the expected recognized phrase. A failed permission attempt is recorded as incomplete, not counted as a capture pass.

For a repeatable synthetic endurance fixture, run `python3 -m spikes.interview_fixture --seconds 1800 --out spikes/results/local/native/interview-30m.wav`. This uses local macOS speech synthesis, mixes no real users, and creates a manifest with scripted text and turn times. Then use `spikes.live_native` with `--seconds 1805 --play-wav ... --summary-only`. A 30-minute run measures sustained transport and recognizer behavior on scripted non-overlapping speech; it does not establish human interview accuracy, true utterance-end latency, or screen-share exclusion. Keep recognition load isolated while measuring it.

## What exists

| Component | Implemented behavior | Boundary |
| --- | --- | --- |
| `core.py` | Session-scoped SQLite transcript revisions, final-only FTS5 search, deletion, pause/resume/stop, capture gaps, immutable evidence snapshots, stale-response gate | Local test engine; no production auth, encryption, sync, or application UI |
| `lab.py` | Synthetic replay, six retrieval cases, 1,801-segment accelerated long-history experiment | Does not record a real three-hour meeting |
| `native/Probe.swift` | User-started system/microphone buffer metrics; own-window overlay test; controlled audio conversion | macOS 15+ arm64 development diagnostic; no recognizer integration |
| `local_stt.py`, `native/local_stream.cpp` | CPU/Metal whole-file Whisper benchmark; persistent-model cumulative-prefix replay | At most 30 seconds; accelerated replay; no rolling streaming or permanent commitment policy |
| `providers.py` | Five grounded Gemini cases; paced AssemblyAI WebSocket audio benchmark | Optional credentials; controlled fixtures only; quality needs review |
| `budget.py` | Transactional usage reservations, verified coverage, separate $10 nominal/$2 possible-cash limits; old rows retained | Local accounting, not a provider-enforced billing cap |
| `streaming.py`, `transport.py`, `native/stream_worker.cpp` | Persistent CPU Whisper/Silero VAD, 30-second rolling window, final-only evidence, independent source epochs and explicit gaps | Reliability lab; native capture integration and latency gates remain separate |
| `dataset.py`, `evaluation.py`, `name_review.py` | Licensed VCTK subset, frozen speaker-held-out comparison, literal name preservation and confirmation suggestions | Read speech/synthetic owners; incomplete hosted runs stay incomplete |

## Run the offline checks

Python 3.9+ with SQLite FTS5 is sufficient. No package installation is needed for the context harness or Gemini adapter.

```sh
make test
make replay
make report
```

Tests cover revision ordering, conflicting duplicates, corrections removing stale search results, session/tenant filtering, Unicode context bounds, deletion, stale outputs, shared budget accounting, and streamed model usage parsing. Prompt byte limits cover the question and evidence representation in the snapshot. They do not establish an exact model-token ceiling or account for every provider envelope/system instruction. The lab uses lexical retrieval and a conservative token heuristic, not embeddings or a model tokenizer.

Reports go to `spikes/results/local/`, which is ignored by Git. Do not promote raw customer audio, screenshots, credentials, or private transcripts into the tracked results directory. Published results here contain fictional fixture output and aggregate diagnostic metrics.

## Native macOS diagnostic

Install Apple Command Line Tools, then:

```sh
make native
.build/CrackitProbe.app/Contents/MacOS/CrackitProbe --capabilities
open .build/CrackitProbe.app
```

The build is ad-hoc signed and not notarized. `--capabilities` checks authorization without starting capture. Opening the app does not capture audio. Use its controls to start a 15-second experiment or stop early. Screen recording permission may require quitting/reopening the app after a grant. Microphone capture is optional and starts only when selected. Stop unrelated system playback before a controlled test. The diagnostic stores metrics, discards audio buffers, and does not upload audio. It does not prove that the system and microphone channels are acoustically independent.

The overlay test captures only the diagnostic’s own magenta window, compares `.readOnly` and `.none`, computes a marker ratio, and discards both images. It is a selected-window ScreenCaptureKit/SCScreenshotManager test. Full-display sharing, conferencing clients, remote participants, recording applications, and Windows remain separate compatibility tests. Failure or an inconclusive baseline must not be described as successful exclusion.

The current diagnostic records audio format and the number of buffers on which RMS was measured. An RMS of zero without successful measurement is not evidence of silence. Older reports without that counter cannot distinguish silence from unsupported measurement. Validate a known audible fixture before claiming signal capture or speech accuracy.

## Local transcription experiment

The tested engine is [whisper.cpp v1.9.5](https://github.com/ggml-org/whisper.cpp/releases/tag/v1.9.5), pinned to commit `d1be6fde11ac6e0407606b4e42fe72d34add8037`. Prerequisites: CMake, a C++17 compiler, Apple SDK, and enough disk space for the checkout, build, and 148 MB model. Downloads are public artifacts, not paid API calls.

```sh
mkdir -p .cache
git clone --depth 1 --branch v1.9.5 https://github.com/ggml-org/whisper.cpp.git .cache/whisper.cpp
make local-engine
curl -L --fail https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin -o .cache/whisper.cpp/models/ggml-base.en.bin
shasum -a 256 .cache/whisper.cpp/models/ggml-base.en.bin
```

Expected model SHA-256 from the measured download: `a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002`. Check it before inference. The model URL follows an upstream repository; the recorded checksum identifies the exact tested artifact. `make local-engine` refuses an unexpected checkout commit and compiles the bounded causal probe with a runtime library path to the local build.

Generate fictional speech using an installed macOS voice and convert it:

```sh
mkdir -p spikes/results/local
say -v Samantha -r 175 -o spikes/results/local/controlled.aiff -f spikes/fixtures/speech.txt
.build/CrackitProbe.app/Contents/MacOS/CrackitProbe --convert-audio spikes/results/local/controlled.aiff spikes/results/local/controlled.wav
python3 -m spikes.local_stt --wav spikes/results/local/controlled.wav --reference spikes/fixtures/speech.txt --backend cpu --runs 3 --causal-replay --out spikes/results/local/local-stt-cpu.json
```

Repeat with `--backend metal` and a separate output path. Inspect backend logs to verify GPU use; requesting Metal is not sufficient. The sandbox on the tested machine prevented speech synthesis and GPU allocation; those commands succeeded with explicit system permission outside it. Empty generated audio and recognizer failures must be diagnosed, not scored as valid results.

Whole-file timing includes process/model startup and measures throughput, not interactive latency. Causal replay decodes every two seconds of cumulative available audio, retains the model, and never uses future audio. Execution is accelerated. Its agreed prefix is provisional, not an irreversible final transcript. Punctuation, uncertain names, incomplete words, and non-speech markers still need explicit treatment. The replay is limited to one short clip and does not implement voice activity detection, channel diarization, resampling live buffers, reconnects, or rolling meeting history.

WER lowercases Unicode words and does not normalize spoken numbers. It penalizes “twelve thousand dollars” versus “$12,000,” and ignores punctuation changes that can alter meaning. Review names, negation, dates, budgets, and action ownership separately. Never select a production recognizer using these TTS fixtures alone.

## Live provider benchmarks: $2 spending ceiling, up to $10 covered usage

The user authorized up to $10 of usage covered by verified free access/trial credits while retaining a $2 actual-spending ceiling. Gemini Free Tier and AssemblyAI $50 trial credits are user-confirmed. The ledger now applies the separate $10 nominal and $2 possible-cash ceilings. AssemblyAI auto-pay status remains unconfirmed; no billing changes are authorized. See [live results](LIVE_RESULTS.md) for measured usage and failures. No deposits or billing upgrades are authorized.

### Get the keys without buying subscriptions

1. **Gemini:** sign in to [Google AI Studio’s API keys page](https://aistudio.google.com/apikey), create/select a project and create an API key. New accounts start on the free tier. The current benchmark model `gemini-3.5-flash-lite` has free-tier input/output access, subject to account quotas. A consumer Gemini subscription is not required. Start with a free-tier project for our fictional fixtures. [API-key instructions](https://ai.google.dev/gemini-api/docs/api-key), [pricing](https://ai.google.dev/gemini-api/docs/pricing).
2. **AssemblyAI:** create a developer account through [AssemblyAI](https://www.assemblyai.com/), then copy/create the API key in its [dashboard](https://www.assemblyai.com/dashboard/). Its current documentation advertises $50 in trial credits, including Streaming STT, with no credit card needed to start. It uses usage billing rather than a monthly subscription. Check the actual credit balance shown for your account. [Key instructions](https://support.assemblyai.com/articles/7562135267-how-to-get-your-api-key), [free-trial details](https://support.assemblyai.com/articles/5370767329-can-i-sign-up-for-free).

Google’s paid-tier upgrade may require a minimum $5 prepayment. That exceeds the user-authorized $2 total budget, so remain on the free tier for these tests. If the dashboard requires payment or access is unavailable, report that instead of making a deposit. [Current billing requirements](https://ai.google.dev/gemini-api/docs/billing). Free-tier Gemini inputs may be used to improve Google products; the current benchmark contains only fictional data. Trial/free usage and our paid-list-price estimate are different quantities; reconcile the dashboard rather than treating the ledger as an invoice.

Save both keys locally in `.env` using [.env.example](../.env.example). Keep this file out of Git and chat. The status command prints configured key names, never key values.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r spikes/requirements.txt
python3 -m spikes.providers status
.venv/bin/python -m spikes.providers model --out spikes/results/local/cloud-model.json
.venv/bin/python -m spikes.providers stt --wav spikes/results/local/controlled.wav --out spikes/results/local/cloud-stt.json
```

Both commands share `spikes/results/local/usage.sqlite3`. Gemini reserves $0.03 per case and AssemblyAI reserves $0.03 per session. Five model cases plus one STT session reserve $0.18 before usage settlement. Missing usage, timeout, cancellation, and ambiguous failures retain the reservation. Requests are not retried automatically. Do not delete/reset the ledger to regain budget. An environment setting cannot override the authorized limits. Unknown usage retains its reservation; unresolved batch failures create a shared hosted-benchmark halt. Reservations bound known planned work, but cannot prevent provider billing changes or unrelated account spending; reconcile invoices before claiming actual cost.

Gemini uses `gemini-3.5-flash-lite`, at most 512 output tokens, minimal thinking, and a controlled prompt below 50 KB. Snapshot mode is the current default. The older all-evidence isolation experiment remains available with `--context-mode all`. Add `--context-mode snapshot` to use our bounded context engine with source-scoped lexical evidence and separately retained provisional text. This selection may still include irrelevant matches; both conditions are development experiments. First sentence punctuation is only a latency proxy. Validate answer correctness, citation support, correction handling, refusal on missing facts, and resistance to quoted malicious instructions. Citation-ID validity alone does not prove support. Successful cases are saved incrementally if a later case fails.

AssemblyAI sends only the explicitly supplied mono 16 kHz PCM WAV, paced in 100 ms frames, with three seconds of controlled trailing silence. The clip is limited to 30 seconds. It uses `universal-streaming-english`, turn formatting, and explicit termination. Turn-order replacement prevents formatted duplicates. First nonempty/final turn arrival is not end-of-utterance latency. Billing uses the greater reported session/audio duration at the documented list rate. Unknown termination usage remains reserved. No ambient audio or screenshots are transmitted by either benchmark.

## Next acceptance gates

1. Verify audible system and microphone signals, channel leakage, pause/stop, sleep/device changes, and sustained capture.
2. Compare local and hosted recognition on consented, representative speech, including names, accents, overlap, noise, and code-switching. Add a held-out set.
3. Build a bounded rolling local decoder with VAD, provisional/final revisions, silence-marker handling, and replayable failure traces.
4. Run/review budgeted model cases, then test retrieval and generation together with measured end-to-end latency.
5. Test each screen-share mode/client/OS combination with a remote participant before publishing compatibility claims.
6. Only after those gates, connect the native audio adapter, context store, and answer display into the first usable vertical slice. Full before/live/after workflow parity remains in the research roadmap.
