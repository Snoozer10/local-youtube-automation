# Channel and Episode Planning

This context covers reusable channel identity and the visual direction of an individual YouTube episode.

## Language

**Production mode**:
The pipeline entrypoint and execution pattern selected for a production job. Legacy batch mode supervises queued URL/run processing; Adaptive staged mode executes explicit content-bound stages for one selected run and channel.

**Workflow**:
The ordered preparation, execution, review and recovery steps followed within a production mode. A mode identifies the execution pattern; its workflow describes how to use it.

**Channel bundle**:
A user's reusable channel profile together with related configuration and assets. This is an organizational term, not a separate package or installer format. Hand-authored Channel JSON and an activated study-derived profile directory are distinct supported profile sources.

**REA**:
The external Reverse Engineer Anything project, whose passive browser observations can supply evidence where separately qualified. It is not a synonym for this repository's reference-channel study APIs or a built-in semantic YouTube-channel analyzer. See [channel research and external REA](docs/usage/channel-research.md).

**Channel DNA**:
A reusable, versioned profile of a channel's identity, audience, editorial voice, visual language, and constraints. It distinguishes observed evidence, inferred traits, and owner preferences, and is separate from any single episode's visual strategy.
_Avoid_: Episode visual strategy

**Reference-channel study**:
An evidence-backed description of a reference channel used for analysis, distinct from the target channel’s reusable production profile. Reference observations and their evidence remain intact; direct observations, inferences, and unknowns stay distinct. Owner language, voice, and brand preferences govern the derived production profile and never rewrite reference observations.

**Candidate pool**:
The eligible channel uploads considered for selection within a reference-channel study's declared format, language, and period. Candidate-pool membership is distinct from inclusion in the study sample.

**Study sample**:
The distinct video examples selected from a candidate pool for a reference-channel study. Each example retains its selection reason and source mapping; multiple evidence files for one video remain one example.

**Partial study**:
A reference-channel study with missing, invalid, or unresolved required evidence or core traits. Its retained work includes the gaps and next action.

**Core-ready study**:
A reference-channel study that meets the required evidence contract for every core trait. Optional gaps may remain, and production-profile activation has separate requirements.

**Episode visual strategy**:
The content-specific visual direction for one episode, connecting its source and narrative beats to a visual palette, pacing, and constraints while preserving the reusable channel identity.
_Avoid_: Channel DNA

For timeline and synchronization vocabulary not covered here, see [CONTEXT.md](./CONTEXT.md).
