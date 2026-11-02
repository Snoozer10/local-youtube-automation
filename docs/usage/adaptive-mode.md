# Adaptive staged mode

Adaptive staged mode builds one episode as a sequence of explicit, resumable steps.
It keeps channel identity separate from episode-specific creative direction, compiles a
timed visual plan, checks generated assets, and requires a person to review a rendered
preview before final rendering.

This guide covers the public entry point in [`adaptive_production.py`](../../adaptive_production.py)
and its implementation in [`production/cli.py`](../../src/youtube_automation/production/cli.py).
For installation, start with [Getting started](../getting-started.md). For profile setup,
see [Channel bundles](./channel-bundles.md); for reference-channel study, see
[Channel research](./channel-research.md).

## Quick path

The commands below illustrate the normal narrated-video route from an existing transcript
or prepared source script. They are examples, not a guarantee that the selected profile,
provider session, local tools, or media are ready. The analyze, write, plan, and generate
stages may use browser-connected model or visual-generation services; authorize those
actions separately and review each candidate before continuing.

The command sequence below is for a fresh run with no saved `visual_budget.json`. If that
file already exists and enables `require_review`, stop before `report`/`preview` and follow
the additional proof-and-audit procedure below; do not remove or weaken the saved budget.

Run commands from the repository root in PowerShell, using the project's `venv` created by
[Getting started](../getting-started.md). This example uses the bundled Professor Yashrah
profile, whose content and language policy are documented in [Channel bundles](./channel-bundles.md).

```powershell
# Start in the checked-out repository root.
$Repo = (Get-Location).Path
$Python = (Resolve-Path '.\venv\Scripts\python.exe').Path
$Runs = Join-Path $Repo 'youtube_runs'
if (-not (Test-Path -LiteralPath $Runs)) { New-Item -ItemType Directory -Path $Runs | Out-Null }
$Run = Join-Path $Runs 'my-first-adaptive-run'
if (Test-Path -LiteralPath $Run) { throw 'Choose a new run directory; this example will not overwrite an existing run.' }
New-Item -ItemType Directory -Path $Run | Out-Null
```

Create the required source text as UTF-8. `raw_transcript.txt` is the source material for
this episode: it can be a transcript you prepared from a source video or the research/script
text for a new episode. The adaptive CLI does not take a YouTube URL and fetch or transcribe
it for you. Do not paste a URL into this file and expect it to be resolved.

```powershell
$SourceText = @'
Replace this line with the reviewed transcript, source notes, or prepared episode script.
'@
$SourcePath = Join-Path $Run 'raw_transcript.txt'
if (Test-Path -LiteralPath $SourcePath) { throw 'Refusing to overwrite raw_transcript.txt.' }
Set-Content -LiteralPath $SourcePath -Value $SourceText -Encoding utf8
```

Select the profile explicitly, analyze the input, and inspect the generated brief before
writing or planning. A provider-backed `analyze` call may study the episode input and create
its episode-specific strategy; it does not rewrite the saved channel profile.

```powershell
$Profile = 'channels\professor-yashrah.json'
& $Python 'adaptive_production.py' analyze --run-dir $Run --channel-profile $Profile
Get-Content -LiteralPath (Join-Path $Run 'episode_brief.json') -Raw
```

Continue through script preparation and voice direction. The default adaptive TTS model is
`gemini-3.8-flash-tts`, which requires an approved, run-specific voice direction before it
speaks. Inspect the generated candidate yourself, then accept the exact candidate digest.
If you intentionally configured `ADAPTIVE_TTS_MODEL=gemini-2.5-pro-preview-tts`, the Pro
path does not use voice direction; it still needs a configured channel voice.

```powershell
& $Python 'adaptive_production.py' write --run-dir $Run
$TtsModel = (& $Python -c 'import youtube_automation.core.utils; from youtube_automation.production.voice_direction import adaptive_tts_model; print(adaptive_tts_model())').Trim()
if ($TtsModel -notin @('gemini-3.8-flash-tts', 'gemini-2.5-pro-preview-tts')) {
    throw "Unsupported ADAPTIVE_TTS_MODEL: $TtsModel"
}
if ($TtsModel -eq 'gemini-3.8-flash-tts') {
    & $Python 'adaptive_production.py' generate-direction --run-dir $Run
    $Candidate = Join-Path $Run 'voice_direction.candidate.json'
    Get-Content -LiteralPath $Candidate -Raw
    $DirectionHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Candidate).Hash.ToLowerInvariant()
}
```

Pause after generating the direction candidate. Read the complete candidate, compare it with the approved channel voice policy and episode needs, and have a human reviewer decide whether it is acceptable. Do not accept it solely because generation succeeded. Only after that explicit review run the acceptance command below. The Pro route skips this direction-acceptance step.

```powershell
if ($TtsModel -eq 'gemini-3.8-flash-tts') {
    & $Python 'adaptive_production.py' accept-direction --run-dir $Run --reviewer 'Your Name' --direction-sha256 $DirectionHash
}
```

After accepting the reviewed Flash direction, or selecting the Pro route with its configured channel voice, continue with voice generation.

```powershell
& $Python 'generate_voice.py' $Run
& $Python 'automate_audacity.py' $Run
& $Python 'stitch_chapters.py' $Run
& $Python 'faster_whisper_transcribe_audio.py' $Run
```

