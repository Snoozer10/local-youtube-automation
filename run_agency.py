import os
import sys
import time
import json
import subprocess
import glob
import re
from utils import get_config_value, send_telegram_notification
from playwright.sync_api import sync_playwright


def get_latest_run_folder(runs_path="youtube_runs"):
    """Finds the most recently created video folder."""
    if not os.path.exists(runs_path):
        return None
    folders = glob.glob(os.path.join(runs_path, "*/"))
    if not folders:
        return None
    return max(folders, key=os.path.getmtime)


def are_images_timestamped(run_folder):
    """Checks if images in the generated_images folder start with numbers."""
    images_dir = os.path.join(run_folder, "generated_images")
    if not os.path.exists(images_dir):
        return False
    for file in os.listdir(images_dir):
        if (file.endswith(".png") or file.endswith(".jpg")) and re.match(
            r"^\d+", file
        ):
            return True
    return False


def print_header(title):
    print("\n" + "=" * 60)
    print(f"🚀 [AGENCY NODE]: {title}")
    print("=" * 60)


def clean_browser_tabs():
    """Connects to the running CDP browser and closes all tabs to free up memory for the next phase."""
    cdp_port = get_config_value("CDP_PORT", "9222")
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(
                f"http://localhost:{cdp_port}", timeout=3000
            )
            context = browser.contexts[0]

            context.new_page()

            for page in context.pages[:-1]:
                try:
                    page.close()
                except Exception:
                    continue
            print("🧹 [SYSTEM] Cleared browser tabs for the next phase.")
    except Exception:
        pass


def get_pipeline_state(folder_path):
    """Reads the pipeline.json file from the video folder."""
    state_file = os.path.join(folder_path, "pipeline.json")
    default_state = {
        "translate": False,
        "refine": False,
        "voice": False,
        "audacity": False,
        "stitch": False,
        "transcribe": False,
        "images": False,
        "fixtimes": False,
        "video": False,
        "thumbnail": False,
    }
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                default_state.update(json.load(f))
        except Exception:
            pass
    return default_state


def save_pipeline_state(folder_path, state):
    """Saves progress back to pipeline.json."""
    state_file = os.path.join(folder_path, "pipeline.json")
    try:
        with open(state_file, "w") as f:
            json.dump(state, f, indent=4)
    except Exception:
        pass


