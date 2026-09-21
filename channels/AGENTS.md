# Purpose
- Saved channel identities and editorial policy for adaptive production.

# Ownership
- Each JSON profile defines stable audience, narration and visual constraints; episode scripts and generated media belong in separate run directories.

# Local Contracts
- Select a profile explicitly before analysis. A script cannot alter channel identity or allowed treatments.
- `voice: null` means no synthesis voice has been selected. It must block AI Studio synthesis, while a verified source-audio receipt identifies an imported narration episode.
- Channel styles describe visual grammar, not a fixed episode topic. Claims, historical details and depicted characters still require episode-level review.

# Work Guidance
- Keep Professor Yashrah on Achird until the user changes that choice. Prefer a coherent illustrated documentary system over the legacy curly-haired mascot.
- Soldier's Sledger and Snoozer Anime source-audio pilots keep their published narration; select a real TTS voice before synthesizing new episodes.

# Verification
- Validate every profile with `load_channel` and check its selected pilot brief hash before downstream work.

# Child DOX Index
- None.
