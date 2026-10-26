"""Video processing and compilation package.

Conforms to ADR 0002 and ADR 0006 (Ports & Adapters + Deep Module).
Callers interact exclusively through VideoCompiler and compile_video.
"""

from .engine import VideoCompiler, compile_video
from .journal import (
    ClipJournalEntry,
    RenderJournal,
    compute_generation_fingerprint,
    get_file_sha256,
)
from .receipt import verification_receipt_path, verify_compilation_receipt
from .runner import (
    FakeMediaRunner,
    MediaExecutionError,
    MediaProbeResult,
    MediaRunner,
    SubprocessMediaRunner,
)
from .schema import (
    CompilationError,
    CompilationProfile,
    CompilationRequest,
    CompilationResult,
    CompilationSpan,
    CompilationTarget,
    DialogueCue,
)

__all__ = [
    "verification_receipt_path",
    "verify_compilation_receipt",
    # Core Engine Facade
    "VideoCompiler",
    "compile_video",
    # Declarative Schemas
    "CompilationRequest",
    "CompilationResult",
    "CompilationProfile",
    "CompilationSpan",
    "CompilationTarget",
    "CompilationError",
    "DialogueCue",
    # Execution Seam (Ports & Adapters)
    "MediaRunner",
    "SubprocessMediaRunner",
    "FakeMediaRunner",
    "MediaProbeResult",
    "MediaExecutionError",
    # Resumable Journal
    "ClipJournalEntry",
    "RenderJournal",
    "compute_generation_fingerprint",
    "get_file_sha256",
]
