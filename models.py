from typing import Literal
from pydantic import BaseModel, Field

SourceType = Literal["customer_original", "user_entered", "ai_inference", "unknown"]
VerificationStatus = Literal["unverified", "pending", "verified", "not_applicable"]
ClarificationStatus = Literal["open", "answered", "deferred", "not_applicable", "applied"]

class FieldSource(BaseModel):
    source_type: SourceType = "unknown"
    source_excerpt: str = ""
    verification_status: VerificationStatus = "pending"

class ClarificationQuestion(BaseModel):
    id: str
    field_name: str
    question: str
    priority: int = Field(ge=1, le=3)
    answer: str = ""
    status: ClarificationStatus = "open"

class Brief(BaseModel):
    brand: str = Field(description="Brand name; empty string if unknown")
    product: str = Field(description="Product/service; empty if unknown")
    audience: str = Field(description="Target audience; empty if unknown")
    campaign_goal: str = Field(description="Marketing objective; empty if unknown")
    key_message: str = Field(description="Main message; empty if unknown")
    tone: str = Field(description="Brand tone; empty if unknown")
    offer: str = Field(description="Verified promotion/offer; empty if not provided")
    call_to_action: str = Field(description="CTA; empty if unknown")
    region: str = Field(description="Target geography; empty if unknown")
    constraints: str = Field(description="Restrictions, mandatory words, budget context; empty if unknown")
    missing_information: list[str] = Field(description="Critical items missing from user's input")
    assumptions: list[str] = Field(description="Any interpretations that require user confirmation")
    field_sources: dict[str, FieldSource] = Field(default_factory=dict)

class BriefExtraction(BaseModel):
    """Schema used only for OpenAI extraction; local workflow metadata is added afterwards."""
    brand: str = Field(description="Brand name; empty string if unknown")
    product: str = Field(description="Product/service; empty if unknown")
    audience: str = Field(description="Target audience; empty if unknown")
    campaign_goal: str = Field(description="Marketing objective; empty if unknown")
    key_message: str = Field(description="Main message; empty if unknown")
    tone: str = Field(description="Brand tone; empty if unknown")
    offer: str = Field(description="Verified promotion/offer; empty if not provided")
    call_to_action: str = Field(description="CTA; empty if unknown")
    region: str = Field(description="Target geography; empty if unknown")
    constraints: str = Field(description="Restrictions, mandatory words, budget context; empty if unknown")
    missing_information: list[str] = Field(description="Critical items missing from user's input")
    assumptions: list[str] = Field(description="Any interpretations that require user confirmation")

class ChannelDraft(BaseModel):
    channel: str
    hook: str
    body: str
    call_to_action: str
    visual_direction: str
    hashtags: list[str]
    notes_for_review: list[str]
    chinese_summary: str = ""
    chinese_summary_status: Literal["current", "pending_update"] = "current"

class GeneratedChannelDraft(BaseModel):
    channel: str
    hook: str
    body: str
    call_to_action: str
    visual_direction: str
    hashtags: list[str]
    notes_for_review: list[str]
    chinese_summary: str = Field(description="Short faithful Chinese summary of the English marketing content")
    chinese_summary_status: Literal["current", "pending_update"] = "current"

class DraftPackage(BaseModel):
    drafts: list[ChannelDraft]
    claims_to_verify: list[str]
    general_review_notes: list[str]
    source_brief_revision: int = 1
    source_brief_snapshot: Brief | None = None
    review_status: str = "草稿 — 未审核"
    lifecycle_status: Literal["current", "stale"] = "current"
    clarification_snapshot: list[ClarificationQuestion] = Field(default_factory=list)
    package_id: str = ""
    generated_at: str = ""
    generation_mode: Literal["local_fixture", "live_ai", "unspecified"] = "unspecified"
    content_revision: int = 1
    reviewed_content_revision: int | None = None
    stale_reason: str = ""

class GeneratedDraftPackage(BaseModel):
    """Schema returned by OpenAI before local version metadata is attached."""
    drafts: list[GeneratedChannelDraft]
    claims_to_verify: list[str]
    general_review_notes: list[str]
