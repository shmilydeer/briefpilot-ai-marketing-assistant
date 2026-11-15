"""In-memory HTTP integration for the BriefPilot prototype.

The default ``local_fixture`` mode is deterministic and never calls an external
service. ``live_ai`` is opt-in per workspace and reads its API key only from the
server environment when the user explicitly starts an AI operation.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field, ValidationError, field_validator

from logic import (
    apply_clarification_answer,
    build_field_sources,
    bind_draft_package,
    change_impact_fields,
    changed_brief_fields,
    create_clarification_questions,
    export_markdown,
    generate_drafts,
    mark_package_stale,
    mark_user_sources,
    reconcile_brief_issues,
    parse_brief,
    replace_package_safely,
    save_brief_revision,
    unresolved_clarifications,
    update_clarification,
)
from models import (
    Brief, ClarificationQuestion, DraftPackage, FieldSource,
    GeneratedChannelDraft, GeneratedDraftPackage,
)


LOGGER = logging.getLogger("briefpilot.live_ai")
PROJECT_ROOT = Path(__file__).resolve().parent
PROTOTYPE_DIR = PROJECT_ROOT / "design_prototype"
LIVE_AI_LOG_PATH = PROJECT_ROOT / "test_exports" / "live_ai_errors.log"
MAX_REQUEST_BYTES = 64 * 1024
SESSION_COOKIE = "briefpilot_session"
EDITABLE_BRIEF_FIELDS = {
    "product", "campaign_goal", "audience", "key_message", "region", "tone", "constraints"
}
RunMode = Literal["local_fixture", "live_ai"]
TRUE_ENV_VALUES = {"1", "true", "yes", "on"}


def environment_flag(name: str) -> bool:
    """Read a boolean environment flag without inspecting any secret values."""
    return os.environ.get(name, "").strip().lower() in TRUE_ENV_VALUES


def public_demo_enabled() -> bool:
    """Render deployments and explicit public demos are fixture-only."""
    return environment_flag("RENDER") or environment_flag("BRIEFPILOT_PUBLIC_DEMO")


def server_port_from_environment() -> int:
    """Use Render's assigned port while preserving the local 8767 default."""
    raw_port = os.environ.get("PORT", "").strip()
    if not raw_port:
        return 8767
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError("PORT 必须是 1 到 65535 之间的整数") from exc
    if not 1 <= port <= 65535:
        raise ValueError("PORT 必须是 1 到 65535 之间的整数")
    return port


def _configure_live_ai_logger() -> None:
    """Persist only allow-listed OpenAI diagnostic metadata."""
    LIVE_AI_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    target = LIVE_AI_LOG_PATH.resolve()
    for handler in LOGGER.handlers:
        if (
            isinstance(handler, logging.FileHandler)
            and Path(handler.baseFilename).resolve() == target
        ):
            return
    handler = logging.FileHandler(LIVE_AI_LOG_PATH, encoding="utf-8", delay=True)
    formatter = logging.Formatter(
        "%(asctime)sZ %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    handler.setLevel(logging.ERROR)
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.ERROR)


_configure_live_ai_logger()


class CaptureAnalyzeRequest(BaseModel):
    raw_text: str = Field(min_length=1, max_length=5000)
    market: Literal["unknown", "UK", "US"] = "unknown"
    channels: list[Literal["TikTok", "Instagram"]] = Field(min_length=1, max_length=2)
    mode: RunMode = "local_fixture"

    @field_validator("raw_text")
    @classmethod
    def strip_and_reject_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("原始需求不能为空")
        return value

    @field_validator("channels")
    @classmethod
    def reject_duplicate_channels(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("传播渠道不能重复")
        return value


class BriefDraftPatch(BaseModel):
    fields: dict[str, str] = Field(min_length=1)

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, value: dict[str, str]) -> dict[str, str]:
        unknown = set(value) - EDITABLE_BRIEF_FIELDS
        if unknown:
            raise ValueError(f"不可编辑的 Brief 字段：{', '.join(sorted(unknown))}")
        return {key: item.strip() for key, item in value.items()}


class ClarificationActionRequest(BaseModel):
    action: Literal["answer", "defer", "not_applicable"]
    answer: str = ""


class WorkspaceResponse(BaseModel):
    mode: RunMode
    fixture_notice: str
    raw_text: str
    brief: Brief
    selected_channels: list[Literal["TikTok", "Instagram"]]
    questions: list[ClarificationQuestion]
    revision: int
    confirmed_revision: int | None
    status: Literal["draft", "confirmed", "confirmed_with_changes", "needs_reconfirmation"]
    dirty: bool
    changed_fields: list[str]
    impact_fields: list[str]
    unresolved_items: list[str]


class DeliverDraftPatch(BaseModel):
    package_id: str
    channel: Literal["TikTok", "Instagram"]
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("英文正文不能为空")
        return value


