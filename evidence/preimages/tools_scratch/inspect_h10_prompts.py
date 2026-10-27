import json
from pathlib import Path


def main() -> None:
    p = json.loads(Path('youtube_runs/adaptive-h10-professor-dog-cues-phase2-20261005T080653Z-codex-cache-rebuild-20261007T094309Z/flow_prompts.json').read_text(encoding='utf-8'))
    for i in [0, 1]:
        shot = p[i]['adaptive_shot']
        print(f"=== Shot {i+1} ({shot['shot_id']}) ===")
        print("Subject:", shot.get('subject'))
        print("Visible state:", shot.get('visible_state'))
        print("Setting:", shot.get('setting'))
        print("Full prompt:\n", p[i]['master_setup_prompt'])
        print()

if __name__ == "__main__":
    main()
