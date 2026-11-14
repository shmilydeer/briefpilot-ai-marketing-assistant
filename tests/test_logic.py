from types import SimpleNamespace

from models import (
    Brief, BriefExtraction, ClarificationQuestion, DraftPackage, ChannelDraft,
    GeneratedChannelDraft, GeneratedDraftPackage,
)
from logic import (
    quality_checks, export_markdown, parse_brief, generate_drafts,
    changed_brief_fields, change_impact_fields, save_brief_revision,
    update_clarification, apply_clarification_answer,
    unresolved_clarifications, reconcile_brief_issues,
    bind_draft_package, mark_package_stale, replace_package_safely,
    build_field_sources, create_clarification_questions, mark_user_sources,
)
import pytest


class FakeStructuredClient:
    def __init__(self, parsed):
        self.parsed = parsed
        self.calls = []
        self.chat = SimpleNamespace(completions=self)

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(refusal=None, parsed=self.parsed)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def sample_brief():
    return Brief(brand="CupCo", product="Reusable cup", audience="Commuters", campaign_goal="Awareness", key_message="Reusable", tone="Friendly", offer="", call_to_action="Learn more", region="UK", constraints="", missing_information=["offer"], assumptions=[])

def sample_package():
    return DraftPackage(drafts=[ChannelDraft(channel="TikTok",hook="Your commute",body="Scene 1: cup on desk",call_to_action="Learn more",visual_direction="Natural light",hashtags=["#ReusableCup"],notes_for_review=[],chinese_summary="面向通勤者的简短中文释义")], claims_to_verify=[],general_review_notes=[])

def test_complete_brief_passes_required_checks():
    assert all(p for _,p,_ in quality_checks(sample_brief(),sample_package()))

def test_missing_cta_is_flagged():
    b=sample_brief().model_copy(update={"call_to_action":""})
    assert any(("行动号召" in name and not passed) for name,passed,_ in quality_checks(b,sample_package()))

def test_unverified_claim_is_flagged():
    p=sample_package().model_copy(update={"claims_to_verify":["50% reduction"]})
    assert not quality_checks(sample_brief(),p)[-1][1]

def test_export_contains_review_status_and_channels():
    output=export_markdown(sample_brief(),sample_package(),"Draft — not approved",2,["确认优惠信息"])
    assert "Draft — not approved" in output and "TikTok" in output
    assert "Brief version: v2" in output
    assert "Marketing Brief" in output and "Client Clarification Sheet" in output and "Creative Handoff" in output
    assert "确认优惠信息" in output
    assert "面向通勤者的简短中文释义" in output
    assert "not approved for automatic publishing" in output

def test_parse_empty_input_rejected_without_api_call():
    with pytest.raises(ValueError):
        parse_brief("  ", "not-a-real-key")

def test_generate_requires_channel_without_api_call():
    with pytest.raises(ValueError):
        generate_drafts(sample_brief(), [], "not-a-real-key")


def test_parse_brief_validates_structured_output_with_pydantic_schema():
    extraction = BriefExtraction(**sample_brief().model_dump(exclude={"field_sources"}))
    client = FakeStructuredClient(extraction)
    brief = parse_brief(
        "CupCo plans a UK campaign for Commuters.",
        "mock-key-not-sent",
        client=client,
    )
    assert isinstance(brief, Brief)
    assert client.calls[0]["response_format"] is BriefExtraction
    assert brief.field_sources["brand"].source_type == "customer_original"
    assert brief.field_sources["brand"].verification_status == "unverified"


def test_generate_drafts_binds_english_and_chinese_structured_fields():
    generated = GeneratedDraftPackage(
        drafts=[GeneratedChannelDraft(
            channel="TikTok",
            hook="Made for the commute.",
            body="Carry it easily through the working day.",
            call_to_action="Explore the travel cup.",
            visual_direction="Natural-light commute scenes.",
            hashtags=["#DailyCarry"],
            notes_for_review=["Confirm product specifications."],
            chinese_summary="轻松随行，陪伴日常通勤。",
        )],
        claims_to_verify=[],
        general_review_notes=["Internal working draft."],
    )
    client = FakeStructuredClient(generated)
    package = generate_drafts(
        sample_brief(),
        ["TikTok"],
        "mock-key-not-sent",
        source_brief_revision=4,
        client=client,
    )
    assert client.calls[0]["response_format"] is GeneratedDraftPackage
    assert package.source_brief_revision == 4
    assert package.drafts[0].body == "Carry it easily through the working day."
    assert package.drafts[0].chinese_summary == "轻松随行，陪伴日常通勤。"

def test_brief_changes_only_include_substantive_editable_fields():
    previous = sample_brief()
    notes_only = previous.model_copy(update={"assumptions": ["待确认"]})
    assert changed_brief_fields(previous, notes_only) == set()
    updated = previous.model_copy(update={"audience": "UK commuters", "tone": "Warm"})
    assert changed_brief_fields(previous, updated) == {"audience", "tone"}

def test_change_impact_review_only_flags_critical_fields():
    assert change_impact_fields({"audience", "tone", "region"}) == {"audience", "region"}