class DeliverReviewRequest(BaseModel):
    package_id: str
    status: Literal["草稿 — 未审核", "需要修改", "内部审核完成"]


class PackageSummary(BaseModel):
    package_id: str
    source_brief_revision: int
    content_revision: int
    review_status: str
    lifecycle_status: Literal["current", "stale"]
    generated_at: str
    stale_reason: str


class DeliverResponse(BaseModel):
    mode: RunMode
    fixture_notice: str
    package: DraftPackage | None
    selected_package_id: str | None
    history: list[PackageSummary]
    latest_brief_revision: int
    latest_brief_status: str
    can_generate: bool
    generation_blocker: str
    unresolved_items: list[str]


CaptureAnalyzeResponse = WorkspaceResponse


class WorkspaceOperationError(Exception):
    def __init__(
        self,
        status: HTTPStatus,
        code: str,
        message: str,
        correlation_id: str = "",
    ):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.correlation_id = correlation_id


class LiveAIAdapter:
    """Small injectable boundary around existing OpenAI/Pydantic logic."""

    def __init__(
        self,
        api_key_provider: Callable[[], str] | None = None,
        parse_function: Callable[..., Brief] = parse_brief,
        generate_function: Callable[..., DraftPackage] = generate_drafts,
    ) -> None:
        self._api_key_provider = api_key_provider or (
            lambda: os.environ.get("OPENAI_API_KEY", "")
        )
        self._parse_function = parse_function
        self._generate_function = generate_function

    @property
    def configured(self) -> bool:
        return bool(self._api_key_provider().strip())

    def analyze(self, request: CaptureAnalyzeRequest) -> Brief:
        api_key = self._require_key()
        try:
            parsed = self._parse_function(request.raw_text, api_key)
            brief = Brief.model_validate(parsed)
        except Exception as exc:
            raise self._safe_error(exc, "Capture") from exc

        sources = build_field_sources(brief, request.raw_text)
        for field_name, source in list(sources.items()):
            if source.source_type == "customer_original":
                sources[field_name] = source.model_copy(
                    update={"verification_status": "unverified"}
                )
            else:
                sources[field_name] = source.model_copy(
                    update={"verification_status": "pending"}
                )
        brief = brief.model_copy(update={"field_sources": sources}, deep=True)
        if request.market != "unknown":
            region = {"UK": "英国（UK）", "US": "美国（US）"}[request.market]
            sources = {
                key: value.model_copy(deep=True)
                for key, value in brief.field_sources.items()
            }
            sources["region"] = FieldSource(
                source_type="user_entered",
                source_excerpt="",
                verification_status="pending",
            )
            brief = brief.model_copy(
                update={"region": region, "field_sources": sources}, deep=True
            )
        return brief

    def generate(self, session: "WorkspaceSession") -> DraftPackage:
        api_key = self._require_key()
        try:
            generated = self._generate_function(
                session.saved_brief.model_copy(deep=True),
                list(session.selected_channels),
                api_key,
                source_brief_revision=session.revision,
                clarifications=[item.model_copy(deep=True) for item in session.questions],
            )
            package = DraftPackage.model_validate(generated)
        except Exception as exc:
            raise self._safe_error(exc, "Deliver") from exc

        expected = sorted(session.selected_channels)
        if sorted(item.channel for item in package.drafts) != expected:
            raise WorkspaceOperationError(
                HTTPStatus.BAD_GATEWAY,
                "invalid_ai_output",
                "AI 返回的渠道与当前 Brief 配置不一致，旧稿已保留。",
            )
        drafts = [
            item.model_copy(update={
                "chinese_summary_status": (
                    "current" if item.chinese_summary.strip() else "pending_update"
                )
            })
            for item in package.drafts
        ]
        return package.model_copy(update={"drafts": drafts}, deep=True)

    def _require_key(self) -> str:
        api_key = self._api_key_provider().strip()
        if not api_key:
            raise WorkspaceOperationError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "openai_not_configured",
                "服务端尚未配置 OPENAI_API_KEY；未调用 AI，也未切换为固定测试结果。",
            )
        return api_key

    @staticmethod
    def _safe_error(exc: Exception, stage: str) -> WorkspaceOperationError:
        if isinstance(exc, WorkspaceOperationError):
            return exc
        from openai import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            BadRequestError,
            ContentFilterFinishReasonError,
            InternalServerError,
            LengthFinishReasonError,
            NotFoundError,
            PermissionDeniedError,
            RateLimitError,
        )

        correlation_id = f"ai-{uuid.uuid4().hex[:12]}"
        exception_type = type(exc).__name__

        def safe_metadata(value: object) -> str:
            if value is None:
                return ""
            return re.sub(r"[^A-Za-z0-9._:/-]", "_", str(value))[:128]

        def safe_parameter_path(value: object) -> str:
            if value is None:
                return ""
            candidate = str(value).strip()
            if not re.fullmatch(r"[A-Za-z0-9_.\[\]-]{1,128}", candidate):
                return ""
            return candidate

        LOGGER.error(
            "live_ai_error stage=%s exception_type=%s http_status=%s "
            "openai_error_code=%s error_param=%s request_id=%s correlation_id=%s",
            safe_metadata(stage),
            safe_metadata(exception_type),
            safe_metadata(getattr(exc, "status_code", "")),
            safe_metadata(getattr(exc, "code", "")),
            safe_parameter_path(getattr(exc, "param", "")),
            safe_metadata(getattr(exc, "request_id", "")),
            correlation_id,
        )

        if isinstance(exc, AuthenticationError):
            code = "openai_authentication_failed"
            message = "OpenAI 认证失败，请检查服务端密钥配置后手动重试。"
        elif isinstance(exc, RateLimitError):
            code = "openai_rate_limited"
            message = "OpenAI 请求受到额度或速率限制，请检查账户用量后稍后手动重试。"
        elif isinstance(exc, (APITimeoutError, TimeoutError)):
            code = "openai_timeout"
            message = "OpenAI 请求超时，请检查网络后手动重试；现有工作状态未改变。"
        elif isinstance(exc, APIConnectionError):
            code = "openai_connection_failed"
            message = "无法连接 OpenAI，请检查网络、代理或 TLS 配置后手动重试。"
        elif isinstance(exc, BadRequestError):
            code = "openai_bad_request"
            message = "OpenAI 拒绝了请求，请检查模型和请求参数。"
        elif isinstance(exc, PermissionDeniedError):
            code = "openai_permission_denied"
            message = "当前 OpenAI 项目无权执行此请求，请检查项目和模型权限。"
        elif isinstance(exc, NotFoundError):
            code = "openai_not_found"
            message = "当前模型或接口不可用，请检查模型配置。"
        elif isinstance(exc, InternalServerError):
            code = "openai_server_error"
            message = "OpenAI 服务暂时异常，请稍后手动重试。"
        elif isinstance(exc, APIStatusError):
            code = "openai_status_error"
            message = "OpenAI 返回未分类的服务错误，请根据参考编号检查安全日志。"
        elif isinstance(exc, LengthFinishReasonError):
            code = "openai_output_limit"
            message = "模型输出达到上限，结构化结果未完成；请缩短输入或调整上限后手动重试。"
        elif isinstance(exc, ContentFilterFinishReasonError):
            code = "openai_content_filtered"
            message = "模型输出被安全策略终止，请检查输入内容后手动重试。"
        elif isinstance(exc, (ValidationError, ValueError, TypeError)):
            code = "invalid_ai_output"
            message = "AI 返回内容未通过结构化校验，请检查输入后手动重试。"
        else:
            code = "openai_request_failed"
            message = "OpenAI 请求失败，请根据参考编号检查安全日志后手动重试。"
        stage_label = "需求解析" if stage == "Capture" else "交付生成"
        return WorkspaceOperationError(
            HTTPStatus.BAD_GATEWAY,
            code,
            f"{stage_label}失败：{message}参考编号：{correlation_id}。",
            correlation_id,
        )


