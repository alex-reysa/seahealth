from seahealth.schemas import EvidenceRef, evidence_ref_id


def _make_ref(**kwargs):
    base = dict(
        source_doc_id="doc_42",
        facility_id="vf_00042_x",
        chunk_id="chunk_007",
        span=(0, 10),
        snippet="hello world",
        source_type="facility_note",
        retrieved_at="2026-04-25T18:00:00Z",
    )
    base.update(kwargs)
    return EvidenceRef(**base)


def test_evidence_ref_id_format():
    ref = _make_ref()
    assert evidence_ref_id(ref) == "doc_42:chunk_007"


def test_evidence_ref_id_handles_special_chars():
    ref = _make_ref(source_doc_id="vf::row#42", chunk_id="c::1")
    assert evidence_ref_id(ref) == "vf::row#42:c::1"
