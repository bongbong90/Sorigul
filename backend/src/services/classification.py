from typing import Dict, Mapping, Optional

# CORE_WORKFLOW_REFINEMENT_PLAN.md D16 -- exact, trimmed subject strings only.
# No alias/fuzzy matching: this table is intentionally not reused as a
# filename-detection heuristic (that was removed under D12).
KNOWN_SUBJECT_STAGE: Dict[str, str] = {
    "부동산학개론": "1차",
    "민법": "1차",
    "공인중개사법": "2차",
    "부동산공법": "2차",
    "부동산공시법": "2차",
    "부동산세법": "2차",
}


class StageRequiredError(ValueError):
    """Raised when a subject is unknown and no override or supplied stage
    resolves it -- the caller must ask the user and either retry with a
    supplied stage or persist an override first."""

    def __init__(self, subject: str):
        super().__init__(subject)
        self.subject = subject


def resolve_stage(
    subject: str,
    supplied_stage: Optional[str],
    overrides: Mapping[str, str],
) -> str:
    """Resolve a subject to "1차"/"2차".

    Known subjects are server-authoritative: a client-supplied stage is
    ignored for them. Unknown subjects fall back to a previously saved
    override, then to a client-supplied stage. If neither is available,
    raises StageRequiredError so the caller can reject Job creation.
    """
    known = KNOWN_SUBJECT_STAGE.get(subject)
    if known is not None:
        return known

    override = overrides.get(subject)
    if override is not None:
        return override

    if supplied_stage in ("1차", "2차"):
        return supplied_stage

    raise StageRequiredError(subject)
