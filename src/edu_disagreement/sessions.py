"""Human assessments and portable sessions; independent of Streamlit."""

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from .comparison import BoundaryProjectionError, ContentMismatchError, compare_annotations
from .models import ComparisonResult, DisagreementRegion
from .parsing import parse_annotation


Verdict = Literal["a_only", "both", "b_only", "neither", "unresolved"]
VERDICTS: tuple[Verdict, ...] = ("a_only", "both", "b_only", "neither", "unresolved")


class SessionValidationError(ValueError):
    """A saved session is malformed or inconsistent with its embedded sources."""


@dataclass(frozen=True)
class Source:
    filename: str
    content: str

    @property
    def sha256(self) -> str:
        return sha256(self.content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Assessment:
    start_offset: int
    end_offset: int
    a_edu_indices: tuple[int, ...]
    b_edu_indices: tuple[int, ...]
    verdict: Verdict
    note: str | None = None

    @property
    def region(self) -> DisagreementRegion:
        return DisagreementRegion(
            self.start_offset, self.end_offset, self.a_edu_indices, self.b_edu_indices
        )


@dataclass
class Session:
    a_source: Source
    b_source: Source
    comparison: ComparisonResult
    assessments: dict[DisagreementRegion, Assessment] = field(default_factory=dict)
    current_disagreement: int = 0
    context_edus: int = 1

    def assess(self, region: DisagreementRegion, verdict: Verdict | None, note: str | None = None) -> None:
        """No selection means no assessment; unresolved is an explicit verdict."""
        if region not in self.comparison.disagreement_regions:
            raise SessionValidationError("Assessment does not match a current disagreement.")
        if verdict is None:
            self.assessments.pop(region, None)
            return
        if verdict not in VERDICTS:
            raise SessionValidationError("Unknown assessment verdict.")
        if note is not None and not isinstance(note, str):
            raise SessionValidationError("Assessment note must be text or null.")
        if note is not None:
            try:
                note.encode("utf-8")
            except UnicodeEncodeError as error:
                raise SessionValidationError("Assessment note contains invalid Unicode.") from error
        self.assessments[region] = Assessment(
            region.start_offset, region.end_offset, region.a_edu_indices,
            region.b_edu_indices, verdict, note,
        )


def compare_uploads(a_bytes: bytes, b_bytes: bytes) -> ComparisonResult:
    """Use the unchanged file parser/comparator, then remove temporary files."""
    with TemporaryDirectory(prefix="edu-comparison-") as directory:
        a_path, b_path = Path(directory) / "a.txt", Path(directory) / "b.txt"
        a_path.write_bytes(a_bytes)
        b_path.write_bytes(b_bytes)
        return compare_annotations(parse_annotation(a_path), parse_annotation(b_path))


def new_session(a_source: Source, b_source: Source) -> Session:
    return Session(
        a_source, b_source,
        compare_uploads(a_source.content.encode("utf-8"), b_source.content.encode("utf-8")),
    )


def export_session(session: Session) -> str:
    """Serialize original sources and judgments, never a cached comparison."""
    sources = {
        label: {"filename": source.filename, "sha256": source.sha256, "content": source.content}
        for label, source in (("A", session.a_source), ("B", session.b_source))
    }
    return json.dumps({
        "schema_version": 1,
        "sources": sources,
        "state": {
            "current_disagreement": session.current_disagreement,
            "context_edus": session.context_edus,
        },
        "assessments": [asdict(session.assessments[region])
                        for region in session.comparison.disagreement_regions
                        if region in session.assessments],
    }, ensure_ascii=False, indent=2) + "\n"


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SessionValidationError(f"Duplicate JSON field: {key}.")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise SessionValidationError(f"Invalid JSON constant: {value}.")


def load_session(payload: str | bytes) -> Session:
    """Validate sources, recompute comparison, then match full region identities."""
    try:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        data = json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise SessionValidationError("Session must be valid UTF-8 JSON.") from error
    if not isinstance(data, dict):
        raise SessionValidationError("Session must be a JSON object.")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise SessionValidationError("Unsupported schema_version; expected 1.")
    if not isinstance(data.get("sources"), dict):
        raise SessionValidationError("Session requires embedded A and B sources.")

    sources = []
    for label in ("A", "B"):
        item = data["sources"].get(label)
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str)
                                                for key in ("filename", "content", "sha256")):
            raise SessionValidationError(f"Source {label} requires filename, content, and sha256 strings.")
        if not item["filename"]:
            raise SessionValidationError(f"Source {label} filename must not be empty.")
        source = Source(item["filename"], item["content"])
        try:
            source.filename.encode("utf-8")
            digest = source.sha256
        except UnicodeEncodeError as error:
            raise SessionValidationError(f"Source {label} contains invalid Unicode.") from error
        if digest != item["sha256"]:
            raise SessionValidationError(f"Source {label} SHA-256 mismatch; embedded content is inconsistent.")
        sources.append(source)

    try:
        session = new_session(*sources)
    except (ContentMismatchError, BoundaryProjectionError) as error:
        raise SessionValidationError(f"Embedded annotations are not comparable: {error}") from error

    records = data.get("assessments")
    if not isinstance(records, list):
        raise SessionValidationError("Session requires an assessments array.")
    for number, item in enumerate(records, 1):
        prefix = f"Assessment {number}"
        if not isinstance(item, dict):
            raise SessionValidationError(f"{prefix} must be an object.")
        if not all(type(item.get(key)) is int for key in ("start_offset", "end_offset")):
            raise SessionValidationError(f"{prefix} requires integer start/end offsets.")
        if not all(isinstance(item.get(key), list) and all(type(i) is int for i in item[key])
                   for key in ("a_edu_indices", "b_edu_indices")):
            raise SessionValidationError(f"{prefix} requires arrays of integer EDU indices.")
        verdict, note = item.get("verdict"), item.get("note")
        if not isinstance(verdict, str) or verdict not in VERDICTS:
            raise SessionValidationError(f"{prefix} has an unknown verdict.")
        if note is not None and not isinstance(note, str):
            raise SessionValidationError(f"{prefix} note must be text or null.")
        region = DisagreementRegion(item["start_offset"], item["end_offset"],
                                    tuple(item["a_edu_indices"]), tuple(item["b_edu_indices"]))
        if region not in session.comparison.disagreement_regions:
            raise SessionValidationError(f"{prefix} identity does not match a recomputed disagreement.")
        if region in session.assessments:
            raise SessionValidationError(f"{prefix} duplicates an assessment for the same disagreement.")
        session.assess(region, verdict, note)

    state = data.get("state", {})
    if not isinstance(state, dict):
        raise SessionValidationError("Session state must be an object.")
    index = state.get("current_disagreement", 0)
    if type(index) is not int:
        index = 0
    session.current_disagreement = max(0, min(index, len(session.comparison.disagreement_regions) - 1))
    context = state.get("context_edus", 1)
    session.context_edus = context if type(context) is int and 0 <= context <= 10 else 1
    return session
