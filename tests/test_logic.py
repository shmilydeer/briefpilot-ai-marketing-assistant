from models import Brief, DraftPackage, ChannelDraft
from logic import quality_checks, export_markdown, parse_brief, generate_drafts
import pytest


def sample_brief():
    return Brief(brand="CupCo", product="Reusable cup", audience="Commuters", campaign_goal="Awareness", key_message="Reusable", tone="Friendly", offer="", call_to_action="Learn more", region="UK", constraints="", missing_information=["offer"], assumptions=[])

def sample_package():
    return DraftPackage(drafts=[ChannelDraft(channel="TikTok",hook="Your commute",body="Scene 1: cup on desk",call_to_action="Learn more",visual_direction="Natural light",hashtags=["#ReusableCup"],notes_for_review=[])], claims_to_verify=[],general_review_notes=[])

def test_complete_brief_passes_required_checks():
    assert all(p for _,p,_ in quality_checks(sample_brief(),sample_package()))

def test_missing_cta_is_flagged():
    b=sample_brief().model_copy(update={"call_to_action":""})
    assert any(("行动号召" in name and not passed) for name,passed,_ in quality_checks(b,sample_package()))

def test_unverified_claim_is_flagged():
    p=sample_package().model_copy(update={"claims_to_verify":["50% reduction"]})
    assert not quality_checks(sample_brief(),p)[-1][1]

def test_export_contains_review_status_and_channels():
    output=export_markdown(sample_brief(),sample_package(),"Draft — not approved")
    assert "Draft — not approved" in output and "TikTok" in output

def test_parse_empty_input_rejected_without_api_call():
    with pytest.raises(ValueError):
        parse_brief("  ", "not-a-real-key")

def test_generate_requires_channel_without_api_call():
    with pytest.raises(ValueError):
        generate_drafts(sample_brief(), [], "not-a-real-key")