def _fixture_sources(brief: Brief, raw_text: str, market: str) -> dict[str, FieldSource]:
    """Reuse conservative matching without presenting fixture values as AI output."""
    sources = build_field_sources(brief, raw_text)
    for field_name, source in sources.items():
        if source.source_type == "ai_inference":
            sources[field_name] = FieldSource(
                source_type="unknown", source_excerpt="", verification_status="pending"
            )
    if market != "unknown":
        sources["region"] = FieldSource(
            source_type="user_entered", source_excerpt="", verification_status="pending"
        )
    return sources


def build_fixture_brief(request: CaptureAnalyzeRequest) -> Brief:
    region = {"UK": "英国（UK）", "US": "美国（US）", "unknown": ""}[request.market]
    clarification_assumptions = [
        "本次推广的营销目标需要如何确认？",
        "目标受众是否需要进一步收窄？",
        "核心信息需要优先强调什么？",
    ]
    if request.market == "unknown":
        clarification_assumptions.insert(0, "目标市场或地区是什么？")

    brief = Brief(
        brand="",
        product="轻量随行杯",
        audience="20–35 岁的城市通勤人群",
        campaign_goal="建立新品认知",
        key_message="轻量便携、易于日常清洁，适合通勤与随身携带",
        tone="自然、克制、专业",
        offer="",
        call_to_action="",
        region=region,
        constraints="不得添加环保认证、折扣或客户批准等未提供信息",
        missing_information=["品牌名称", "明确的行动号召", "已核实的优惠信息"],
        assumptions=clarification_assumptions,
    )
    brief.field_sources = _fixture_sources(brief, request.raw_text, request.market)
    return brief


