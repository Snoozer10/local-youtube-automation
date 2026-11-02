# Channel profiles and bundles

Use a saved channel profile to give production a stable audience, narration policy and visual identity. The three profiles in `channels/` are examples you can try; they are not an installer, a required set of niches, or limits on the kinds of channels you can create.

This guide covers hand-authored profiles. To derive a profile from an offline reference-channel study, see [Channel research and external REA](./channel-research.md).

## Try the included profiles

The repository includes three example profiles:

| Profile | Example niche | Voice policy |
|---|---|---|
| [Professor Yashrah](../../channels/professor-yashrah.json) | Arabic explanations of psychology, attention, mental health and behavior | Achird |
| [Soldier's Sledger](../../channels/soldiers-ledger.json) | Military history and documentary storytelling | Charon for new synthesized narration |
| [Snoozer Anime](../../channels/snoozer-anime.json) | Egyptian Arabic anime recaps | `null`; synthesis is blocked until a voice is selected |

Treat these as starting points for trying the project. Read the profile before using it: each includes editorial choices and visual constraints that may not fit your episode. A profile does not establish that a particular episode's claims, source material, script or generated assets are accurate or acceptable.

Install the project first using the [getting started guide](../getting-started.md). Then select one profile explicitly for the run. In Adaptive staged mode, pass its saved JSON path to the `analyze --channel-profile` option; the [Adaptive staged mode guide](./adaptive-mode.md) documents the stage command. Do not rely on an implicit default: the production contract requires an explicit saved channel.

## What “channel bundle” means here

“Bundle” is a convenient name for the profile together with any configuration and assets that belong to that channel. In this repository the profile itself is a JSON file under `channels/`; some workflows may also refer to separate files. There is no separate bundle installer or package format to build. Keep episode scripts, source media and generated outputs with their run, not inside the reusable channel identity.

## Create your own profile

Make a new JSON file with a unique channel ID. Do not overwrite an included profile or reuse its ID. The JSON is UTF-8, and the root value must be an object accepted by the current `Channel` model in [`contracts.py`](../../src/youtube_automation/production/contracts.py).

The following is a small editable version-3 profile. Replace the sample editorial choices with your own channel's real audience and style. `Charon` is included as a known project profile voice; if it is not the voice you want, choose a supported voice deliberately. A voice name does not grant provider access or perform synthesis.

```json
{
  "version": 3,
  "channel_id": "weeknight-kitchen",
  "name": "Weeknight Kitchen",
  "audience": "Beginner home cooks who want reliable weeknight meals",
  "language": "English",
  "dialect": "Plain conversational English",
  "asr_language": "en",
  "voice": "Charon",
  "tone": "Warm, practical, and precise",
  "style": "Explain one cooking decision at a time, with clear steps and realistic timing.",
  "visual_directives": [
    "Show the actual ingredient, tool, or cooking action being discussed.",
    "Keep measurements and step labels readable when added as local graphics."
  ],
  "forbidden_motifs": [
    "unrelated restaurant glamour shots",
    "unsafe food handling presented as a recommended step"
  ],
  "allowed_treatments": ["subject_scene", "detail", "metaphor"]
}
```

The `Channel` model requires `channel_id`, `name`, `audience`, `language`, `dialect`, `tone`, `style` and a nonempty `allowed_treatments` list. Treatment values must come from the model's supported set: `subject_scene`, `detail`, `mechanism`, `comparison`, `timeline_map`, `metaphor` and `host`. Other model fields have defaults, but a version-2-or-newer profile must provide positive `visual_directives` and exact `forbidden_motifs`; version 3 also supports episode visual strategies. The example supplies its policy fields explicitly. Keep the channel ID unique and stable after you start using the profile: it identifies the channel across runs.

The `host` treatment additionally requires `host_mode: "CUSTOM_AVATAR"` and a nonempty `host_description`. The default host mode is `NONE`; do not add `host` to a profile without configuring its avatar identity.

### Write useful policy

- **Audience and promise:** describe the intended viewers and what they come for in plain terms.
- **Language and dialect:** say which language and variety to use. `asr_language` is the speech-recognition language code; it is separate from the human-readable `language` and `dialect` fields.
- **Tone and style:** give actionable narration guidance rather than praise words alone. State how explanations, humor, pacing or evidence should feel.
- **Voice:** use a selected voice name for new synthesis. `voice: null` means that no synthesis voice is selected and blocks AI Studio TTS. It is not a way to request narration from the original video.
- **Visual directives:** describe the channel's repeatable visual grammar and useful constraints. Keep these broad enough to work across episodes.
- **Forbidden motifs:** list concrete visual treatments to avoid. These constrain planning; they do not replace episode-level review.

An imported source narration is a separate, episode-level input identified by its source-audio receipt. It does not change the saved channel's `voice`, and a null voice does not itself prove that source audio exists. New synthesized narration and imported narration follow different paths.

Use a distinct file such as `channels/weeknight-kitchen.json`. Do not copy episode-specific claims, source URLs, selected participants or approved narration into the channel profile. If a deployed profile is versioned and active, treat that revision as immutable: edit a working copy and publish a new revision through the supported activation flow rather than silently rewriting the active revision.

## Validate the profile offline

After saving the file, run the model-backed loader from the repository root:

```powershell
.\venv\Scripts\python.exe -c "from youtube_automation.production.contracts import load_channel; channel = load_channel('channels/weeknight-kitchen.json'); print(f'Valid channel: {channel.channel_id} (schema v{channel.version})')"
```

`load_channel` reads the JSON and validates it against the current `Channel` model; it does not activate the profile, start a run, contact a provider or generate media. Run this after changing the JSON. If the project's environment cannot import `youtube_automation`, finish installation as described in the [getting started guide](../getting-started.md), then retry in that environment.

## Select and maintain it

Choose the profile explicitly when starting a production run. In Adaptive staged mode, pass the profile path using `analyze --channel-profile <profile-path>`. See the [Adaptive staged mode guide](./adaptive-mode.md) for the full command sequence. Check the run's saved profile identity before proceeding.

When channel policy needs to change:

1. Save a copy under a new unique channel ID if you intend to create a separate channel; otherwise retain the existing ID for a policy revision of that same channel.
2. Edit and validate the JSON offline.
3. Select the intended profile explicitly for a new run and inspect the saved run identity.
4. Keep already accepted episode narration and run evidence with that episode. A channel-policy edit alone is not approval to replace narration or regenerate accepted outputs.
5. For a study-derived profile managed as an immutable revision, follow the activation and recovery contract in [Reference-channel research](./channel-research.md).

## Related documentation

- [Getting started](../getting-started.md) — install and prepare the local environment.
- [Adaptive staged mode](./adaptive-mode.md) — choose the mode and run with an explicit profile.
- [Channel research and external REA](./channel-research.md) — record offline study evidence and understand the separate external REA project.
- [Channel profile contract](../../channels/AGENTS.md) — maintainer rules for saved channel identities and editorial policy.