The direction-generation and TTS steps use a browser-connected provider; Audacity uses local
desktop automation, and transcription uses a local model. These are separate entry points,
not adaptive CLI stages. Configure and authorize each concrete action, then verify each
output before moving on. Do not accept a generated direction without reviewing its candidate.

If the episode will use audio from a local video rather than generated narration, do not run
`write`, `generate-direction`, TTS, Audacity, or chapter stitching. After `analyze`, use the
source-audio branch below to import an explicitly bounded segment, then run the transcriber
and continue at `plan`.

Create and inspect the timed visual plan. `plan` is model-assisted, then Python compiles
semantic intent into deterministic timing, IDs, narration excerpts, continuity operations,
camera defaults, and local overlay geometry. A bounded critic review must accept every shot
before image generation can proceed.

```powershell
& $Python 'adaptive_production.py' plan --run-dir $Run
Get-Content -LiteralPath (Join-Path $Run 'shot_plan.json') -Raw
```

Inspect the compiled plan. Then generate the planned visual assets and build the review
report. `generate` does not create a visual audit. A per-shot visual audit is required only
when the run's saved `visual_budget.json` sets `require_review` to true; see “Budget and
visual audit” below. Human review of the final preview is required in every case.

```powershell
& $Python 'adaptive_production.py' generate --run-dir $Run
& $Python 'adaptive_production.py' report --run-dir $Run
& $Python 'adaptive_production.py' preview --run-dir $Run
```

This sequence assumes the new run has no budget file that requires per-shot visual review.
If its saved `visual_budget.json` does require review, first run `proofs`, inspect the
samples, and create `visual_audit.json` as described below; only then run `report` and
`preview`. The CLI checks that gate before those stages.

Watch the preview as a person. Confirm the narration, pacing, image-to-script match,
readability, continuity, overlays, and audio. For a version-3 brief, create a scorecard from
your actual review before approving; otherwise `approve` will fail. Do not treat a successful
render, audit, scorecard, or model critic as human approval. After review, explicitly approve
and render:

```powershell
& $Python 'adaptive_production.py' approve --run-dir $Run --reviewer 'Your Name'
& $Python 'adaptive_production.py' render --run-dir $Run
```

Use the commands on your own run directory. The preview, approval, and final render are
bound to the inputs and review evidence; changing relevant inputs makes earlier artifacts
stale and requires the affected steps to be repeated.

## What Adaptive staged mode does

The pipeline records an explicit run directory and ledger state for each step. Stage
recipes include the content and configuration inputs that determine whether an earlier
result still applies. Re-running a stage with unchanged, verified inputs normally reports
that it already succeeded or registers a verified existing output. A changed recipe
triggers validation and, when required, archives affected outputs before rebuilding them.

| Concern | Adaptive behavior |
| --- | --- |
| Channel identity | Loaded from the explicitly selected profile; analysis cannot silently change stable identity. |
| Episode strategy | Bound to that episode’s source, topic, timeline, and current channel policy. |
| Script and speech | The episode brief, refined script, generated chapter audio, and word-timed timeline are linked and verified. |
| Visual planning | Model-authored semantic intent is validated and compiled by deterministic Python rules. |
| Image generation | Requires the plan, critique, asset checks, and visual budget to pass. |
| Review | Report and render proofs inform review; a person watches the preview and explicitly approves. |
| Recovery | A local ledger, stage recipes, receipts, and invalidation journals support safe resume and diagnosis. |

### Main outputs by stage

This is the common artifact path; optional branches and configuration add receipts, proofs,
reviews, and assets. Use the run directory as the source of truth and preserve its journals.

| Step | Main input | Main output to verify |
| --- | --- | --- |
| Prepare / `analyze` | `raw_transcript.txt`, selected channel profile | `episode_brief.json` with source/profile lineage and episode visual strategy. |
| `write` | Current source text and brief | `refined_script.txt`, `final_output.txt`, `breaked_paragraphs.txt`, and `adaptive_writing_receipt.json`. |
| Direction (Flash TTS only) | Current script and channel voice | `voice_direction.candidate.json`; after human acceptance, `voice_direction.json`. |
| Voice generation | Accepted script, profile voice, required direction | `voice_generation_manifest.json`, `voice_chapters/`, then polished chapters/master audio through the audio workflow. |
| Transcription | Verified master audio and ASR language | `timeline.json` with canonical word timing. |
| `plan` | Brief, timeline, visual policy | `shot_plan.json`, `editorial_review.json`, and versioned semantic checkpoints where applicable. |
| `generate` | Current plan and visual budget | Generated assets plus per-asset receipts and visual spending journal; deterministic local visuals may be compiled locally. |
| `source-audio` | Local media segment and source text | `source_audio_receipt.json`, content-named WAV under `source_audio/`, source-preserved script outputs, and a writing receipt. |
| `report` | Current brief/plan and any assets present | `adaptive_review/index.html` and contact sheets; missing images may appear as missing placeholders. |
| `proofs` | Current audio, plan, assets, render recipe | Sampled diagnostic PNGs and a manifest under `.adaptive_diagnostics/render_proofs/`; this is not a visual audit or a moving-video preview. |
| `preview` | Current audio, plan, assets, render settings | Review video and `adaptive_preview.json` receipt. |
| `approve` | Current preview and real human review | `editorial_approval.json`; version-3 briefs also require `preview_scorecard.json`. |
| `render` | Current approval and unchanged render inputs | Final master video and content-bound render receipt/activation metadata. |