def build_fixture_drafts(channels: list[str]) -> GeneratedDraftPackage:
    """Return safe fictional English working copy; no model or external service is used."""
    fixtures = {
        "TikTok": GeneratedChannelDraft(
            channel="TikTok",
            hook="Made for the commute.",
            body=(
                "Made for the commute. Light to carry, easy to clean, and ready "
                "for every stop along the way."
            ),
            call_to_action="Explore the everyday travel cup.",
            visual_direction="Natural-light city commute scenes with restrained product close-ups.",
            hashtags=["#EverydayCommute", "#TravelCup"],
            notes_for_review=["Confirm launch timing and any factual product specifications before use."],
            chinese_summary="为通勤日常而设计。轻便随行、易于清洁，陪你从容到达每一站。",
        ),
        "Instagram": GeneratedChannelDraft(
            channel="Instagram",
            hook="A lighter way to move through the day.",
            body=(
                "A lighter way to move through the day. Meet the travel cup "
                "designed for simple, everyday commutes."
            ),
            call_to_action="Discover a simpler commute.",
            visual_direction="Editorial still life and real commute moments in soft natural light.",
            hashtags=["#DailyCarry", "#CommuteDesign"],
            notes_for_review=["Do not add certifications, discounts, or approval claims."],
            chinese_summary="用更轻盈的方式开启一天。这款随行杯为简单、日常的通勤场景而设计。",
        ),
    }
    return GeneratedDraftPackage(
        drafts=[fixtures[channel] for channel in channels],
        claims_to_verify=[],
        general_review_notes=[
            "本地固定测试稿，仅用于内部工作流验证，不代表客户、市场或法律批准。",
            "上线日期、预算及任何营销声明在正式使用前仍需人工核实。",
        ],
    )


