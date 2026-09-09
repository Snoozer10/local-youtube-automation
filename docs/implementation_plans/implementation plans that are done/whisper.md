### The Architect's Adjustment
We will still execute the plan, but with **surgical hardware optimizations**:
1.  **Lower Beam Size:** I will reduce the beam search from `5` to `3`. This still gives you a massive accuracy boost over standard Whisper, but fits comfortably inside your 2GB VRAM limit.
2.  **Word-Level Extraction Algorithm:** I will write a custom Python loop that pulls the word-level data from Whisper and dynamically groups them into punchy, 5-to-6 word YouTube-style caption blocks.

---

### The Implementation Plan

**Objective:** Upgrade `transcribe_audio.py` to output highly accurate, fast-paced YouTube-style short captions, optimized for a 2GB VRAM GPU.

1.  **Update Transcription Call:** Add `word_timestamps=True` and `beam_size=3` to the `model.transcribe()` function.
2.  **Flatten Word Data:** Extract the raw word dictionaries from the Whisper segments into a single continuous list.
3.  **Dynamic Chunking Engine:** Loop through the words and build a sentence. Force the sentence to break (creating a new SRT timestamp line) if:
    *   The chunk hits **6 words**.
    *   The word ends with a punctuation mark (`.`, `!`, `؟`, `,`).
    *   There is a silence gap larger than **0.5 seconds** before the next word.
4.  **Absolute Math:** Calculate the correct start and end times for each micro-chunk and push it to the `.srt` and `.txt` files.

---

### The Code Block for `transcribe_audio.py`

Open `transcribe_audio.py`. Locate the **Step 4 processing loop** (around line 96), specifically the `try:` block where `result = model.transcribe(...)` happens. 

**Replace the entire `try...except` block with this optimized chunking architecture:**

```python
        # Transcribe the single chapter audio file
        try:
            # OPTIMIZATION: beam_size=3 boosts accuracy without crashing 2GB VRAM. word_timestamps enables micro-captions.
            result = model.transcribe(
                path, 
                language="ar", 
                fp16=use_fp16, 
                initial_prompt=egyptian_arabic_prompt,
                word_timestamps=True,
                beam_size=3 
            )
            
            segments = result.get("segments", [])
            
            # Extract all words across all segments into a single flat list
            all_words = []
            for segment in segments:
                for word_info in segment.get("words", []):
                    all_words.append(word_info)
                    
            if not all_words:
                # Fallback if audio is completely silent or failed to generate words
                text_content = result.get("text", "").strip() or "..."
                absolute_start = current_time_offset
                absolute_end = current_time_offset + duration
                
                output_text_lines.append(f"{format_timestamp(absolute_start)} {text_content}")
                output_srt_lines.extend([
                    str(srt_index),
                    f"{format_srt_timestamp(absolute_start)} --> {format_srt_timestamp(absolute_end)}",
                    text_content,
                    ""
                ])
                srt_index += 1
            else:
                # DYNAMIC YOUTUBE CHUNKING ENGINE
                current_chunk_words = []
                chunk_start_time = None
                
                for i, word_obj in enumerate(all_words):
                    word_text = word_obj.get("word", "").strip()
                    w_start = word_obj.get("start", 0.0)
                    w_end = word_obj.get("end", duration)
                    
                    if not word_text:
                        continue
                        
                    if chunk_start_time is None:
                        chunk_start_time = w_start
                        
                    current_chunk_words.append(word_text)
                    
                    # 1. Check conditions to force a line break (Chunking Rules)
                    is_last_word = (i == len(all_words) - 1)
                    has_punctuation = any(p in word_text for p in ['.', '!', '؟', '،', ','])
                    max_words_reached = len(current_chunk_words) >= 6 # Max 6 words per screen for YouTube Shorts style
                    
                    # 2. Check silence gap to the next word
                    next_word_gap = 0.0
                    if not is_last_word:
                        next_word_start = all_words[i+1].get("start", w_end)
                        next_word_gap = next_word_start - w_end
                    
                    # 3. Apply break if any condition is met
                    if is_last_word or has_punctuation or max_words_reached or next_word_gap > 0.5:
                        chunk_text = " ".join(current_chunk_words).strip()
                        chunk_end_time = w_end
                        
                        # Calculate absolute locations in the master track
                        absolute_start = current_time_offset + chunk_start_time
                        absolute_end = current_time_offset + chunk_end_time
                        
                        # Console output
                        formatted_line = f"{format_timestamp(absolute_start)} {chunk_text}"
                        print(formatted_line)
                        output_text_lines.append(formatted_line)
                        
                        # SRT appending
                        output_srt_lines.extend([
                            str(srt_index),
                            f"{format_srt_timestamp(absolute_start)} --> {format_srt_timestamp(absolute_end)}",
                            chunk_text,
                            ""
                        ])
                        srt_index += 1
                        
                        # Reset for next chunk
                        current_chunk_words = []
                        chunk_start_time = None

        except Exception as e:
            print(f"Error transcribing {path}: {e}")
            # If the GPU crashed from VRAM limits, catch it gracefully
            if "OutOfMemoryError" in str(e) or "CUDA out of memory" in str(e):
                print("\n[HARDWARE WARNING] Your GeForce 840M ran out of VRAM!")
                print("To fix: Open voice_option_notes.txt and change Whisper Model from 'small' to 'base'.")
                sys.exit(1)
                
            formatted_line = f"{format_timestamp(current_time_offset)} [Chapter {chapter_num} transcription failed]"
            print(formatted_line)
            output_text_lines.append(formatted_line)
```

### Important Hardware Note:
When you run this, watch your console. If Whisper still crashes and prints the **`[HARDWARE WARNING]`** I wrote into the `except` block, it means the 2GB VRAM is just slightly too small. If that happens, simply open your `voice_option_notes.txt`, change `Whisper Model: small` to `Whisper Model: base`, and run it again. 

Apply these changes and let me know how perfectly those new YouTube-style captions look!