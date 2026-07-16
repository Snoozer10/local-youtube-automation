import os, sys, shutil, subprocess, tempfile

ROOT = r"C:\Users\Snoozer\Downloads\Antigravity\Youtube Automation 2\buckup\Version 4 before deepseek implementation plan\image_generation"
sys.path.insert(0, ROOT)
import compile_video

SRC = os.path.join(ROOT, "youtube_runs", "Everyday Habits That Boost Brain Power", "generated_images")

work = tempfile.mkdtemp()
print("work:", work)
# Copy video_config.txt and force legacy + CPU
shutil.copy(os.path.join(ROOT, "video_config.txt"), os.path.join(work, "video_config.txt"))
cfg_text = open(os.path.join(work, "video_config.txt"), encoding="utf-8").read()
cfg_text = cfg_text.replace("ENABLE_SINGLE_PASS=true", "ENABLE_SINGLE_PASS=false")
cfg_text = cfg_text.replace("ENCODER_FORCE=", "ENCODER_FORCE=libx264")
open(os.path.join(work, "video_config.txt"), "w", encoding="utf-8").write(cfg_text)

# Mini run folder (images live in generated_images/ like the real pipeline)
run = os.path.join(work, "run1")
os.makedirs(os.path.join(run, "generated_images"))
for n in ["00_00.png", "00_08.png", "00_17.png"]:
    shutil.copy(os.path.join(SRC, n), os.path.join(run, "generated_images", n))
subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                "-ac", "1", "-ar", "48000", os.path.join(run, "full_episode_voice.wav")], check=True)
with open(os.path.join(run, "timestamped_transcript.txt"), "w", encoding="utf-8") as f:
    f.write("[00:00] a\n[00:02] b\n[00:04] c\n")
with open(os.path.join(run, "timestamped_transcript.srt"), "w", encoding="utf-8") as f:
    f.write("1\n00:00:00,000 --> 00:00:02,000\nسطر\n\n2\n00:00:02,000 --> 00:00:04,000\nسطر\n\n3\n00:00:04,000 --> 00:00:06,000\nسطر\n")

prev = os.getcwd()
os.chdir(work)
try:
    compile_video.main(run_folder=run)
finally:
    os.chdir(prev)

out = os.path.join(run, "youtube_ready_video.mp4")
if os.path.exists(out):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,codec_name,width,height",
                        "-of", "default=noprint_wrappers=1", out],
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    print("PROBE:\n", p.stdout)
    print("LEGACY OUTPUT OK size", os.path.getsize(out))
    # Verify checkpoint cleaned up
    cp = os.path.join(run, "compile_checkpoint.json")
    print("checkpoint exists after success:", os.path.exists(cp))
else:
    print("NO OUTPUT - legacy failed")

shutil.rmtree(work, ignore_errors=True)
print("cleaned")
