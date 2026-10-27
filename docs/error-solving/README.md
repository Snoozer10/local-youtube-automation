# Error-Solving Case Register & Index

Welcome to the structured error knowledge base for the local YouTube automation architecture.

## Investigator Quick Links
- **Scoped Guidelines**: [`AGENTS.md`](AGENTS.md)
- **New Case Template**: [`TEMPLATE.md`](TEMPLATE.md)
- **Legacy Register Archive**: [`understood-errors.md`](understood-errors.md) *(Historical SHA-256: `73e0486215fc176f581acfc1832c61ec2b0939f7b505bc45a689762defd8dc39`)*

---

## Active & Migrated Cases

| Case ID | Responsible Layer | Title / Symptom | Status | Case File |
| :--- | :--- | :--- | :--- | :--- |
| **ERR-001** | `os.filesystem` | Windows Explorer Long Path Video Playback Failure (-2147219196) | resolved | [`ERR-001-win-long-path.md`](cases/ERR-001-win-long-path.md) |
| **ERR-002** | `video.qsv` | Intel QSV Lookahead Stream Corruption | resolved | [`ERR-002-qsv-lookahead.md`](cases/ERR-002-qsv-lookahead.md) |
| **ERR-003** | `audio.pipe` | Audacity Named Pipe Leading Newline Protocol Framing Desynchronization | resolved | [`ERR-003-audacity-pipe-desync.md`](cases/ERR-003-audacity-pipe-desync.md) |
| **ERR-004** | `speech.manifest` | Whisper Spoken Manifest Fallback and Ghost Word Extrapolation Drift | resolved | [`ERR-004-whisper-manifest-fallback.md`](cases/ERR-004-whisper-manifest-fallback.md) |
| **ERR-005** | `browser.gemini` | Gemini Thinking Indicator Substring False-Positive | resolved | [`ERR-005-gemini-thinking-selector.md`](cases/ERR-005-gemini-thinking-selector.md) |

---

## Failure Domains & Responsible Layers

- **`os.filesystem`**: Path length limitations, Unicode filenames, read-only permissions, and sparse checkouts.
- **`video.qsv`**: Intel QuickSync hardware transcoding, pixel format negotiation (`nv12`), and lookahead controls.
- **`audio.pipe`**: Audacity `mod-script-pipe` IPC protocol, newline framing, and process ownership.
- **`speech.manifest`**: Audio manifest authority, Whisper alignment, and subtitle/paragraph synchronization.
- **`browser.gemini`**: Gemini web SPA hydration, generation indicator detection, and model selection.
- **`pipeline.gate`**: Production budget gates, visual audits, and OCR text collision gates.

---

## Legacy Headings Resolution Map

Historical anchors in [`understood-errors.md`](understood-errors.md) remain valid and resolve directly to their original positions:

| Legacy Heading | Mapped Case / Anchor |
| :--- | :--- |
| `Windows Explorer Long Path Video Playback Failure` | [`ERR-001-win-long-path.md`](cases/ERR-001-win-long-path.md) / [Legacy Anchor](understood-errors.md#windows-explorer-long-path-video-playback-failure-file-system-error--2147219196) |
| `QSV Lookahead Stream Corruption` | [`ERR-002-qsv-lookahead.md`](cases/ERR-002-qsv-lookahead.md) / [Legacy Anchor](understood-errors.md#qsv-lookahead-stream-corruption) |
| `Audacity Named Pipe Leading Newline Protocol Framing Desynchronization` | [`ERR-003-audacity-pipe-desync.md`](cases/ERR-003-audacity-pipe-desync.md) / [Legacy Anchor](understood-errors.md#audacity-named-pipe-leading-newline-protocol-framing-desynchronization) |
| `Whisper Spoken Manifest Fallback and Ghost Word Extrapolation Drift` | [`ERR-004-whisper-manifest-fallback.md`](cases/ERR-004-whisper-manifest-fallback.md) / [Legacy Anchor](understood-errors.md#whisper-spoken-manifest-fallback-and-ghost-word-extrapolation-drift) |
| `Gemini Thinking Indicator Substring False-Positive` | [`ERR-005-gemini-thinking-selector.md`](cases/ERR-005-gemini-thinking-selector.md) / [Legacy Anchor](understood-errors.md#gemini-thinking-indicator-substring-false-positive) |
| All Other Headings (61 items) | Retained in [`understood-errors.md`](understood-errors.md) |
