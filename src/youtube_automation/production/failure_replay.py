"""Sanitized, offline replay cases for adaptive semantic-planner failures."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError, model_validator

from .contracts import Brief, Contract, Digest, Identifier, Text, VisualMode, fingerprint
from .shots import (
    SEMANTIC_PLANNER_VERSION,
    SHOT_COMPILER_VERSION,
    NarrationUnit,
    SemanticGraphic,
    SemanticIssue,
    SemanticPlanError,
    SemanticRepairContent,
    SemanticShotBatch,
    SemanticShotIntent,
    Shot,
    ShotPlan,
    _compile_semantic_batch,
    _exact_semantic_repair_batch_model,
    resolve_editorial_policy,
    validate_plan,
)


class SanitizedSemanticIntent(Contract):
    """Small, provider-text-free semantic record used only by replay fixtures."""

    beat_id: Identifier
    first_unit_id: Identifier
    last_unit_id: Identifier | None = None
    visual_mode: VisualMode
    beat_kind: Literal[
        "claim", "question", "example", "contrast", "mechanism", "instruction", "reveal", "transition"
    ]
    framing: Literal[
        "establishing", "wide", "medium", "close_up", "insert", "overhead", "diagram"
    ]
    graphic_template: Literal[
        "kinetic_type", "comparison", "focus_sweep", "schulte_challenge"
    ] | None = None
    semantic_link: Literal[
        "direct", "causal", "example", "contrast", "mechanism", "instruction", "metaphor", "transition"
    ] = "direct"
    viewer_takeaway: Text | None = None
    subject: Text | None = None
    visible_state: Text | None = None
    setting: Text | None = None
    composition: Text | None = None
    entity_ids: list[Identifier] | None = None
    continuity: Literal["new", "reuse", "edit"] = "new"
    reference_id: Identifier | None = None

    def to_semantic_intent(self) -> SemanticShotIntent:
        unit_suffix = self.first_unit_id.removeprefix("u").replace("_", "-")
        substrate = self.graphic_template is not None
        default_entity_id = f"{'canvas' if substrate else 'object'}_{unit_suffix}"
        entity_ids = self.entity_ids or [default_entity_id]
        graphic: SemanticGraphic | None = None
        if self.graphic_template is not None:
            graphic = SemanticGraphic(
                template=self.graphic_template,
                primary_text=f"Visible instruction for {self.beat_id}",
                secondary_text=(
                    "Second comparison state"
                    if self.graphic_template == "comparison"
                    else "Start"
                    if self.graphic_template == "schulte_challenge"
                    else ""
                ),
                timer_text="00:00" if self.graphic_template == "schulte_challenge" else "",
            )
        return SemanticShotIntent(
            beat_id=self.beat_id,
            first_unit_id=self.first_unit_id,
            last_unit_id=self.last_unit_id or self.first_unit_id,
            visual_mode=self.visual_mode,
            beat_kind=self.beat_kind,
            semantic_link=self.semantic_link,
            viewer_takeaway=self.viewer_takeaway or f"Sanitized takeaway for {self.beat_id}",
            subject=self.subject or f"A visible {default_entity_id.replace('_', ' ')}",
            visible_state=(
                self.visible_state
                or f"The {default_entity_id.replace('_', ' ')} shows one stable state"
            ),
            setting=(
                self.setting
                or ("A grounded room" if not substrate else "A clean uncluttered studio backdrop")
            ),
            framing=self.framing,
            composition=self.composition or f"Distinct composition for {self.beat_id} at {unit_suffix}",
            entity_ids=entity_ids,
            continuity=self.continuity,
            reference_id=self.reference_id,
            graphic=graphic,
        )

    def to_repair_content(self) -> SemanticRepairContent:
        payload = self.to_semantic_intent().model_dump(
            mode="python",
            exclude={"beat_id", "first_unit_id", "last_unit_id"},
        )
        return SemanticRepairContent.model_validate(payload)


class SanitizedSemanticBatch(Contract):
    shots: list[SanitizedSemanticIntent] = Field(min_length=1, max_length=40)

    def to_semantic_batch(self) -> SemanticShotBatch:
        return SemanticShotBatch(
            shots=[intent.to_semantic_intent() for intent in self.shots]
        )


class SemanticFailureCheckpoint(Contract):
    """Minimal accepted semantic history needed to reproduce a later failure."""

    planner_version: int = Field(ge=1)
    compiler_version: int = Field(ge=1)
    windows: list[tuple[int, int]] = Field(min_length=1)
    next_window: int = Field(ge=0)
    units_by_window: list[list[NarrationUnit]]
    batches: list[SanitizedSemanticBatch]

    @model_validator(mode="after")
    def aligned_history(self) -> SemanticFailureCheckpoint:
        if self.next_window != len(self.batches):
            raise ValueError("Failure checkpoint next_window must equal its accepted batch count")
        if len(self.units_by_window) != len(self.batches):
            raise ValueError("Failure checkpoint requires narration units for every accepted batch")
        if self.next_window >= len(self.windows):
            raise ValueError("Failure checkpoint must retain the failed planning window")
        return self


class SanitizedRepairContract(Contract):
    """Cardinality and episode-palette evidence without provider response text."""

    required_count: int = Field(ge=1, le=40)
    candidate_contents: list[SanitizedSemanticIntent]
    corrected_contents: list[SanitizedSemanticIntent]

    @model_validator(mode="after")
    def corrected_cardinality(self) -> SanitizedRepairContract:
        if len(self.corrected_contents) != self.required_count:
            raise ValueError("Corrected repair contents must match required_count")
        return self


class SemanticFailureCase(Contract):
    """Versioned, sanitized evidence for one distinct semantic failure boundary."""

    version: Literal[1] = 1
    case_id: Identifier
    title: Text
    failure_code: Identifier
    root_cause_class: Literal[
        "transport",
        "schema",
        "model_semantics",
        "deterministic_timing",
        "deterministic_topology",
        "deterministic_entity",
        "editorial",
    ]
    responsible_layer: Literal[
        "browser_transport",
        "request_contract",
        "semantic_repair",
        "python_compiler",
        "editorial_review",
    ]
    stage: Literal["plan"] = "plan"
    window_index: int = Field(ge=0)
    raw_evidence_sha256s: list[Digest] = Field(min_length=1)
    input_sha256: Digest
    candidate_sha256: Digest
    brief: Brief
    timeline: dict[str, Any]
    checkpoint: SemanticFailureCheckpoint
    failed_units: list[NarrationUnit] = Field(min_length=1)
    replay_kind: Literal["semantic_candidate", "repair_contract"] = "semantic_candidate"
    failed_candidate: SanitizedSemanticBatch | None = None
    corrected_candidate: SanitizedSemanticBatch | None = None
    repair_contract: SanitizedRepairContract | None = None
    expected_boundary: Literal["request_contract", "semantic_compiler", "final_validator"]
    expected_issue: SemanticIssue
    expected_corrected_behavior: Text

    @model_validator(mode="after")
    def aligned_failure(self) -> SemanticFailureCase:
        if self.window_index != self.checkpoint.next_window:
            raise ValueError("Failure case window must follow its accepted checkpoint")
        if self.failure_code != self.expected_issue.code:
            raise ValueError("Failure code must match the expected semantic issue")
        if self.replay_kind == "semantic_candidate" and self.failed_candidate is None:
            raise ValueError("Semantic replay cases require failed_candidate")
        if self.replay_kind == "repair_contract" and self.repair_contract is None:
            raise ValueError("Request-contract replay cases require repair_contract")
        return self


class SemanticFailureReplayResult(Contract):
    case_id: Identifier
    checkpoint_batches: int = Field(ge=0)
    checkpoint_shots: int = Field(ge=0)
    observed_boundary: Literal[
        "accepted", "request_contract", "semantic_compiler", "final_validator"
    ]
    issues: list[SemanticIssue]
    corrected_boundary: Literal[
        "not_provided", "accepted", "request_contract", "semantic_compiler", "final_validator"
    ] = "not_provided"
    late_validator_escape: str | None = None


class SemanticFailureCorpusReport(Contract):
    case_ids: list[Identifier]
    observed_boundaries: dict[str, str]
    accepted_checkpoint_batches: int = Field(ge=0)
    repeated_failure_codes: dict[str, int]
    late_validator_escapes: list[Identifier]
    ready: bool


class FailureOwnershipRule(Contract):
    category: Literal[
        "provider_transport",
        "request_schema",
        "model_semantics",
        "deterministic_compiler",
        "aesthetic_review",
    ]
    responsible_layer: Literal[
        "browser_transport",
        "request_contract",
        "semantic_repair",
        "python_compiler",
        "editorial_review",
    ]
    code_prefixes: list[str] = Field(min_length=1)
    action: Text


FAILURE_OWNERSHIP_TAXONOMY = (
    FailureOwnershipRule(
        category="provider_transport",
        responsible_layer="browser_transport",
        code_prefixes=["PROVIDER_", "TRANSPORT_", "QUOTA_"],
        action="Preserve the receipt, recover or fail over, and retry the exact request.",
    ),
    FailureOwnershipRule(
        category="request_schema",
        responsible_layer="request_contract",
        code_prefixes=["REQUEST_CONTRACT_", "SCHEMA_"],
        action="Reject before semantic compilation with the exact current response schema.",
    ),
    FailureOwnershipRule(
        category="model_semantics",
        responsible_layer="semantic_repair",
        code_prefixes=["MODEL_SEMANTIC_"],
        action="Repair only the addressable model-authored semantic record.",
    ),
    FailureOwnershipRule(
        category="deterministic_compiler",
        responsible_layer="python_compiler",
        code_prefixes=["SEMANTIC_", "NARRATION_EVENT_", "HOOK_", "COVERAGE_"],
        action="Compute from local canonical inputs and return beat-addressable issues.",
    ),
    FailureOwnershipRule(
        category="aesthetic_review",
        responsible_layer="editorial_review",
        code_prefixes=["EDITORIAL_", "AESTHETIC_"],
        action="Leave judgment to the critic and explicit human approval.",
    ),
)


def failure_ownership_for_code(code: str) -> FailureOwnershipRule:
    """Resolve one stable failure code to its narrowest responsible layer."""
    for rule in FAILURE_OWNERSHIP_TAXONOMY:
        if any(code.startswith(prefix) for prefix in rule.code_prefixes):
            return rule
    raise ValueError(f"Failure code has no ownership rule: {code}")


class ValidatorBoundaryAuditEntry(Contract):
    rule_group: Identifier
    responsibility: Literal[
        "input_contract", "request_contract", "semantic_compiler", "editorial_review"
    ]
    stable_codes: list[Identifier] = Field(min_length=1)
    deterministic: bool
    addressable: bool


class ValidatorBoundaryAudit(Contract):
    entries: list[ValidatorBoundaryAuditEntry]
    late_validator_rule_groups: list[Identifier]
    ready: bool


def semantic_validator_audit() -> ValidatorBoundaryAudit:
    """Return the maintained ownership audit for every final-plan rule family."""
    entries = [
        ValidatorBoundaryAuditEntry(
            rule_group="input_lineage_and_timing",
            responsibility="input_contract",
            stable_codes=["INPUT_LINEAGE_INVALID", "CANONICAL_TIMING_INVALID"],
            deterministic=True,
            addressable=False,
        ),
        ValidatorBoundaryAuditEntry(
            rule_group="compiled_shot_schema",
            responsibility="request_contract",
            stable_codes=["REQUEST_CONTRACT_INVALID", "COMPILED_SHOT_INVALID"],
            deterministic=True,
            addressable=False,
        ),
        ValidatorBoundaryAuditEntry(
            rule_group="semantic_record_rules",
            responsibility="semantic_compiler",
            stable_codes=["SEMANTIC_RECORD_INVALID"],
            deterministic=True,
            addressable=True,
        ),
        ValidatorBoundaryAuditEntry(
            rule_group="prefix_and_episode_budgets",
            responsibility="semantic_compiler",
            stable_codes=[
                "SEMANTIC_PREFIX_REPETITION",
                "SEMANTIC_SCENE_REPETITION",
                "SEMANTIC_VISUAL_FAMILY_REPETITION",
                "SEMANTIC_FRAMING_DIVERSITY",
            ],
            deterministic=True,
            addressable=True,
        ),
        ValidatorBoundaryAuditEntry(
            rule_group="narration_bound_events",
            responsibility="semantic_compiler",
            stable_codes=["NARRATION_EVENT_TOPOLOGY", "NARRATION_EVENT_REQUIRED"],
            deterministic=True,
            addressable=True,
        ),
        ValidatorBoundaryAuditEntry(
            rule_group="aesthetic_judgment",
            responsibility="editorial_review",
            stable_codes=["EDITORIAL_REJECTED"],
            deterministic=False,
            addressable=True,
        ),
    ]
    late = [
        entry.rule_group
        for entry in entries
        if entry.deterministic and entry.responsibility == "editorial_review"
    ]
    return ValidatorBoundaryAudit(
        entries=entries,
        late_validator_rule_groups=late,
        ready=not late,
    )


class SanitizedLiveRunEvidence(Contract):
    run_id: Identifier
    planner_version: int = Field(ge=1)
    compiler_version: int = Field(ge=1)
    stage_recipe_sha256: Digest
    live_attempts: int = Field(ge=0)
    accepted_windows: int = Field(ge=0)
    checkpoint_windows: int = Field(ge=0)
    total_windows: int = Field(ge=1)
    checkpoint_shots: int = Field(ge=0)
    repair_count: int = Field(ge=0)
    provider_refusals: int = Field(ge=0)
    quota_switches: int = Field(ge=0)
    evidence_sha256s: list[Digest] = Field(min_length=1)
    latest: bool = False


class SanitizedLiveRunLedger(Contract):
    version: Literal[2] = 2
    runs: list[SanitizedLiveRunEvidence] = Field(min_length=1)

    @model_validator(mode="after")
    def one_latest_run(self) -> SanitizedLiveRunLedger:
        if sum(run.latest for run in self.runs) != 1:
            raise ValueError("Failure intelligence evidence requires exactly one latest run")
        return self


class FailureIntelligenceReport(Contract):
    live_runs: int = Field(ge=0)
    live_attempts: int = Field(ge=0)
    accepted_windows: int = Field(ge=0)
    live_attempts_per_accepted_window: float | None
    repair_count: int = Field(ge=0)
    provider_refusals: int = Field(ge=0)
    quota_switches: int = Field(ge=0)
    checkpoint_progress: Text
    repeated_failure_codes: dict[str, int]
    late_validator_escapes: list[Identifier]
    validator_audit_ready: bool
    replay_corpus_ready: bool
    next_planner_version: int = Field(ge=1)
    next_compiler_version: int = Field(ge=1)
    bounded_live_requests_allowed: Literal[0, 1]
    ready_for_one_bounded_live_request: bool


def _input_fingerprint(case: SemanticFailureCase) -> str:
    return fingerprint(
        {
            "brief": case.brief.model_dump(mode="json"),
            "timeline": case.timeline,
            "checkpoint": case.checkpoint.model_dump(mode="json"),
        }
    )


def load_semantic_failure_case(path: str | Path) -> SemanticFailureCase:
    """Load one committed fixture and verify its content-addressed inputs."""
    case = SemanticFailureCase.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )
    if case.input_sha256 != _input_fingerprint(case):
        raise ValueError(f"Failure case input hash mismatch: {case.case_id}")
    candidate = (
        case.failed_candidate
        if case.replay_kind == "semantic_candidate"
        else case.repair_contract
    )
    if candidate is None:
        raise ValueError(f"Failure case has no replay candidate: {case.case_id}")
    if case.candidate_sha256 != fingerprint(candidate):
        raise ValueError(f"Failure case candidate hash mismatch: {case.case_id}")
    return case


def _validate_compiled_prefix(
    shots: list[Shot], case: SemanticFailureCase
) -> str | None:
    if not shots:
        return None
    partial = ShotPlan(
        version=3,
        shots=shots,
        brief_sha256=fingerprint(case.brief),
        timeline_sha256=fingerprint(case.timeline),
        fps=int(case.timeline["fps"]),
        total_frames=shots[-1].end_frame,
        editorial_policy=resolve_editorial_policy(case.brief),
    )
    shadow = partial.model_copy(update={"total_frames": int(case.timeline["total_frames"])})
    try:
        validate_plan(
            shadow,
            case.timeline,
            case.brief,
            editorial_complete=shots[-1].end_frame == case.timeline["total_frames"],
        )
    except ValueError as exc:
        return str(exc)
    return None


def _replay_repair_contract(
    case: SemanticFailureCase,
) -> tuple[
    Literal["accepted", "request_contract"],
    list[SemanticIssue],
    Literal["accepted", "request_contract"],
]:
    assert case.repair_contract is not None
    contract = case.repair_contract
    visual_modes = (
        tuple(case.brief.visual_strategy.visual_modes) if case.brief.visual_strategy else ()
    )
    model = _exact_semantic_repair_batch_model(contract.required_count, visual_modes)
    candidate_payload = {
        "shots": [
            item.to_repair_content().model_dump(mode="json")
            for item in contract.candidate_contents
        ]
    }
    try:
        model.model_validate(candidate_payload)
    except ValidationError:
        observed: Literal["accepted", "request_contract"] = "request_contract"
        issues = [case.expected_issue]
    else:
        observed = "accepted"
        issues = []
    corrected_payload = {
        "shots": [
            item.to_repair_content().model_dump(mode="json")
            for item in contract.corrected_contents
        ]
    }
    try:
        model.model_validate(corrected_payload)
    except ValidationError:
        corrected: Literal["accepted", "request_contract"] = "request_contract"
    else:
        corrected = "accepted"
    return observed, issues, corrected


def replay_semantic_failure_case(
    case_or_path: SemanticFailureCase | str | Path,
) -> SemanticFailureReplayResult:
    """Rebuild accepted history and replay one candidate without external services."""
    case = (
        case_or_path
        if isinstance(case_or_path, SemanticFailureCase)
        else load_semantic_failure_case(case_or_path)
    )
    compiled: list[Shot] = []
    for window_index, (batch, units) in enumerate(
        zip(
            case.checkpoint.batches,
            case.checkpoint.units_by_window,
            strict=True,
        )
    ):
        compiled.extend(
            _compile_semantic_batch(
                batch.to_semantic_batch(),
                units,
                case.brief,
                case.timeline,
                compiled,
                window_index,
            )
        )
        late_escape = _validate_compiled_prefix(compiled, case)
        if late_escape:
            return SemanticFailureReplayResult(
                case_id=case.case_id,
                checkpoint_batches=window_index + 1,
                checkpoint_shots=len(compiled),
                observed_boundary="final_validator",
                issues=[],
                late_validator_escape=late_escape,
            )
    if case.replay_kind == "repair_contract":
        observed, issues, corrected = _replay_repair_contract(case)
        return SemanticFailureReplayResult(
            case_id=case.case_id,
            checkpoint_batches=len(case.checkpoint.batches),
            checkpoint_shots=len(compiled),
            observed_boundary=observed,
            issues=issues,
            corrected_boundary=corrected,
        )
    assert case.failed_candidate is not None
    try:
        candidate_shots = _compile_semantic_batch(
            case.failed_candidate.to_semantic_batch(),
            case.failed_units,
            case.brief,
            case.timeline,
            compiled,
            case.window_index,
        )
    except SemanticPlanError as exc:
        result = SemanticFailureReplayResult(
            case_id=case.case_id,
            checkpoint_batches=len(case.checkpoint.batches),
            checkpoint_shots=len(compiled),
            observed_boundary="semantic_compiler",
            issues=exc.issues,
        )
    else:
        late_escape = _validate_compiled_prefix([*compiled, *candidate_shots], case)
        result = SemanticFailureReplayResult(
            case_id=case.case_id,
            checkpoint_batches=len(case.checkpoint.batches),
            checkpoint_shots=len(compiled),
            observed_boundary="final_validator" if late_escape else "accepted",
            issues=[],
            late_validator_escape=late_escape,
        )
    if case.corrected_candidate is None:
        return result
    try:
        corrected_shots = _compile_semantic_batch(
            case.corrected_candidate.to_semantic_batch(),
            case.failed_units,
            case.brief,
            case.timeline,
            compiled,
            case.window_index,
        )
    except SemanticPlanError:
        corrected_boundary = "semantic_compiler"
    else:
        corrected_escape = _validate_compiled_prefix(
            [*compiled, *corrected_shots], case
        )
        corrected_boundary = "final_validator" if corrected_escape else "accepted"
        if corrected_escape and result.late_validator_escape is None:
            result = result.model_copy(update={"late_validator_escape": corrected_escape})
    return result.model_copy(update={"corrected_boundary": corrected_boundary})


def replay_semantic_failure_corpus(
    directory: str | Path,
) -> SemanticFailureCorpusReport:
    """Replay every committed semantic failure case in stable filename order."""
    paths = sorted(Path(directory).glob("*.json"))
    if not paths:
        raise ValueError("Semantic failure corpus is empty")
    cases = [load_semantic_failure_case(path) for path in paths]
    results = [replay_semantic_failure_case(case) for case in cases]
    repeated: dict[str, int] = {}
    for case in cases:
        repeated[case.failure_code] = repeated.get(case.failure_code, 0) + 1
    late_escapes = [
        result.case_id for result in results if result.late_validator_escape
    ]
    expected = {
        case.case_id: case.expected_boundary for case in cases
    }
    observed: dict[str, str] = {
        result.case_id: result.observed_boundary for result in results
    }
    ready = (
        observed == expected
        and not late_escapes
        and all(
            result.corrected_boundary in {"not_provided", "accepted"}
            for result in results
        )
    )
    return SemanticFailureCorpusReport(
        case_ids=[case.case_id for case in cases],
        observed_boundaries=observed,
        accepted_checkpoint_batches=sum(
            result.checkpoint_batches for result in results
        ),
        repeated_failure_codes=repeated,
        late_validator_escapes=late_escapes,
        ready=ready,
    )


def build_failure_intelligence_report(
    corpus_directory: str | Path,
    live_evidence_path: str | Path,
) -> FailureIntelligenceReport:
    """Combine sanitized live metrics, corpus replay and validator ownership audit."""
    corpus_directory = Path(corpus_directory)
    case_paths = sorted(corpus_directory.glob("*.json"))
    cases = [load_semantic_failure_case(path) for path in case_paths]
    for case in cases:
        ownership = failure_ownership_for_code(case.failure_code)
        if ownership.responsible_layer != case.responsible_layer:
            raise ValueError(
                f"Failure ownership mismatch for {case.case_id}: "
                f"{case.responsible_layer} != {ownership.responsible_layer}"
            )
    corpus = replay_semantic_failure_corpus(corpus_directory)
    audit = semantic_validator_audit()
    ledger = SanitizedLiveRunLedger.model_validate_json(
        Path(live_evidence_path).read_text(encoding="utf-8")
    )
    case_evidence = {
        digest for case in cases for digest in case.raw_evidence_sha256s
    }
    ledger_evidence = {
        digest for run in ledger.runs for digest in run.evidence_sha256s
    }
    missing = sorted(case_evidence - ledger_evidence)
    if missing:
        raise ValueError(
            "Live failure evidence does not cover corpus hashes: " + ", ".join(missing)
        )
    live_attempts = sum(run.live_attempts for run in ledger.runs)
    accepted_windows = sum(run.accepted_windows for run in ledger.runs)
    latest = next(run for run in ledger.runs if run.latest)
    repeated = {
        code: count
        for code, count in corpus.repeated_failure_codes.items()
        if count > 1
    }
    ready = corpus.ready and audit.ready
    return FailureIntelligenceReport(
        live_runs=len(ledger.runs),
        live_attempts=live_attempts,
        accepted_windows=accepted_windows,
        live_attempts_per_accepted_window=(
            live_attempts / accepted_windows if accepted_windows else None
        ),
        repair_count=sum(run.repair_count for run in ledger.runs),
        provider_refusals=sum(run.provider_refusals for run in ledger.runs),
        quota_switches=sum(run.quota_switches for run in ledger.runs),
        checkpoint_progress=(
            f"{latest.checkpoint_windows}/{latest.total_windows} windows, "
            f"{latest.checkpoint_shots} shots"
        ),
        repeated_failure_codes=repeated,
        late_validator_escapes=corpus.late_validator_escapes,
        validator_audit_ready=audit.ready,
        replay_corpus_ready=corpus.ready,
        next_planner_version=SEMANTIC_PLANNER_VERSION,
        next_compiler_version=SHOT_COMPILER_VERSION,
        bounded_live_requests_allowed=1 if ready else 0,
        ready_for_one_bounded_live_request=ready,
    )
