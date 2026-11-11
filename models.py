from pydantic import BaseModel, Field

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

class ChannelDraft(BaseModel):
    channel: str
    hook: str
    body: str
    call_to_action: str
    visual_direction: str
    hashtags: list[str]
    notes_for_review: list[str]

class DraftPackage(BaseModel):
    drafts: list[ChannelDraft]
    claims_to_verify: list[str]
    general_review_notes: list[str]