def main():
    print_header("Initializing Fully Autonomous Media Pipeline (Batch Mode)")
    time.sleep(2)
    global_start_time = time.time()

    # 1. Run the global script generator first (Processes youtube_urls.txt)
    print_header("Phase 1: Global Script Translation & Extraction")
    try:
        subprocess.run([sys.executable, "automate_all.py"], check=True)
        clean_browser_tabs()
    except subprocess.CalledProcessError:
        print("❌ [FATAL] automate_all.py failed. Halting pipeline.")
        send_telegram_notification(
            "❌ [FATAL] automate_all.py failed. Halting pipeline."
        )
        sys.exit(1)

    # 2. Scan for all valid video folders
    runs_dir = "youtube_runs"
    if not os.path.exists(runs_dir):
        print("No youtube_runs folder found.")
        sys.exit(0)

    folders = [
        os.path.join(runs_dir, d)
        for d in os.listdir(runs_dir)
        if os.path.isdir(os.path.join(runs_dir, d))
    ]

    valid_folders = [
        f for f in folders if os.path.exists(os.path.join(f, "final_output.txt"))
    ]

    if not valid_folders:
        print("No valid video folders found to process. Exiting.")
        sys.exit(0)

    print(
        f"\n📦 Found {len(valid_folders)} video(s) to process. Initiating Batch"
        " State Machine...\n"
    )

    # 3. Process each folder
    for folder_idx, folder in enumerate(valid_folders, 1):
        video_title = os.path.basename(os.path.normpath(folder))
        print_header(
            f"Processing Video {folder_idx}/{len(valid_folders)}: {video_title}"
        )

        os.utime(folder, None)
        time.sleep(1)

        state = get_pipeline_state(folder)

        if "refine" not in state:
            state["refine"] = True

        if state.get("video", False) and state.get("thumbnail", False):
            print(
                f"✅ Video '{video_title}' is already fully compiled and"
                " processed. Skipping."
            )
            continue

        # -----------------------------------------------------------------
        # DYNAMIC PIPELINE CONFIGURATION (from .env)
        # -----------------------------------------------------------------
        enable_refine = (
            get_config_value("ENABLE_REFINE_SCRIPT", "true").strip().lower()
            in ["true", "1", "yes"]
        )
        flip_audacity = (
            get_config_value("FLIP_AUDACITY_ORDER", "false").strip().lower()
            in ["true", "1", "yes"]
        )
        whisper_engine = get_config_value(
            "WHISPER_ENGINE", "faster_whisper"
        ).strip().lower()

        img_gen_type = (
            get_config_value("IMAGE_GENERATOR_TYPE", "flow").strip().lower()
        )
        img_script = (
            "script_image_generator.py"
            if img_gen_type == "script"
            else "flow_image_generator.py"
        )
        whisper_script = (
            "transcribe_audio.py"
            if whisper_engine == "hard_whisper"
            else "faster_whisper_transcribe_audio.py"
        )

        # Construct declarative pipeline step array
        folder_steps = []

        # Step 1: Translation & Extraction
        folder_steps.append({
            "key": "translate",
            "script": "automate_all.py",
            "desc": "Phase 1: Script Extraction & Translation",
        })

        # Step 2: Script Refinement (Conditional)
        if enable_refine:
            folder_steps.append({
                "key": "refine",
                "script": "refine_script.py",
                "desc": "Phase 2: Arabic Script Refinement",
            })
        else:
            print(
                "ℹ️  [SYSTEM] Script Refinement is disabled in config."
                " Skipping Phase 2 mapping."
            )

        # Step 3: Voice Generation
        folder_steps.append({
            "key": "voice",
            "script": "generate_voice.py",
            "desc": "Phase 3: AI Voice Synthesis",
        })

        # Steps 4 & 5: Audio Polishing and Stitching
        audacity_step = {
            "key": "audacity",
            "script": "automate_audacity.py",
            "desc": "Phase 4: Studio Audio Polish",
        }
        stitch_step = {
            "key": "stitch",
            "script": "stitch_chapters.py",
            "desc": "Phase 5: Audio Stitching",
        }

        if flip_audacity:
            folder_steps.extend([stitch_step, audacity_step])
        else:
            folder_steps.extend([audacity_step, stitch_step])

        # Step 6 to 10: Finalizing Pipeline
        folder_steps.extend([
            {
                "key": "transcribe",
                "script": whisper_script,
                "desc": (
                    f"Phase 6: Whisper Transcription ({whisper_engine.upper()})"
                ),
            },
            {
                "key": "images",
                "script": img_script,
                "desc": f"Phase 7: Image Generation ({img_gen_type.upper()})",
            },
            {
                "key": "fixtimes",
                "script": "fix_timestamps.py",
                "desc": "Phase 8: Timestamp Alignment Checking",
            },
            {
                "key": "video",
                "script": "compile_video.py",
                "desc": "Phase 9: Final Video Compositing & Rendering",
            },
            {
                "key": "thumbnail",
                "script": "generate_thumbnail.py",
                "desc": "Phase 10: Youtube Thumbnail Optimization",
            },
        ])

        folder_failed = False

        for step in folder_steps:
            if state.get(step["key"], False):
                print(f"⏭️  [SKIP] {step['desc']} already completed.")
                continue

            if (
                step["script"] == "fix_timestamps.py"
                and are_images_timestamped(folder)
            ):
                print(
                    f"⏭️  [SKIP] {step['desc']}: Generated image assets are"
                    " already sorted by timeline layout on disk."
                )
                state[step["key"]] = True
                save_pipeline_state(folder, state)
                continue

            print(f"\n⏳ [RUNNING] {step['desc']} ({step['script']})...")
            try:
                if step["script"] == "compile_video.py":
                    subprocess.run(
                        [sys.executable, step["script"], folder],
                        check=True,
                        timeout=3600,
                    )
                else:
                    subprocess.run([sys.executable, step["script"]], check=True)

                state[step["key"]] = True
                save_pipeline_state(folder, state)
                clean_browser_tabs()

                notify_per_step = (
                    get_config_value("TELEGRAM_NOTIFY_PER_STEP", "false")
                    .strip()
                    .lower()
                    in ["true", "1", "yes"]
                )
                if notify_per_step:
                    send_telegram_notification(
                        f"✅ [Step Completed]\n"
                        f"Video: {video_title}\n"
                        f"Completed: {step['desc']}"
                    )
                time.sleep(2)

            except subprocess.CalledProcessError as err:
                error_msg = (
                    f"❌ [PIPELINE CRASH]\n"
                    f"Video: {video_title}\n"
                    f"Failed At: {step['desc']} ({step['script']})\n"
                    f"Status Code: {err.returncode}"
                )
                print(f"\n{error_msg}")
                send_telegram_notification(error_msg)
                folder_failed = True
                break

            except subprocess.TimeoutExpired:
                timeout_msg = (
                    f"⚠️ [TIMEOUT EXPIRED]\n"
                    f"Video: {video_title}\n"
                    f"Step: {step['desc']} timed out."
                )
                print(f"\n{timeout_msg}")
                send_telegram_notification(timeout_msg)
                folder_failed = True
                break

            except KeyboardInterrupt:
                cancel_msg = (
                    f"🛑 [USER INTERRUPTION]\n"
                    f"Video: {video_title}\n"
                    f"Pipeline aborted during step: {step['desc']}"
                )
                print(f"\n{cancel_msg}")
                send_telegram_notification(cancel_msg)
                raise

        if folder_failed:
            continue

    elapsed = time.time() - global_start_time
    hours, rem = divmod(elapsed, 3600)
    minutes, seconds = divmod(rem, 60)
    print("\n" + "=" * 60)
    print(
        f"🎉 BATCH PIPELINE FINISHED! Total Time:"
        f" {int(hours):02d}h:{int(minutes):02d}m:{int(seconds):02d}s"
    )
    print("=" * 60)
    send_telegram_notification(
        "🏁 [Batch Complete]\nAll assigned videos have been processed!\nTotal"
        f" Time: {int(hours):02d}h:{int(minutes):02d}m:{int(seconds):02d}s"
    )


if __name__ == "__main__":
    main()