@dataclass
class WorkspaceSession:
    raw_text: str
    selected_channels: list[Literal["TikTok", "Instagram"]]
    mode: RunMode
    saved_brief: Brief
    draft_brief: Brief
    questions: list[ClarificationQuestion]
    revision: int = 1
    confirmed_revision: int | None = None
    had_confirmation: bool = False
    last_impact_fields: set[str] = field(default_factory=set)
    packages: list[DraftPackage] = field(default_factory=list)
    selected_package_id: str | None = None
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    @classmethod
    def from_capture(
        cls, request: CaptureAnalyzeRequest, brief: Brief | None = None
    ) -> "WorkspaceSession":
        if brief is None and request.mode == "live_ai":
            raise WorkspaceOperationError(
                HTTPStatus.BAD_GATEWAY,
                "live_brief_required",
                "实时 AI 工作区必须使用通过校验的模型响应创建。",
            )
        brief = brief or build_fixture_brief(request)
        return cls(
            raw_text=request.raw_text,
            selected_channels=list(request.channels),
            mode=request.mode,
            saved_brief=brief.model_copy(deep=True),
            draft_brief=brief.model_copy(deep=True),
            questions=create_clarification_questions(brief, request.raw_text),
        )

    def response(self) -> WorkspaceResponse:
        changed = changed_brief_fields(self.saved_brief, self.draft_brief)
        dirty = bool(changed)
        if self.confirmed_revision == self.revision and not dirty:
            status = "confirmed"
        elif self.confirmed_revision == self.revision and dirty:
            status = "confirmed_with_changes"
        elif self.had_confirmation:
            status = "needs_reconfirmation"
        else:
            status = "draft"
        active_impact = change_impact_fields(changed) or self.last_impact_fields
        return WorkspaceResponse(
            mode=self.mode,
            fixture_notice=(
                "本地测试模式：结构化 Brief 使用固定虚构夹具；"
                "页面状态来自 Python 会话与业务规则，未调用 AI。"
                if self.mode == "local_fixture"
                else "实时 AI 模式：Brief 来自 OpenAI structured output；"
                "仍需人工核实、保存并确认，不能视为事实或客户批准。"
            ),
            raw_text=self.raw_text,
            brief=self.draft_brief.model_copy(deep=True),
            selected_channels=list(self.selected_channels),
            questions=[item.model_copy(deep=True) for item in self.questions],
            revision=self.revision,
            confirmed_revision=self.confirmed_revision,
            status=status,
            dirty=dirty,
            changed_fields=sorted(changed),
            impact_fields=sorted(active_impact),
            unresolved_items=unresolved_clarifications(self.questions),
        )

    def patch_draft(self, patch: BriefDraftPatch) -> WorkspaceResponse:
        with self.lock:
            candidate = self.draft_brief.model_copy(update=patch.fields, deep=True)
            changed = changed_brief_fields(self.draft_brief, candidate)
            if changed:
                candidate = mark_user_sources(candidate, changed)
                self.draft_brief = reconcile_brief_issues(candidate, self.questions)
            return self.response()

    def update_question(self, question_id: str, request: ClarificationActionRequest) -> WorkspaceResponse:
        with self.lock:
            index = self._question_index(question_id)
            try:
                self.questions[index] = update_clarification(
                    self.questions[index], request.action, request.answer
                )
            except ValueError as exc:
                raise WorkspaceOperationError(
                    HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_clarification", str(exc)
                ) from exc
            self.saved_brief = reconcile_brief_issues(self.saved_brief, self.questions)
            self.draft_brief = reconcile_brief_issues(self.draft_brief, self.questions)
            return self.response()

    def apply_question(self, question_id: str) -> WorkspaceResponse:
        with self.lock:
            index = self._question_index(question_id)
            try:
                updated, applied = apply_clarification_answer(
                    self.draft_brief, self.questions[index]
                )
            except ValueError as exc:
                raise WorkspaceOperationError(
                    HTTPStatus.CONFLICT, "clarification_not_applicable", str(exc)
                ) from exc
            self.questions[index] = applied
            self.draft_brief = reconcile_brief_issues(updated, self.questions)
            self.saved_brief = reconcile_brief_issues(self.saved_brief, self.questions)
            return self.response()

    def save(self) -> WorkspaceResponse:
        with self.lock:
            candidate = reconcile_brief_issues(self.draft_brief, self.questions)
            saved, revision, confirmed, changed = save_brief_revision(
                self.saved_brief, candidate, self.revision, self.confirmed_revision
            )
            self.saved_brief = saved
            self.draft_brief = saved.model_copy(deep=True)
            self.revision = revision
            self.confirmed_revision = confirmed
            if changed:
                self.last_impact_fields = change_impact_fields(changed)
                if self.last_impact_fields:
                    reason = (
                        f"Brief v{self.revision} 的关键字段 "
                        f"{', '.join(sorted(self.last_impact_fields))} 已变化；整份交付物需要复审。"
                    )
                    self.packages = [
                        mark_package_stale(package, reason)
                        if package.lifecycle_status == "current" else package
                        for package in self.packages
                    ]
            return self.response()

    def confirm(self) -> WorkspaceResponse:
        with self.lock:
            if changed_brief_fields(self.saved_brief, self.draft_brief):
                raise WorkspaceOperationError(
                    HTTPStatus.CONFLICT,
                    "unsaved_changes",
                    "存在未保存修改，请先保存草稿再确认。",
                )
            self.confirmed_revision = self.revision
            self.had_confirmation = True
            self.last_impact_fields.clear()
            return self.response()

    def delivery_response(self, package_id: str | None = None) -> DeliverResponse:
        with self.lock:
            selected = None
            target_id = package_id or self.selected_package_id
            if target_id:
                selected = self._package(target_id)
                self.selected_package_id = selected.package_id
            elif self.packages:
                selected = self.packages[-1]
                self.selected_package_id = selected.package_id

            workspace = self.response()
            can_generate = workspace.status == "confirmed" and not workspace.dirty
            if can_generate:
                blocker = ""
            elif workspace.dirty:
                blocker = "存在未保存修改，请先保存并重新确认 Brief。"
            else:
                blocker = "当前 Brief 尚未人工确认或确认已失效。"
            unresolved = self._package_unresolved(selected) if selected else workspace.unresolved_items
            return DeliverResponse(
                mode=self.mode,
                fixture_notice=(
                    "本地固定测试交付物：未调用 AI，不代表客户、市场或法律批准。"
                    if self.mode == "local_fixture"
                    else "实时 AI 交付工作稿：已调用 OpenAI；仍不代表客户、市场或法律批准。"
                ),
                package=selected.model_copy(deep=True) if selected else None,
                selected_package_id=selected.package_id if selected else None,
                history=[
                    PackageSummary(
                        package_id=item.package_id,
                        source_brief_revision=item.source_brief_revision,
                        content_revision=item.content_revision,
                        review_status=item.review_status,
                        lifecycle_status=item.lifecycle_status,
                        generated_at=item.generated_at,
                        stale_reason=item.stale_reason,
                    )
                    for item in reversed(self.packages)
                ],
                latest_brief_revision=self.revision,
                latest_brief_status=workspace.status,
                can_generate=can_generate,
                generation_blocker=blocker,
                unresolved_items=unresolved,
            )

    def generate_delivery(
        self,
        generator: Callable[[list[str]], GeneratedDraftPackage | DraftPackage] | None = None,
    ) -> DeliverResponse:
        with self.lock:
            workspace = self.response()
            if workspace.status != "confirmed" or workspace.dirty:
                raise WorkspaceOperationError(
                    HTTPStatus.CONFLICT,
                    "brief_not_confirmed",
                    "只有已保存且当前人工确认的 Brief 才能生成交付物。",
                )
            current = self.packages[-1] if self.packages else None
            selected_generator = generator or build_fixture_drafts

            def create_package() -> DraftPackage:
                generated = selected_generator(list(self.selected_channels))
                if isinstance(generated, DraftPackage):
                    return generated.model_copy(deep=True)
                return bind_draft_package(
                    generated,
                    self.saved_brief,
                    self.revision,
                    self.questions,
                )

            package, error = replace_package_safely(
                current,
                create_package,
            )
            if isinstance(error, WorkspaceOperationError):
                raise error
            if error or package is None or package is current:
                raise WorkspaceOperationError(
                    HTTPStatus.BAD_GATEWAY,
                    "generation_failed",
                    f"本地测试稿生成失败：{error or '未返回新交付物'}",
                )
            package = package.model_copy(update={
                "package_id": f"pkg-{uuid.uuid4().hex[:10]}",
                "generated_at": datetime.now(UTC).isoformat(),
                "generation_mode": self.mode,
                "content_revision": 1,
                "reviewed_content_revision": None,
                "review_status": "草稿 — 未审核",
                "lifecycle_status": "current",
                "stale_reason": "",
            }, deep=True)
            self.packages.append(package)
            self.selected_package_id = package.package_id
            return self.delivery_response(package.package_id)

    def patch_delivery(self, request: DeliverDraftPatch) -> DeliverResponse:
        with self.lock:
            package_index, package = self._package_with_index(request.package_id)
            drafts = [item.model_copy(deep=True) for item in package.drafts]
            target_index = next(
                (index for index, draft in enumerate(drafts) if draft.channel == request.channel),
                None,
            )
            if target_index is None:
                raise WorkspaceOperationError(
                    HTTPStatus.NOT_FOUND, "channel_not_found", "该交付包中不存在指定渠道"
                )
            if drafts[target_index].body == request.body:
                return self.delivery_response(package.package_id)
            drafts[target_index] = drafts[target_index].model_copy(update={
                "body": request.body,
                "chinese_summary_status": "pending_update",
            })
            review_status = "需要修改" if package.lifecycle_status == "stale" else "草稿 — 未审核"
            updated = package.model_copy(update={
                "drafts": drafts,
                "content_revision": package.content_revision + 1,
                "reviewed_content_revision": None,
                "review_status": review_status,
            }, deep=True)
            self.packages[package_index] = updated
            return self.delivery_response(updated.package_id)

    def review_delivery(self, request: DeliverReviewRequest) -> DeliverResponse:
        with self.lock:
            package_index, package = self._package_with_index(request.package_id)
            if request.status == "内部审核完成" and package.lifecycle_status == "stale":
                raise WorkspaceOperationError(
                    HTTPStatus.CONFLICT,
                    "stale_package",
                    "过期交付物不能标记为当前内部审核完成；可保留或导出并重新生成。",
                )
            reviewed_revision = (
                package.content_revision if request.status == "内部审核完成" else None
            )
            updated = package.model_copy(update={
                "review_status": request.status,
                "reviewed_content_revision": reviewed_revision,
            }, deep=True)
            self.packages[package_index] = updated
            return self.delivery_response(updated.package_id)

    def export_delivery(self, package_id: str, export_format: str) -> tuple[bytes, str, str]:
        with self.lock:
            package = self._package(package_id)
            unresolved = self._package_unresolved(package)
            warning = (
                "内部探索稿；不得视为客户、市场或法律批准。"
                if package.review_status != "内部审核完成" or package.lifecycle_status == "stale"
                else "仅完成内部人工审核；不代表客户、市场或法律批准。"
            )
            if export_format == "markdown":
                content = export_markdown(
                    package.source_brief_snapshot or self.saved_brief,
                    package,
                    package.review_status,
                    package.source_brief_revision,
                    unresolved,
                )
                content += (
                    "\n\n## Export risk notice\n"
                    f"- {warning}\n"
                    f"- Stale reason: {package.stale_reason or 'None'}\n"
                    "- Unverified marketing statements must remain unverified until independently checked.\n"
                )
                return (
                    content.encode("utf-8"),
                    f"briefpilot-{package.package_id}.md",
                    "text/markdown; charset=utf-8",
                )
            if export_format == "json":
                payload = {
                    "purpose": "Internal creative review; not approved for automatic publishing",
                    "warning": warning,
                    "brief_version": package.source_brief_revision,
                    "review_status": package.review_status,
                    "lifecycle_status": package.lifecycle_status,
                    "unresolved_items": unresolved,
                    "risk_notes": [
                        "客户提供的信息不等于事实已核实。",
                        "过期或未完成内部审核的稿件不得作为正式批准交付物。",
                    ],
                    "package": package.model_dump(mode="json"),
                }
                return (
                    json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
                    f"briefpilot-{package.package_id}.json",
                    "application/json; charset=utf-8",
                )
            raise WorkspaceOperationError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "invalid_export_format",
                "导出格式仅支持 markdown 或 json",
            )

    def _package_unresolved(self, package: DraftPackage | None) -> list[str]:
        if package is None:
            return []
        brief = package.source_brief_snapshot
        items = list(brief.missing_information if brief else [])
        items.extend(unresolved_clarifications(package.clarification_snapshot))
        return list(dict.fromkeys(items))

    def _package(self, package_id: str) -> DraftPackage:
        return self._package_with_index(package_id)[1]

    def _package_with_index(self, package_id: str) -> tuple[int, DraftPackage]:
        for index, package in enumerate(self.packages):
            if package.package_id == package_id:
                return index, package
        raise WorkspaceOperationError(
            HTTPStatus.NOT_FOUND, "package_not_found", "交付物不存在"
        )

    def _question_index(self, question_id: str) -> int:
        for index, question in enumerate(self.questions):
            if question.id == question_id:
                return index
        raise WorkspaceOperationError(
            HTTPStatus.NOT_FOUND, "question_not_found", "澄清问题不存在"
        )


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, WorkspaceSession] = {}
        self._lock = threading.RLock()

    def replace(
        self,
        session_id: str | None,
        request: CaptureAnalyzeRequest,
        brief: Brief | None = None,
    ) -> tuple[str, WorkspaceSession]:
        session_id = session_id or uuid.uuid4().hex
        session = WorkspaceSession.from_capture(request, brief)
        with self._lock:
            self._sessions[session_id] = session
        return session_id, session

    def get(self, session_id: str | None) -> WorkspaceSession:
        if not session_id:
            raise WorkspaceOperationError(
                HTTPStatus.NOT_FOUND, "session_not_found", "尚无 Capture 工作状态，请先分析需求。"
            )
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise WorkspaceOperationError(
                HTTPStatus.NOT_FOUND,
                "session_expired",
                "本地会话不存在或服务已重启，请返回 Capture 重新分析。",
            )
        return session


