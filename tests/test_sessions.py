from hashlib import sha256
import json

import pytest

from edu_disagreement import DisagreementRegion
from edu_disagreement import sessions
from edu_disagreement.sessions import (
    VERDICTS, SessionValidationError, Source, export_session, load_session, new_session,
)


@pytest.fixture
def session():
    return new_session(Source("a.edus", "a\nbc\nd\nef"), Source("b.txt", "ab\nc\ndef"))


@pytest.mark.parametrize("verdict", VERDICTS)
def test_all_verdicts_round_trip(session, verdict):
    region = session.comparison.disagreement_regions[0]
    session.assess(region, verdict)
    loaded = load_session(export_session(session))
    assert loaded.assessments[region].verdict == verdict
    assert loaded.assessments[region].region == region
    assert loaded.assessments[region].note is None


def test_absence_is_distinct_from_unresolved(session):
    a, b = session.comparison.disagreement_regions
    assert not session.assessments
    session.assess(a, "unresolved")
    assert len(session.assessments) == 1
    assert b not in session.assessments
    loaded = load_session(export_session(session))
    assert loaded.assessments[a].verdict == "unresolved"
    assert b not in loaded.assessments
    loaded.assess(a, None)
    assert not loaded.assessments


def test_round_trip_preserves_sources_hashes_notes_and_ui_state(session):
    a = Source("a é.edus", "\r\na \r\n\r\nbc\r\nd\r\nef\r\n")
    b = Source("b.txt", "ab\nc\ndef\n")
    session = new_session(a, b)
    first, second = session.comparison.disagreement_regions
    session.assess(first, "both", "  é🙂\nfirst note  ")
    session.assess(second, "neither", "second note")
    session.current_disagreement, session.context_edus = 1, 4
    payload = export_session(session)
    data = json.loads(payload)
    assert set(data) == {"schema_version", "sources", "state", "assessments"}
    assert data["sources"]["A"]["content"] == a.content
    assert data["sources"]["A"]["sha256"] == sha256(a.content.encode("utf-8")).hexdigest()
    assert data["sources"]["B"]["sha256"] == sha256(b.content.encode("utf-8")).hexdigest()
    loaded = load_session(payload.encode("utf-8"))
    assert loaded == session
    assert loaded.a_source.content.encode("utf-8") == a.content.encode("utf-8")
    assert loaded.comparison is not session.comparison
    assert loaded.assessments[first].note != loaded.assessments[second].note


def test_load_recomputes_comparison_and_ignores_untrusted_cached_results(session, monkeypatch):
    data = json.loads(export_session(session))
    data["comparison_result"] = {"canonical_text": "stale", "disagreement_regions": []}
    calls = []
    original = sessions.compare_annotations

    def compare(a, b):
        calls.append((a, b))
        return original(a, b)

    monkeypatch.setattr(sessions, "compare_annotations", compare)
    loaded = load_session(json.dumps(data))
    assert len(calls) == 1
    assert loaded.comparison == session.comparison


@pytest.mark.parametrize("payload", ["{", "null", "[]", b"\xff", '{"schema_version":1,"schema_version":1}',
                                     '{"x":NaN}'])
def test_malformed_session_rejected(payload):
    with pytest.raises(SessionValidationError):
        load_session(payload)


@pytest.mark.parametrize("version", [None, 0, 2, "1", True])
def test_unsupported_schema_rejected(session, version):
    data = json.loads(export_session(session))
    data["schema_version"] = version
    with pytest.raises(SessionValidationError, match="schema_version"):
        load_session(json.dumps(data))


@pytest.mark.parametrize("field", ["filename", "content", "sha256"])
def test_required_source_fields(session, field):
    data = json.loads(export_session(session))
    del data["sources"]["A"][field]
    with pytest.raises(SessionValidationError, match="Source A requires"):
        load_session(json.dumps(data))


