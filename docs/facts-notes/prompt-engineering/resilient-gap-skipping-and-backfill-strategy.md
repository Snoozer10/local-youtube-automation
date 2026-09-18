# Note: Resilient Gap-Skipping and Deterministic Backfill Strategy

**Category:** Prompt Engineering / Automation Reliability  
**Date Logged:** 2026-09-17  
**Relevant Code Files:** `src/youtube_automation/visuals/flow_generator.py`, `flow_image_generator.py`  
**Audit Reference:** Phase 7B Batch Generation Resilience  

### 1. Core Rule in Plain English
When executing high-volume browser-based image diffusion batches (100+ frames), transient queue latency or input timeouts must never halt the entire batch; transiently stalled frames are safely skipped while preserving the account session, and all missing frames are reconciled in a rapid, deterministic post-batch sweep using disk-existence checks.

### 2. The Failure Mode It Prevents
Halting an entire generation runner or cycling Google accounts upon a transient 45-second card-spawn delay on a single frame. Monolithic all-or-nothing architectures waste hours of execution time and burn healthy accounts unnecessarily on non-fatal web queue hiccups.

### 3. Implementation Specification
1. **Transient Error Classification**:
   ```python
   # flow_generator.py
   is_quota = check_flow_quota_or_errors(flow_page, fatal_only=True)
   if not is_quota:
       print(f"⚠️ [TRANSIENT ERROR] Frame {idx} failed after 3 attempts. Preserving active profile.")
       reset_workspace_checkpoint(run_folder)
   ```

2. **Deterministic Post-Batch Sweeping**:
   ```python
   # flow_image_generator.py / flow_generator.py
   if os.path.exists(save_path) and os.path.getsize(save_path) > 100:
       continue
   ```

### 4. Verification Check
- Assert `pipeline_manifest.json` tracks `completed_indices`.
- Re-run `flow_image_generator.py` post-batch and verify all missing frames render to 100% completion without re-rendering existing frames.