The planner enforces canonical narration coverage, shot-duration limits, visual-mode and
composition repetition constraints, framing diversity, selective motion, continuity, and
channel-forbidden visual policy. It preserves accepted semantic records during targeted
repair where possible. The critic is a bounded automated editorial check; it does not certify
truth, audience performance, or human acceptance.

Adaptive staged mode is one of the repository’s production modes, alongside [Legacy batch
mode](../../README.md#how-it-works). It is not a claim that every niche, provider,
machine, or workflow can complete unattended.

## Inputs and preparation

### The run directory

Create a new, empty directory for a new episode. The CLI requires `--run-dir` for production
stages, and that directory must already exist. Keep the source file, episode outputs, audio,
visual receipts, reports, previews, and recovery records together under this run directory
unless the relevant interface explicitly accepts an external file.

Avoid reusing a run directory for an unrelated episode. The ledger and generated artifacts
are tied to the run's inputs. Copying files from another run can break those bindings and
invalidate receipts.

### Source URL, transcript, or researched script

The adaptive production CLI accepts a run directory, not a source-video URL. It does not
download a video, extract a transcript from YouTube, conduct reference-channel research, or
verify source claims as part of the `analyze` command.

Prepare the text that belongs in `raw_transcript.txt` before `analyze`:

- For a source video, obtain and review its transcript or notes through a workflow you are
  authorized to use, then save the intended text as UTF-8.
- For a researched-topic episode, prepare the research notes or source script first. Keep
  citations and fact-checking in your research workflow; a generated episode brief is not
  evidence that claims were externally verified.
- For a supplied script, place the source text in `raw_transcript.txt` and decide whether
  you want the `write` stage to transform it into the channel’s spoken format.

`analyze` binds the brief to the source text and selected profile. A change to either is a
meaningful new input. When analysis requests factual verification, `evidence_needs` describes
external verification needs; it does not fetch the evidence. Fictional facts and visible
states belong to continuity anchors, not real-world research claims.

### Using an existing script

The standard `write` stage uses the model-assisted episode-writing path. The supported
accepted-original path publishes the accepted `raw_transcript.txt` words without rewriting
them (it trims outer whitespace and writes a trailing newline) when the run contains a valid
`script_acceptance.json`. There is no CLI stage or factory function for
creating the record; the source-supported file contract is shown below. Create it only after
you personally reviewed and accepted that exact text as spoken narration for the selected
channel. `analyze` must have completed first so the brief binds the same source and channel.

This PowerShell example uses the installed Python package to compute the required content
fingerprint and channel ID, then creates the acceptance file exclusively so it cannot
silently overwrite a prior decision:

```powershell
$AcceptanceBuilder = @'
import json
import sys
from pathlib import Path
from youtube_automation.production.contracts import fingerprint, load_brief

run = Path(sys.argv[1]).resolve()
accepted_by = sys.argv[2].strip()
statement = sys.argv[3].strip()
if not accepted_by or not statement:
    raise ValueError("Provide the human reviewer and acceptance statement")
raw = (run / "raw_transcript.txt").read_text(encoding="utf-8-sig")
brief = load_brief(run)
record = {
    "version": 1,
    "kind": "accepted_original_script",
    "channel_id": brief.channel.channel_id,
    "script_sha256": fingerprint(raw),
    "accepted_by": accepted_by,
    "statement": statement,
}
with (run / "script_acceptance.json").open("x", encoding="utf-8") as handle:
    json.dump(record, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
'@
$AcceptanceBuilder | & $Python - $Run 'Your Name' 'I reviewed and accept this exact script as narration for this channel.'
& $Python 'adaptive_production.py' write --run-dir $Run
```

The acceptance record is invalid if the source text or selected channel changes, or if the
reviewer or statement is missing. The script must be non-empty and cannot contain
`<final_script>` markup. Once accepted, do not edit `raw_transcript.txt`; changed text needs a
fresh human review and matching record. This path performs no writing-model request.

For normal model-assisted usage, `write` creates `refined_script.txt`, and voice generation
uses that script. A `<final_script>...</final_script>` response is unwrapped only when it is
one complete non-empty wrapper with no extra non-whitespace text. Source context and cached
model response are preserved for recovery.

### Channel profile versus episode strategy

A channel bundle contains the stable identity, audience, voice, policy, and visual
constraints used to make episodes recognizable. Select one explicitly using `--channel-profile`.
Do not edit the profile to describe one episode’s topic or visual plan. `analyze` creates or
updates the episode-specific brief and visual strategy while keeping the selected identity
separate. If you need a new channel profile, use [Channel bundles](./channel-bundles.md).

The anime sample profile currently has no configured voice. A missing voice configuration
means its TTS path needs profile work before voice generation can succeed; a bundled example
is not proof that every profile is production-ready.

## Stage reference

The supported stage names and shared arguments are defined by the current parser in
[`production/cli.py`](../../src/youtube_automation/production/cli.py). Run the entry point
with `--help` only after your environment is installed and project guidance permits it; the
reference below reflects the checked-in parser and implementation.

| Stage | Purpose and important conditions |
| --- | --- |
| `analyze` | Requires `--channel-profile`; uses `raw_transcript.txt` to create or refresh `episode_brief.json` and episode strategy. May use a model/browser transport. |
| `write` | Creates the refined spoken script from the brief, or publishes a valid pre-accepted original script verbatim. |
| `direct` | Validates a local direction response JSON supplied with `--direction-response-file`; it makes no provider request. Produces an unapproved candidate. |
| `generate-direction` | Provider-backed automated voice-direction generation. Produces an unapproved candidate and may use an authorized Gemini browser session. |
| `accept-direction` | Human-accepts a candidate only with `--reviewer` and the exact `--direction-sha256`. |
| `source-audio` | Imports an explicitly selected media segment into the run as source narration; requires media path and start/end seconds. |
| `adopt-polished-audio` | Adopts an exact externally polished WAV only with matching audio and acceptance paths and SHA-256 values. |
| `plan` | Creates, validates, repairs, and compiles the shot plan, then runs a bounded critic. |
| `generate` | Generates missing planned visual assets after plan, critic, budget, and input validation. |
| `report` | Writes the local adaptive review report under `adaptive_review/`. |
| `preview` | Renders the review preview using current inputs and video configuration. |
| `approve` | Records explicit human approval after preview review; for version-3 briefs, a valid scorecard is also required. |
| `render` | Renders the final video only from current approved inputs. |
| `proofs` | Produces current render-proof diagnostics for the run. |
| `status` | Reads and formats local production-ledger state. It does not run a production stage. |
| `diagnose` | Requires `--last`; displays the latest bounded local failure record, optionally from `--path`. It is read-only. |
| `retention` | Reports runtime retention by default; supports `--runtime-dir`, `--dry-run`, `--archive-cohort`, and `--restore-cohort`. |

All production stages require `--run-dir PATH`. The run directory must already exist. The
retention stage can instead target a runtime root using `--runtime-dir`; without an archive
or restore request, it prints a dry-run report and makes no changes. `proofs`, `status`,
`diagnose`, and `retention` are inspection/maintenance interfaces, not episode production
stages.

Shared optional parser flags are stage-scoped and validated:

| Flag | Applies to | Meaning |
| --- | --- | --- |
| `--channel-profile PATH` | `analyze` | Explicit channel profile input. |
| `--strategy-feedback-file PATH` | `analyze` with `--force-retry` | Non-empty editorial feedback requesting a revised v3 episode visual strategy. |
| `--direction-response-file PATH` | `direct` | Local UTF-8 JSON response; no provider request. |
| `--reviewer NAME` | `accept-direction`, `approve` | Human identity recorded with the exact action. |
| `--direction-sha256 HASH` | `accept-direction` | Digest of the direction candidate being accepted. |
| `--scorecard-file PATH` | `approve` | JSON scorecard input; it is validated and recorded. |
| `--media-file PATH`, `--start-seconds N`, `--end-seconds N` | `source-audio` | Explicit source media file and selected segment. |
| `--polished-audio-file PATH`, `--polished-audio-sha256 HASH`, `--audio-acceptance-file PATH`, `--audio-acceptance-sha256 HASH` | `adopt-polished-audio` | Exact WAV plus separate existing human acceptance evidence; no transcoding. |
| `--last`, `--path PATH` | `diagnose` | Read a bounded failure record or select its local JSONL path. |
| `--runtime-dir PATH`, `--dry-run`, `--archive-cohort ID`, `--restore-cohort ID` | `retention` | Inspect, reversibly archive, or restore an eligible runtime cohort. |
| `--force-retry` | Corrected retry | Retry after the bounded stage failure circuit opens; it is not a generic freshness switch. |

The accepted `--scorecard-file` JSON keys are `semantic_match`, `hook_strength`, `attractiveness`,
`progression`, `continuity`, `readability`, and `motion`, as defined by the current preview
scorecard model. Inspect the preview and record honest scores; do not use fabricated scores
to bypass the review threshold. For version-3 briefs, approval validation requires that the
scorecard pass its publishability rules.

## Voice, audio, and source narration

### Generated narration route

The usual narration route is `write`, voice generation, Audacity polishing, chapter
stitching, and word-level transcription. The root scripts are compatibility entry points
for maintained modules; they are separate from the adaptive CLI:

- [`generate_voice.py`](../../generate_voice.py) invokes the audio TTS generator. It creates
  chapter audio and a generation manifest based on the run’s refined script and profile.
- [`automate_audacity.py`](../../automate_audacity.py) invokes the Audacity client. The
  adaptive path relies on owned resources and exact local process checks; do not close or
  control an unrelated Audacity instance.
- [`stitch_chapters.py`](../../stitch_chapters.py) requires an explicit run directory for
  adaptive runs. It verifies completed chapters and prefers polished chapters; adaptive
  stitching rejects a route that lacks verified polished chapter audio.
- [`faster_whisper_transcribe_audio.py`](../../faster_whisper_transcribe_audio.py) uses the run profile’s ASR language when
  an episode brief exists and prefers the polished master audio, then falls back to the raw
  master track. It writes the word-timed timeline consumed by planning and rendering.

Generated voice is a provider-assisted workflow and may require configured accounts,
browser access, an explicit voice in the channel profile, an operational Audacity setup,
and the local speech-recognition model. Check [`docs/getting-started.md`](../getting-started.md)
and the relevant config files before running it.

### Source audio route

For narration that already exists in a local media file, use a branch from `analyze` that
skips `write`, direction generation, TTS, Audacity, and chapter stitching. The `source-audio`
stage imports a bounded segment and source-preserves the prepared text as its spoken script.
The source text and selected audio must match. The CLI expects all three values:

```powershell
& $Python 'adaptive_production.py' source-audio --run-dir $Run --media-file 'C:\media\source-video.mp4' --start-seconds 32 --end-seconds 418
& $Python 'faster_whisper_transcribe_audio.py' $Run
& $Python 'adaptive_production.py' plan --run-dir $Run
```

The command verifies the source media and the selected range and writes the source-narration
artifact set with lineage to the episode brief. It does not fetch the media from a URL,
transcribe it, or approve the resulting narration. Check its output and run verification
before later stages.

If an audio engineer has already polished a WAV outside the managed audio workflow, use
`adopt-polished-audio` only when you already have the exact WAV hash and a separate
human-acceptance JSON plus its exact hash. Adoption does not transcode, clean, or validate
subjective audio quality. It records the supplied identity and acceptance evidence and
blocks other audio stages while adoption recovery is pending.

## Planning, images, overlays, and audits

### Deterministic semantic compilation

`plan` is more than a prompt that asks for an arbitrary shot list. It combines the brief,
canonical word timing, the episode’s visual palette, continuity/reference context, and
compiler-owned constraints. For current version-3 plans, the model returns semantic intent;
Python assigns stable IDs, timing, narration excerpts, continuity operations, treatments,
camera defaults, and overlay geometry. The compiled plan must cover the canonical narration
without gaps or overlaps outside its accepted representation.

When validation finds a semantic defect, bounded repairs target the affected intent records
while preserving accepted records and stable references where possible. Deterministic
constraints stay in Python; the model is not asked to invent timing or override the channel’s
forbidden policy. A critic examines each compiled shot’s relationship to its narration,
viewer takeaway, continuity, and visual specificity. The critic must accept the plan before
Flow asset generation begins.

### Generated and local visual assets

The `generate` stage verifies the plan and registered asset receipts. For generated assets,
the Flow integration uses the selected model and count settings and records durable receipts
for completed outputs. Existing valid receipts can be reused when their bound inputs remain
identical. Interrupted or mismatched attempts are recovered or refused through the stage
journal; do not delete partial evidence as a first troubleshooting step.

Some plans compile deterministic local canvases or overlays rather than asking Flow to draw
every visual element. Local graphic cues are generated from typed plan data, and the renderer
composes overlays using its shared filter recipe. These assets still participate in plan,
receipt, review, and render-input validation.

### Budget and visual audit

The visual budget is enforced before generation and again at review/render boundaries. The
implementation caps the absolute image count at 400, but the default limit is duration-aware
(up to 20 images per minute, with a minimum of 20); a saved run or pilot budget may set a
lower cap. The budget is an upper bound, not a target. Never increase it as a workaround for a
poor plan.

When no `visual_budget.json` exists, the implementation derives the default limit and sets
`require_review` to false. If a budget file exists, `require_review` defaults to true unless
the saved file explicitly sets another value. Treat an existing budget as an intentional
review policy; do not delete it or turn review off to get past a gate. If per-shot review is
enabled, `report`, `preview`, `approve`, and `render` require the current audit before they
advance.

The visual audit checks registered image identity and content before downstream review. OCR
validation requires the configured English and Arabic OCR data (`eng+ara`) when validating
text-bearing backgrounds. If OCR or language data is unavailable, the image remains
unverified and the downstream gate blocks it; do not mark it accepted by hand. Reference
images and character assets are bound by identity and content hashes where supported, and
the plan must declare how recurring entities remain visually continuous.

The `report` stage writes an HTML contact sheet at `adaptive_review/index.html`; before image
generation, missing images appear as placeholders. The `proofs` stage renders sampled PNG
frames from each current shot, saves `manifest.json` and diagnostic data under
`.adaptive_diagnostics/render_proofs/`, and binds them to the current plan, assets, audio,
renderer inputs, and FFmpeg build. It does not execute the production H.264 encoder, create a
full moving preview, write `visual_audit.json`, or grant editorial approval. Neither the
report nor sampled proofs replace inspection of the complete preview and rendered media.
The stage runs local FFmpeg sampling and encoder probes under the shared encoder lease; it
is an explicit local media operation, not an offline metadata-only check.

### Required per-shot audit when enabled

Proof collection is a local FFmpeg/probe action. The proofs command acquires the established encoder lease and writes the render-input recipe and digest to its manifest; this example reads that receipt and does not call current_render_inputs() itself. That helper performs encoder-dependent discovery and must only be called under the established lease. Checking that the receipt digest matches its recorded inputs verifies receipt integrity; it does not establish that the inputs are still current or replace the per-shot human audit. The later production gate checks freshness against the current recipe. The proofs CLI currently binds root video_config.txt, while preview can load a run-local override, so this proof recipe does not validate a different run-local video configuration; preserve the actual configuration and do not claim that override is covered.



There is no `audit` CLI stage and no helper that automatically writes an audit. The supported
validation API is `VisualAudit` / `VisualDecision` in
[`visual_gate.py`](../../src/youtube_automation/production/visual_gate.py). When the saved
budget requires per-shot review, the reviewer must inspect the current sampled PNGs and
assemble a version-2 `visual_audit.json` for every shot in exact plan order. It binds the
current plan fingerprint, exact asset receipt hashes, the `current_render_inputs_sha256`
from the proof manifest, and proof paths/hashes. Each shot needs real reviewer notes and
scores of at least 4/5 for semantic match, continuity, readability, and attractiveness.

The following assembly example uses the checked-in schema and APIs. It intentionally stops
until you fill `human_reviews` for every shot after looking at that shot’s proof frames; the
code does not inspect images or generate review scores for you. Run only after `generate`
completes and the `proofs` stage has produced current evidence.

```python
import json
from pathlib import Path

from youtube_automation.core.utils import atomic_write_json
from youtube_automation.production.contracts import fingerprint
from youtube_automation.production.shots import ShotPlan
from youtube_automation.production.visual_gate import VisualAudit, VisualDecision

run = Path(input("Enter the existing run directory: ").strip()).resolve(strict=True)
reviewer = input("Reviewer name: ").strip()
plan = ShotPlan.model_validate_json((run / "shot_plan.json").read_text(encoding="utf-8"))
proof_root = Path(input("Enter the proof directory printed by `proofs`: ").strip()).resolve(strict=True)
if not proof_root.is_relative_to(run):
    raise ValueError("Proof directory must be inside this run")
manifest = json.loads((proof_root / "manifest.json").read_text(encoding="utf-8"))
if manifest["status"] != "COMPLETE_SAMPLED_PNGS":
    raise ValueError("Proof manifest is incomplete")
if manifest["plan_fingerprint"] != fingerprint(plan):
    raise ValueError("Proof manifest belongs to another plan")
if manifest["current_render_inputs_sha256"] != fingerprint(manifest["current_render_inputs"]):
    raise ValueError("Proof manifest render-input digest is invalid")
assets = manifest["assets"]

# After personally inspecting every sample listed for each shot, enter one review per shot.
human_reviews = {
    # "shot-id-from-plan": {
    #     "semantic_match": 4,
    #     "continuity": 4,
    #     "readability": 4,
    #     "attractiveness": 4,
    #     "notes": "Describe the observed image-to-script match and any issue checked.",
    # },
}
if set(human_reviews) != {shot.shot_id for shot in plan.shots}:
    raise ValueError("Enter an actual visual review for every current shot")

decisions = []
for shot in plan.shots:
    samples = [sample for sample in manifest["samples"] if sample["shot_id"] == shot.shot_id]
    if not samples:
        raise ValueError(f"No proof samples for {shot.shot_id}")
    paths = {
        (proof_root / sample["path"]).resolve().relative_to(run).as_posix(): sample["sha256"]
        for sample in samples
    }
    primary_path, primary_sha256 = next(iter(paths.items()))
    extra_proofs = dict(list(paths.items())[1:])
    decision = human_reviews[shot.shot_id]
    decisions.append(VisualDecision(
        shot_id=shot.shot_id,
        proof_path=primary_path,
        proof_sha256=primary_sha256,
        additional_proofs=extra_proofs,
        **decision,
    ))

audit = VisualAudit(
    version=2,
    plan_sha256=fingerprint(plan),
    assets=assets,
    render_inputs_sha256=manifest["current_render_inputs_sha256"],
    reviewer=reviewer,
    decisions=decisions,
)
audit_path = run / "visual_audit.json"
if audit_path.exists():
    raise FileExistsError("Preserve and review the existing visual_audit.json before creating a replacement")
atomic_write_json(str(audit_path), audit.model_dump(mode="json"))
```

The example’s `human_reviews` mapping is deliberately unfilled: using invented scores would
falsify a human-review record. Changing the plan, image bytes, audio, video configuration,
renderer, FFmpeg build, or proof pixels invalidates the binding; generate fresh proofs,
inspect them again, and assemble a fresh audit. The separate full-preview human approval is
still required after this per-shot audit.

The `proofs` command currently binds its manifest to the repository-root `video_config.txt`.
Do not assume proof/audit validation works with a different per-run video configuration; the
gate recomputes the current render recipe. Preserve the intended configuration and resolve
support before continuing. The example refuses to replace an existing `visual_audit.json`;
preserve that file and its review notes before preparing a replacement.

## Preview, scorecard, human approval, and final render

Before `preview`, current planned assets and visual-audit evidence must pass. Preview
rendering uses the run’s audio, plan, registered images, renderer version, tool version, and
video settings. The preview receipt binds these inputs and its generation identity.

Review the resulting preview file directly and check at least:

- Narration coverage and word-to-shot synchronization.
- Hook clarity, progression, pacing, and sensible pauses.
- Visual specificity and whether each shot actually depicts its narration.
- Recurring entity identity, reference continuity, and scene-to-scene changes.
- Text legibility, safe margins, OCR-sensitive content, and overlay timing.
- Voice intelligibility, loudness, cuts, transitions, and final audio/video alignment.

For version-3 episodes, an actual human scorecard is required. The supported Python API
`record_preview_scorecard(run_dir, reviewer, scores)` validates your scores against the
current plan and preview, checks for a matching human rejection, and writes
`preview_scorecard.json` bound to the plan, preview, reviewer, and current audio state.
Each of the seven dimensions is an integer from 1 to 5; every dimension must be at least 4
to approve. The API does not infer ratings from a rendered preview.

After watching the complete preview, call the API with scores and notes that reflect your
own review. Fill the values; do not copy the numbers below as a pre-approved scorecard.

```python
from pathlib import Path
from youtube_automation.production.review import record_preview_scorecard

def ask_score(name):
    score = int(input(f"{name} score (1–5): "))
    if not 1 <= score <= 5:
        raise ValueError("Enter a score from 1 to 5")
    return score

record_preview_scorecard(
    run_dir=Path(input("Existing run directory: ").strip()),
    reviewer=input("Reviewer name: ").strip(),
    scores={
        "semantic_match": ask_score("Semantic match"),
        "hook_strength": ask_score("Hook strength"),
        "attractiveness": ask_score("Attractiveness"),
        "progression": ask_score("Progression"),
        "continuity": ask_score("Continuity"),
        "readability": ask_score("Readability"),
        "motion": ask_score("Motion"),
        "notes": input("Describe the preview you reviewed and any issue: ").strip(),
    },
)
```

The CLI alternative is `--scorecard-file PATH` on `approve`. That input file contains the
seven score fields and `notes` only; the CLI records the current plan/preview/reviewer
bindings for you. Use actual scores, then approve:

```powershell
& $Python 'adaptive_production.py' approve --run-dir $Run --reviewer 'Your Name' --scorecard-file (Join-Path $Run 'my-preview-scores.json')
```

Alternatively, after calling `record_preview_scorecard`, omit `--scorecard-file`:

```powershell
& $Python 'adaptive_production.py' approve --run-dir $Run --reviewer 'Your Name'
```

Approval binds the reviewer, plan fingerprint, exact assets, preview generation/hash, and
for v3, scorecard fingerprint. If a person rejects the preview, the rejection blocks approval
of that same plan/preview. Revise the affected inputs, regenerate invalidated outputs, make a
new preview, and review the new candidate. Approval does not publish the episode to YouTube.

`render` requires current approval and current inputs. The final output is a locally rendered
video artifact with a receipt tied to the current assets, audio, settings, renderer code, and
tools. Hardware encoding can fall back to software encoding when the configured hardware
encoder is unavailable, subject to the renderer’s execution and receipt checks. CPU rendering
may take much longer and use substantial memory; adjust expected runtime rather than
weakening the verification gates.

## Thumbnails

Thumbnail generation is a separate root entry point, not an adaptive CLI stage. When the
run already contains a valid adaptive brief and verified written script,
[`generate_thumbnail.py`](../../generate_thumbnail.py) uses that episode context and records
accepted adaptive thumbnail receipts under the run’s `thumbnails` directory. It can reuse
valid matching receipts; otherwise its concept, critique, and image-generation steps may
contact browser/provider services. Review current configuration and authorization first.

```powershell
& $Python 'generate_thumbnail.py' $Run
```

The script can also process a legacy run folder; that path does not create an adaptive
episode brief. A thumbnail result is a separate asset and does not change the video’s
editorial approval or publish the episode.

## Resume, idempotence, invalidation, and recovery

The production CLI reconciles interrupted invalidation work before attempting a stage and
uses content-bound stage recipes. Re-run the same command only after checking the last
output; if the recipe and verified artifact are unchanged, the stage is adopted or skipped.
If inputs changed, the system may archive downstream activation files before creating new
ones. Keep the run directory and its `.runtime` state intact while troubleshooting.

For a safe resume:

1. Run `status` to inspect local ledger state.
2. Run `diagnose --last` to see the latest bounded failure record, if present.
3. Inspect the failed stage’s inputs, exact outputs, hashes, and relevant provider/local
   tool state.
4. Correct the actual cause, then retry the same stage. Use `--force-retry` only when a
   corrected attempt is blocked by the failure circuit.
5. Resume downstream work only after verifying the stage output and report.

```powershell
& $Python 'adaptive_production.py' status --run-dir $Run
& $Python 'adaptive_production.py' diagnose --last
```

The CLI `diagnose` is a read-only bounded local record view. It does not retry a stage,
contact a provider, or repair files. When a different diagnostic JSONL path is needed, pass
`--path PATH` with `--last`.

Interrupted generation, writing, audio adoption, source narration, rendering, and stage
invalidation use dedicated journals or receipts to recover or fail closed. Preserve the
original failure record and any rejected candidate. Do not edit hashes, reconstruct missing
receipts, or remove `.pending`/journal files to make a stage appear complete.

Retention is separate from episode-stage execution. Inspect first:

```powershell
& $Python 'adaptive_production.py' retention --runtime-dir '.runtime' --dry-run
```

Only rebuildable cache cohorts are eligible for archival. Archiving is reversible and
requires an explicit cohort identifier; restoration checks for conflicts. Retention does not
authorize deletion of run evidence, accepted or rejected media, or recovery journals.

## Configuration and resource boundaries

Configuration is not one universal file. The production CLI reads selected model, transport,
Flow count, failover, and account state from process configuration/runtime settings. For
example, `IMAGE_PLANNER_MODEL`, `IMAGE_PLANNER_TRANSPORT`, `FLOW_IMAGE_MODEL`,
`FLOW_IMAGE_COUNT`, `IMAGE_PLANNER_TIMEOUT_SECONDS`, and `FAILOVER_RETRY_LIMIT` are read by
the stage implementation. `get_config_value` reads the process environment and falls back
to code defaults. Do not assume editing an unrelated `config.txt` changes these values.

The renderer reads the repository `video_config.txt` by default, and can use a per-run
`video_config.txt` when supplied through the current review/render interface. The checked-in
configuration enables hardware encoding but configures a software fallback; its actual
availability depends on the local FFmpeg build and drivers. Read [`video_config.txt`](../../video_config.txt)
before changing resolution, frame rate, encoder, subtitle, or resource settings.

Audio and transcription use their own inputs and configuration. Review
[`transcribe_config.txt`](../../transcribe_config.txt), the profile’s configured voice and
ASR language, and the installed model settings. Provider accounts, browser state, local model
weights, OCR language data, FFmpeg binaries, Audacity, and hardware encoders are independent
prerequisites. No one `.env` file or successful offline check proves the entire system is
ready.

Adaptive production can make browser and provider requests during analysis, writing,
direction generation, plan creation, Flow image generation, and voice generation. `direct`
only accepts a supplied local response. The project may retry boundedly after a verified
quota condition, and some provider-backed stages use configured account failover. A retry
or failover can consume additional provider usage. Review current settings and explicit
authorization before starting such work.

## External REA and local reference studies

REA means the external Reverse Engineer Anything project/tool. The local reference-study APIs and procedures in this repository are separate capabilities; they are not the external REA tool, and this guide does not claim an external REA run. See [channel research](./channel-research.md) for the local reference-study entry points and their boundaries.

Reference-channel analysis is a separate research capability. The production CLI stage list
does not include a `research-channel` or `rea` stage. The study, readiness, evidence-integrity,
profile-derivation, and activation interfaces are implemented as Python APIs in the
production package. They do not imply that simply running `adaptive_production.py` will
research a channel or activate a derived profile. See [Channel research](./channel-research.md)
for its supported interface and evidence expectations.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `--run-dir is required` or run directory error | Pass an existing run directory and check the working directory/path spelling. |
| `analyze requires --channel-profile` | Select an existing profile explicitly; profile examples are listed in [Channel bundles](./channel-bundles.md). |
| Missing `raw_transcript.txt` or stale brief | Create or correct the UTF-8 source text, then rerun `analyze` with the intended channel profile. |
| `write` cannot validate the brief | Confirm `analyze` completed, source/profile inputs still match, and the brief is current. |
| TTS cannot start or voice is unavailable | Check profile voice configuration, provider/browser setup, the voice manifest, and script verification. A profile with `voice: null` needs setup. |
| Audacity does not respond | Confirm the expected Audacity installation and script-pipe setup; avoid interacting with or terminating an unrelated Audacity process. |
| Chapter stitching reports incomplete chapters | Inspect the generation manifest and all expected `voice_chapters` and `polished_chapters`; adaptive stitching requires verified polished chapters. |
| Transcription cannot find audio | Check the configured polished audio subdirectory/filename, then confirm the raw master audio fallback exists. |
| Plan or critic rejects a shot | Read the stage error and report; correct the source/brief/episode strategy or provide targeted feedback, then retry the corrected plan. |
| Visual budget exceeded | Reduce unnecessary shots or use fewer, better-targeted visuals; do not raise the budget without understanding the duration/profile limits. |
| OCR says required data is unavailable | Install/configure the required English and Arabic OCR data through the normal setup process, then revalidate the asset. |
| Visual generation fails | Preserve receipts and journals; verify the exact stage input, browser/provider availability, selected account, and existing asset identities before a bounded retry. |
| Preview or approval is stale | Re-run `report` and `preview` after fixing changed inputs, watch the new preview, and approve that exact candidate. |
| Hardware render fails | Inspect FFmpeg/driver availability and current render evidence; the software fallback can be slower and may also fail if resources are insufficient. |
| Stage says prior failure circuit opened | Diagnose the failure first. After correcting it, use `--force-retry` on that stage if required. |

When collecting a report for a maintainer, include the stage name, sanitized error message,
whether inputs changed, the relevant artifact paths and hashes, and the output of
`status`/`diagnose`. Do not share `.env` contents, cookies, private scripts, account data,
or provider session captures.

## Related references

- [Getting started](../getting-started.md): installation, dependencies, and first setup.
- [Channel bundles](./channel-bundles.md): use bundled examples or create a profile.
- [Channel research](./channel-research.md): reference evidence, study readiness, and profile activation.
- [Adaptive production CLI](../../src/youtube_automation/production/cli.py): current stage parser and implementation.
- [Adaptive production contract](../../src/youtube_automation/production/AGENTS.md): production behavior and safeguards.