@pytest.mark.parametrize("side", ["A", "B"])
def test_hash_mismatch_rejected(session, side):
    data = json.loads(export_session(session))
    data["sources"][side]["content"] += " "
    with pytest.raises(SessionValidationError, match=f"Source {side} SHA-256 mismatch"):
        load_session(json.dumps(data))


@pytest.mark.parametrize("field", ["start_offset", "end_offset", "a_edu_indices", "b_edu_indices"])
def test_every_identity_field_must_match(session, field):
    session.assess(session.comparison.disagreement_regions[0], "a_only")
    data = json.loads(export_session(session))
    item = data["assessments"][0]
    item[field] = [999] if field.endswith("indices") else item[field] + 1
    with pytest.raises(SessionValidationError, match="identity does not match"):
        load_session(json.dumps(data))


def test_changed_sources_cannot_reuse_old_region_identity(session):
    session.assess(session.comparison.disagreement_regions[0], "both")
    data = json.loads(export_session(session))
    content = "abc\nde\nf"
    data["sources"]["A"].update(content=content, sha256=sha256(content.encode()).hexdigest())
    with pytest.raises(SessionValidationError, match="identity does not match"):
        load_session(json.dumps(data))


@pytest.mark.parametrize(("index", "expected"), [(0, 0), (1, 1), (-3, 0), (999, 1), ("bad", 0)])
def test_position_restoration_and_clamping(session, index, expected):
    data = json.loads(export_session(session))
    data["state"]["current_disagreement"] = index
    assert load_session(json.dumps(data)).current_disagreement == expected


@pytest.mark.parametrize(("context", "expected"), [(0, 0), (10, 10), (11, 1), (-1, 1), ("bad", 1)])
def test_context_restoration_and_fallback(session, context, expected):
    data = json.loads(export_session(session))
    data["state"]["context_edus"] = context
    assert load_session(json.dumps(data)).context_edus == expected


def test_zero_regions_restores_safe_position():
    session = new_session(Source("a.txt", "a"), Source("b.edus", "a"))
    session.current_disagreement = 999
    assert load_session(export_session(session)).current_disagreement == 0


@pytest.mark.parametrize(("field", "value", "message"), [
    ("verdict", "hlv", "unknown verdict"), ("note", 10, "note must be text"),
    ("start_offset", True, "integer start/end"), ("a_edu_indices", [True], "integer EDU"),
])
def test_malformed_assessment_fields(session, field, value, message):
    session.assess(session.comparison.disagreement_regions[0], "both")
    data = json.loads(export_session(session))
    data["assessments"][0][field] = value
    with pytest.raises(SessionValidationError, match=message):
        load_session(json.dumps(data))


def test_duplicate_assessment_rejected(session):
    session.assess(session.comparison.disagreement_regions[0], "both")
    data = json.loads(export_session(session))
    data["assessments"].append(data["assessments"][0])
    with pytest.raises(SessionValidationError, match="duplicates an assessment"):
        load_session(json.dumps(data))


def test_noncomparable_embedded_sources_rejected(session):
    data = json.loads(export_session(session))
    data["sources"]["B"].update(content="different", sha256=sha256(b"different").hexdigest())
    with pytest.raises(SessionValidationError, match="not comparable"):
        load_session(json.dumps(data))


@pytest.mark.parametrize("field", ["filename", "content", "note"])
def test_unpaired_unicode_surrogates_are_rejected(session, field):
    session.assess(session.comparison.disagreement_regions[0], "both")
    data = json.loads(export_session(session))
    if field == "note":
        data["assessments"][0][field] = "\ud800"
    else:
        data["sources"]["A"][field] = "\ud800"
    with pytest.raises(SessionValidationError, match="invalid Unicode"):
        load_session(json.dumps(data))


def test_optional_ui_state_defaults(session):
    data = json.loads(export_session(session))
    del data["state"]
    restored = load_session(json.dumps(data))
    assert restored.current_disagreement == 0
    assert restored.context_edus == 1


def test_assessing_nonexistent_region_rejected(session):
    with pytest.raises(SessionValidationError):
        session.assess(DisagreementRegion(999, 1000, (0,), (0,)), "both")