def build_fixture_response(request: CaptureAnalyzeRequest) -> CaptureAnalyzeResponse:
    """Compatibility helper used by tests and non-HTTP callers."""
    if request.mode != "local_fixture":
        raise ValueError("build_fixture_response 仅用于 local_fixture 模式")
    return WorkspaceSession.from_capture(request).response()


class LocalIntegrationHandler(SimpleHTTPRequestHandler):
    server_version = "BriefPilotLocalIntegration/4.0"

    @property
    def session_store(self) -> SessionStore:
        return self.server.session_store  # type: ignore[attr-defined]

    @property
    def ai_adapter(self) -> LiveAIAdapter:
        return self.server.ai_adapter  # type: ignore[attr-defined]

    @property
    def live_ai_enabled(self) -> bool:
        return self.server.live_ai_enabled  # type: ignore[attr-defined]

    def _require_live_ai_enabled(self) -> None:
        if not self.live_ai_enabled:
            raise WorkspaceOperationError(
                HTTPStatus.FORBIDDEN,
                "live_ai_disabled",
                "公开演示仅支持 Local Fixture；服务端未调用 OpenAI。",
            )

    def _session_id(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def _write_json(
        self, status: HTTPStatus, payload: dict, session_id: str | None = None
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if session_id:
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE}={session_id}; Path=/; HttpOnly; SameSite=Strict",
            )
        self.end_headers()
        self.wfile.write(body)

    def _write_error(self, error: WorkspaceOperationError) -> None:
        payload = {"code": error.code, "message": error.message}
        if error.correlation_id:
            payload["correlation_id"] = error.correlation_id
        self._write_json(
            error.status,
            {"error": payload},
        )

    def _write_download(self, body: bytes, filename: str, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_model(self, model_type: type[BaseModel]) -> BaseModel:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            raise WorkspaceOperationError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "invalid_size",
                "请求内容为空或过大",
            )
        try:
            payload = json.loads(self.rfile.read(content_length))
            return model_type.model_validate(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise WorkspaceOperationError(
                HTTPStatus.BAD_REQUEST, "invalid_json", "请求不是有效的 JSON"
            ) from exc
        except ValidationError as exc:
            raise WorkspaceOperationError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "validation_error",
                "输入不符合接口要求",
            ) from exc

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            live_ai_enabled = self.live_ai_enabled
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "modes": (
                        ["local_fixture", "live_ai"]
                        if live_ai_enabled
                        else ["local_fixture"]
                    ),
                    "public_demo": not live_ai_enabled,
                    "live_ai_enabled": live_ai_enabled,
                    "live_ai_configured": (
                        self.ai_adapter.configured if live_ai_enabled else False
                    ),
                },
            )
            return
        if path == "/api/workspace":
            try:
                response = self.session_store.get(self._session_id()).response()
                self._write_json(HTTPStatus.OK, response.model_dump(mode="json"))
            except WorkspaceOperationError as exc:
                self._write_error(exc)
            return
        if path in {"/api/deliver", "/api/deliver/export"}:
            try:
                query = parse_qs(parsed.query)
                session = self.session_store.get(self._session_id())
                package_id = query.get("package_id", [None])[0]
                if path == "/api/deliver":
                    response = session.delivery_response(package_id)
                    self._write_json(HTTPStatus.OK, response.model_dump(mode="json"))
                else:
                    if not package_id:
                        raise WorkspaceOperationError(
                            HTTPStatus.UNPROCESSABLE_ENTITY,
                            "package_required",
                            "导出需要指定交付物",
                        )
                    export_format = query.get("format", ["markdown"])[0]
                    body, filename, content_type = session.export_delivery(
                        package_id, export_format
                    )
                    self._write_download(body, filename, content_type)
            except WorkspaceOperationError as exc:
                self._write_error(exc)
            return
        super().do_GET()

    def do_PATCH(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path not in {"/api/brief/draft", "/api/deliver/draft"}:
            self._write_error(WorkspaceOperationError(HTTPStatus.NOT_FOUND, "not_found", "接口不存在"))
            return
        try:
            session = self.session_store.get(self._session_id())
            if path == "/api/brief/draft":
                request = self._read_json_model(BriefDraftPatch)
                response = session.patch_draft(request)
            else:
                request = self._read_json_model(DeliverDraftPatch)
                response = session.patch_delivery(request)
            self._write_json(HTTPStatus.OK, response.model_dump(mode="json"))
        except WorkspaceOperationError as exc:
            self._write_error(exc)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/capture/analyze":
                request = self._read_json_model(CaptureAnalyzeRequest)
                if request.mode == "live_ai":
                    self._require_live_ai_enabled()
                    brief = self.ai_adapter.analyze(request)
                else:
                    brief = None
                session_id, session = self.session_store.replace(
                    self._session_id(), request, brief
                )
                self._write_json(
                    HTTPStatus.OK, session.response().model_dump(mode="json"), session_id
                )
                return

            session = self.session_store.get(self._session_id())
            if path == "/api/brief/save":
                response = session.save()
            elif path == "/api/brief/confirm":
                response = session.confirm()
            elif path == "/api/deliver/generate":
                if session.mode == "live_ai":
                    self._require_live_ai_enabled()
                generator = (
                    (lambda _channels: self.ai_adapter.generate(session))
                    if session.mode == "live_ai"
                    else None
                )
                response = session.generate_delivery(generator)
            elif path == "/api/deliver/review":
                request = self._read_json_model(DeliverReviewRequest)
                response = session.review_delivery(request)
            else:
                match = re.fullmatch(r"/api/clarifications/([^/]+)(/apply)?", path)
                if not match:
                    raise WorkspaceOperationError(HTTPStatus.NOT_FOUND, "not_found", "接口不存在")
                question_id, apply_suffix = match.groups()
                if apply_suffix:
                    response = session.apply_question(question_id)
                else:
                    request = self._read_json_model(ClarificationActionRequest)
                    response = session.update_question(question_id, request)
            self._write_json(HTTPStatus.OK, response.model_dump(mode="json"))
        except WorkspaceOperationError as exc:
            self._write_error(exc)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8767,
    session_store: SessionStore | None = None,
    ai_adapter: LiveAIAdapter | None = None,
    live_ai_enabled: bool = True,
) -> ThreadingHTTPServer:
    handler = partial(LocalIntegrationHandler, directory=str(PROTOTYPE_DIR))
    server = ThreadingHTTPServer((host, port), handler)
    server.session_store = session_store or SessionStore()  # type: ignore[attr-defined]
    server.ai_adapter = ai_adapter or LiveAIAdapter()  # type: ignore[attr-defined]
    server.live_ai_enabled = live_ai_enabled  # type: ignore[attr-defined]
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="BriefPilot local integration")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    port = args.port if args.port is not None else server_port_from_environment()
    fixture_only = public_demo_enabled()
    server = create_server(args.host, port, live_ai_enabled=not fixture_only)
    mode_status = (
        "已禁用（公开演示仅使用 Local Fixture）"
        if fixture_only
        else ("已配置" if server.ai_adapter.configured else "未配置")
    )
    print(f"BriefPilot 本地服务（fixture 默认；live_ai {mode_status}）")
    print(f"打开：http://{args.host}:{server.server_address[1]}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