def test_identical_brief_does_not_increment_revision():
    brief = sample_brief()
    saved, revision, confirmed, changed = save_brief_revision(brief, brief.model_copy(deep=True), 4, 4)
    assert saved == brief
    assert revision == 4
    assert confirmed == 4
    assert changed == set()

def test_core_field_change_increments_revision_and_invalidates_confirmation():
    brief = sample_brief()
    candidate = brief.model_copy(update={"audience": "UK commuters aged 20-35"})
    _, revision, confirmed, changed = save_brief_revision(brief, candidate, 2, 2)
    assert revision == 3
    assert confirmed is None
    assert change_impact_fields(changed) == {"audience"}

def test_clarification_answer_is_linked_and_requires_explicit_apply():
    brief = sample_brief()
    question = ClarificationQuestion(id="cq-1", field_name="audience", question="目标受众是谁？", priority=1)
    answered = update_clarification(question, "answer", "UK urban commuters")
    assert answered.field_name == "audience"
    assert answered.answer == "UK urban commuters"
    assert brief.audience == "Commuters"
    updated, applied = apply_clarification_answer(brief, answered)
    assert updated.audience == "UK urban commuters"
    assert applied.status == "applied"

def test_resolved_question_is_not_exported_as_unresolved():
    brief = sample_brief().model_copy(update={"missing_information": ["offer"]})
    question = ClarificationQuestion(id="cq-1", field_name="offer", question="offer", priority=1)
    resolved = update_clarification(question, "not_applicable")
    reconciled = reconcile_brief_issues(brief, [resolved])
    assert reconciled.missing_information == []
    assert unresolved_clarifications([resolved]) == []
    package = bind_draft_package(GeneratedDraftPackage(**sample_package().model_dump(include={"drafts", "claims_to_verify", "general_review_notes"})), reconciled, 2)
    output = export_markdown(reconciled, package, package.review_status, 2, unresolved_clarifications([resolved]))
    clarification_section = output.split("## Client Clarification Sheet", 1)[1].split("## Creative Handoff", 1)[0]
    assert "offer" not in clarification_section

def test_ai_suggestion_never_overwrites_field_before_user_applies_it():
    brief = sample_brief().model_copy(update={"key_message": "Human-approved message"})
    question = ClarificationQuestion(id="cq-1", field_name="key_message", question="核心信息？", priority=1)
    answered = update_clarification(question, "answer", "AI suggested replacement")
    assert brief.key_message == "Human-approved message"
    assert answered.status == "answered"

def test_draft_package_keeps_independent_source_brief_snapshot():
    brief = sample_brief()
    clarification = ClarificationQuestion(id="cq-1", field_name="offer", question="是否有优惠？", priority=1, status="deferred")
    package = bind_draft_package(GeneratedDraftPackage(**sample_package().model_dump(include={"drafts", "claims_to_verify", "general_review_notes"})), brief, 5, [clarification])
    brief.audience = "Changed later"
    clarification.status = "not_applicable"
    assert package.source_brief_revision == 5
    assert package.source_brief_snapshot.audience == "Commuters"
    assert package.clarification_snapshot[0].status == "deferred"

def test_failed_generation_preserves_existing_package():
    current = sample_package()
    def fail_generation():
        raise RuntimeError("simulated failure")
    result, error = replace_package_safely(current, fail_generation)
    assert result is current
    assert isinstance(error, RuntimeError)

def test_stale_package_exports_its_snapshot_and_original_revision():
    original = sample_brief()
    package = bind_draft_package(GeneratedDraftPackage(**sample_package().model_dump(include={"drafts", "claims_to_verify", "general_review_notes"})), original, 3)
    stale = mark_package_stale(package)
    latest = original.model_copy(update={"audience": "A different audience"})
    output = export_markdown(latest, stale, stale.review_status, 99, [])
    assert "Brief version: v3" in output
    assert "Package status: stale" in output
    assert "Commuters" in output
    assert "A different audience" not in output

def test_source_excerpt_is_only_used_when_it_exists_verbatim_in_input():
    brief = sample_brief()
    sources = build_field_sources(brief, "CupCo targets Commuters in the UK.")
    assert sources["audience"].source_type == "customer_original"
    assert sources["audience"].source_excerpt == "Commuters"
    assert sources["key_message"].source_type == "ai_inference"
    assert sources["key_message"].source_excerpt == ""

def test_user_edit_changes_source_without_fabricating_excerpt_and_questions_are_capped():
    brief = sample_brief().model_copy(update={
        "missing_information": ["offer", "CTA", "目标市场", "预算"],
        "assumptions": ["品牌语气"],
    })
    sourced = mark_user_sources(brief, {"audience", "tone"})
    assert sourced.field_sources["audience"].source_type == "user_entered"
    assert sourced.field_sources["audience"].source_excerpt == ""
    assert sourced.field_sources["tone"].source_type == "user_entered"
    assert len(create_clarification_questions(brief)) == 3

def test_clarification_question_field_matching_distinguishes_market_audience_and_goal():
    brief = sample_brief().model_copy(update={
        "missing_information": ["目标市场或地区是什么？", "目标受众需要收窄吗？", "营销目标是什么？"],
        "assumptions": [],
    })
    questions = create_clarification_questions(brief)
    assert [item.field_name for item in questions] == ["region", "audience", "campaign_goal"]
