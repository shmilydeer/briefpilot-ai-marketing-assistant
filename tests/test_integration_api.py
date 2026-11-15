import http.client
import json
import re
import threading
from pathlib import Path

import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    BadRequestError,
    ContentFilterFinishReasonError,
    InternalServerError,
    LengthFinishReasonError,
    NotFoundError,
    PermissionDeniedError,
)

from integration_api import (
    BriefDraftPatch,
    CaptureAnalyzeRequest,
    ClarificationActionRequest,
    DeliverDraftPatch,
    DeliverReviewRequest,
    LIVE_AI_LOG_PATH,
    LOGGER,
    LiveAIAdapter,
    SessionStore,
    WorkspaceOperationError,
    WorkspaceSession,
    build_fixture_brief,
    build_fixture_drafts,
    build_fixture_response,
    create_server,
    public_demo_enabled,
    server_port_from_environment,
)
from logic import bind_draft_package
from models import Brief


def capture_request(market="UK", channels=None):
    return CaptureAnalyzeRequest(
        raw_text="在英国推广一款轻量随行杯，建立新品认知，不得添加未提供的认证信息。",
        market=market,
        channels=channels or ["TikTok", "Instagram"],
    )


def confirmed_session(market="UK", channels=None):
    session = WorkspaceSession.from_capture(capture_request(market, channels))
    session.confirm()
    return session


def test_fixture_response_is_brief_compatible_and_preserves_configuration():
    response = build_fixture_response(capture_request("US", ["TikTok"]))
    assert response.mode == "local_fixture"
    assert isinstance(response.brief, Brief)
    assert response.brief.region == "美国（US）"
    assert response.selected_channels == ["TikTok"]
    assert "未调用 AI" in response.fixture_notice
    assert response.brief.field_sources["region"].source_type == "user_entered"


def test_answer_does_not_change_brief_until_explicit_apply():
    session = WorkspaceSession.from_capture(capture_request("unknown", ["TikTok"]))
    question = session.questions[0]
    original = session.draft_brief.region
    answered = session.update_question(
        question.id, ClarificationActionRequest(action="answer", answer="美国（US）")
    )
    assert answered.questions[0].status == "answered"
    assert answered.brief.region == original

    applied = session.apply_question(question.id)
    assert applied.brief.region == "美国（US）"
    assert applied.questions[0].status == "applied"
    assert applied.brief.field_sources["region"].source_type == "user_entered"


def test_save_and_confirm_are_separate_and_identical_save_does_not_bump_revision():
    session = WorkspaceSession.from_capture(capture_request())
    unchanged = session.save()
    assert unchanged.revision == 1
    assert unchanged.confirmed_revision is None

    confirmed = session.confirm()
    assert confirmed.status == "confirmed"
    assert confirmed.confirmed_revision == 1


def test_core_change_bumps_revision_and_invalidates_confirmation():
    session = WorkspaceSession.from_capture(capture_request())
    session.confirm()
    draft = session.patch_draft(BriefDraftPatch(fields={"campaign_goal": "推动新品试用"}))
    assert draft.status == "confirmed_with_changes"
    assert draft.impact_fields == ["campaign_goal"]
    with pytest.raises(WorkspaceOperationError) as error:
        session.confirm()
    assert error.value.code == "unsaved_changes"

    saved = session.save()
    assert saved.revision == 2
    assert saved.confirmed_revision is None
    assert saved.status == "needs_reconfirmation"
    assert saved.impact_fields == ["campaign_goal"]


def test_failed_operation_keeps_saved_workspace_state():
    session = WorkspaceSession.from_capture(capture_request())
    before = session.response()
    with pytest.raises(WorkspaceOperationError):
        session.apply_question(session.questions[0].id)
    after = session.response()
    assert after.brief == before.brief
    assert after.revision == before.revision
    assert after.questions == before.questions


@pytest.fixture
def local_server():
    server = create_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def http_json(port, method, path, payload=None, cookie=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {}
    if body is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    if cookie:
        headers["Cookie"] = cookie
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    data = json.loads(response.read())
    set_cookie = response.getheader("Set-Cookie")
    connection.close()
    return response.status, data, set_cookie


def http_download(port, path, cookie=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    headers = {"Cookie": cookie} if cookie else {}
    connection.request("GET", path, headers=headers)
    response = connection.getresponse()
    body = response.read()
    content_type = response.getheader("Content-Type")
    connection.close()
    return response.status, body, content_type


def test_capture_creates_cookie_session_and_workspace_survives_refresh(local_server):
    payload = capture_request().model_dump(mode="json")
    status, capture, set_cookie = http_json(local_server, "POST", "/api/capture/analyze", payload)
    cookie = set_cookie.split(";", 1)[0]
    assert status == 200
    assert capture["brief"]["region"] == "英国（UK）"

    status, refreshed, _ = http_json(local_server, "GET", "/api/workspace", cookie=cookie)
    assert status == 200
    assert refreshed == capture


def test_capture_workspace_keeps_missing_information_available_for_questions():
    request = capture_request()
    brief = build_fixture_brief(request).model_copy(update={
        "assumptions": [],
        "missing_information": ["What is the call to action?"],
    })
    session = WorkspaceSession.from_capture(request, brief)
    assert session.saved_brief.missing_information == ["What is the call to action?"]
    assert [item.field_name for item in session.questions] == ["call_to_action"]


def test_clarify_question_count_copy_distinguishes_empty_from_completed():
    source = (
        Path(__file__).parents[1] / "design_prototype" / "clarify.js"
    ).read_text(encoding="utf-8")
    assert "if (!questions.length) return '暂无澄清问题';" in source
    assert "return unresolved ? `${unresolved} 项待处理` : '全部已处理';" in source
    assert "questionCountText(state.questions)" in source


def test_deliver_frontend_localizes_unresolved_status_without_changing_export_data():
    source = (
        Path(__file__).parents[1] / "design_prototype" / "deliver.js"
    ).read_text(encoding="utf-8")
    assert "function formatUnresolvedItem(item)" in source
    assert "deferred: '已暂缓'" in source
    assert "open: '待处理'" in source
    assert "not_applicable: '不适用'" in source
    assert "formatUnresolvedItem(item)" in source
    assert "state.unresolved_items" in source


def test_different_browser_sessions_are_isolated(local_server):
    uk_status, _, uk_cookie = http_json(
        local_server, "POST", "/api/capture/analyze", capture_request("UK").model_dump(mode="json")
    )
    us_status, _, us_cookie = http_json(
        local_server,
        "POST",
        "/api/capture/analyze",
        capture_request("US", ["TikTok"]).model_dump(mode="json"),
    )
    _, uk_state, _ = http_json(local_server, "GET", "/api/workspace", cookie=uk_cookie.split(";", 1)[0])
    _, us_state, _ = http_json(local_server, "GET", "/api/workspace", cookie=us_cookie.split(";", 1)[0])
    assert uk_status == us_status == 200
    assert uk_state["brief"]["region"] == "英国（UK）"
    assert us_state["brief"]["region"] == "美国（US）"
    assert us_state["selected_channels"] == ["TikTok"]


def test_http_clarification_answer_and_apply_are_distinct(local_server):
    _, capture, set_cookie = http_json(
        local_server, "POST", "/api/capture/analyze", capture_request().model_dump(mode="json")
    )
    cookie = set_cookie.split(";", 1)[0]
    question_id = capture["questions"][0]["id"]

    status, answered, _ = http_json(
        local_server,
        "POST",
        f"/api/clarifications/{question_id}",
        {"action": "answer", "answer": "Northstar"},
        cookie,
    )
    assert status == 200
    assert answered["brief"]["campaign_goal"] == "建立新品认知"
    assert answered["questions"][0]["status"] == "answered"

    status, applied, _ = http_json(
        local_server, "POST", f"/api/clarifications/{question_id}/apply", cookie=cookie
    )
    assert status == 200
    assert applied["brief"]["campaign_goal"] == "Northstar"
    assert applied["dirty"] is True


def test_http_invalid_write_does_not_erase_saved_state(local_server):
    _, capture, set_cookie = http_json(
        local_server, "POST", "/api/capture/analyze", capture_request().model_dump(mode="json")
    )
    cookie = set_cookie.split(";", 1)[0]
    status, error, _ = http_json(
        local_server,
        "PATCH",
        "/api/brief/draft",
        {"fields": {"not_a_brief_field": "bad"}},
        cookie,
    )
    assert status == 422
    assert error["error"]["code"] == "validation_error"
    _, after, _ = http_json(local_server, "GET", "/api/workspace", cookie=cookie)
    assert after == capture


def test_service_restart_boundary_is_explicit(local_server):
    _, _, set_cookie = http_json(
        local_server, "POST", "/api/capture/analyze", capture_request().model_dump(mode="json")
    )
    stale_cookie = set_cookie.split(";", 1)[0]
    empty_store_server = create_server(port=0, session_store=SessionStore())
    thread = threading.Thread(target=empty_store_server.serve_forever, daemon=True)
    thread.start()
    try:
        status, data, _ = http_json(
            empty_store_server.server_address[1], "GET", "/api/workspace", cookie=stale_cookie
        )
        assert status == 404
        assert data["error"]["code"] == "session_expired"
    finally:
        empty_store_server.shutdown()
        empty_store_server.server_close()
        thread.join(timeout=2)


def test_unconfirmed_brief_cannot_generate_delivery():
    session = WorkspaceSession.from_capture(capture_request())
    with pytest.raises(WorkspaceOperationError) as error:
        session.generate_delivery()
    assert error.value.code == "brief_not_confirmed"
    assert session.packages == []


def test_confirmed_brief_generates_fixture_bound_to_independent_snapshot():
    session = confirmed_session()
    result = session.generate_delivery()
    package = result.package
    assert package is not None
    assert package.generation_mode == "local_fixture"
    assert package.source_brief_revision == 1
    assert package.source_brief_snapshot == session.saved_brief
    assert package.source_brief_snapshot is not session.saved_brief
    assert [draft.channel for draft in package.drafts] == ["TikTok", "Instagram"]
    assert package.clarification_snapshot == session.questions
    assert package.clarification_snapshot is not session.questions


def test_delivery_response_uses_package_snapshots_for_all_three_sections():
    session = confirmed_session("US", ["TikTok"])
    package = session.generate_delivery().package
    assert package is not None
    response = session.delivery_response(package.package_id)
    assert response.package.source_brief_snapshot.region == "美国（US）"
    assert response.package.clarification_snapshot[0].id == session.questions[0].id
    assert [draft.channel for draft in response.package.drafts] == ["TikTok"]
    assert response.unresolved_items


def test_editing_english_copy_invalidates_review_and_marks_summary_pending():
    session = confirmed_session()
    package = session.generate_delivery().package
    session.review_delivery(
        DeliverReviewRequest(package_id=package.package_id, status="内部审核完成")
    )
    edited = session.patch_delivery(
        DeliverDraftPatch(
            package_id=package.package_id,
            channel="TikTok",
            body="A manually revised English test draft.",
        )
    ).package
    assert edited.review_status == "草稿 — 未审核"
    assert edited.content_revision == 2
    assert edited.reviewed_content_revision is None
    tiktok = next(item for item in edited.drafts if item.channel == "TikTok")
    assert tiktok.body == "A manually revised English test draft."
    assert tiktok.chinese_summary_status == "pending_update"


def test_critical_brief_change_marks_existing_package_stale_with_reason():
    session = confirmed_session()
    package_id = session.generate_delivery().package.package_id
    session.patch_draft(BriefDraftPatch(fields={"audience": "英国城市通勤人群"}))
    saved = session.save()
    stale = session.delivery_response(package_id).package
    assert saved.revision == 2
    assert saved.status == "needs_reconfirmation"
    assert stale.lifecycle_status == "stale"
    assert stale.review_status == "需要修改"
    assert "audience" in stale.stale_reason
    assert stale.source_brief_revision == 1


def test_noncritical_brief_change_does_not_mark_package_stale():
    session = confirmed_session()
    package_id = session.generate_delivery().package.package_id
    session.patch_draft(BriefDraftPatch(fields={"tone": "克制、清晰、自然"}))
    session.save()
    assert session.delivery_response(package_id).package.lifecycle_status == "current"


def test_new_generation_preserves_old_package_history():
    session = confirmed_session()
    old = session.generate_delivery().package
    session.patch_draft(BriefDraftPatch(fields={"campaign_goal": "建立英国市场新品认知"}))
    session.save()
    session.confirm()
    new = session.generate_delivery().package
    assert new.package_id != old.package_id
    assert new.source_brief_revision == 2
    assert len(session.packages) == 2
    assert session.delivery_response(old.package_id).package.lifecycle_status == "stale"
    assert session.delivery_response(new.package_id).package.lifecycle_status == "current"


def test_failed_regeneration_keeps_existing_package_unchanged():
    session = confirmed_session()
    old = session.generate_delivery().package.model_copy(deep=True)

    def failing_generator(_channels):
        raise RuntimeError("fixture failure")

    with pytest.raises(WorkspaceOperationError) as error:
        session.generate_delivery(generator=failing_generator)
    assert error.value.code == "generation_failed"
    assert len(session.packages) == 1
    assert session.packages[0] == old


def test_exporting_old_package_uses_old_brief_snapshot():
    session = confirmed_session()
    old = session.generate_delivery().package
    old_goal = old.source_brief_snapshot.campaign_goal
    session.patch_draft(BriefDraftPatch(fields={"campaign_goal": "完全不同的新目标"}))
    session.save()
    markdown, _, _ = session.export_delivery(old.package_id, "markdown")
    text = markdown.decode("utf-8")
    assert old_goal in text
    assert "完全不同的新目标" not in text
    assert f"Brief version: v{old.source_brief_revision}" in text
    assert "Package status: stale" in text


def test_markdown_and_json_exports_match_server_package_state():
    session = confirmed_session()
    package = session.generate_delivery().package
    session.review_delivery(
        DeliverReviewRequest(package_id=package.package_id, status="内部审核完成")
    )
    markdown, markdown_name, markdown_type = session.export_delivery(
        package.package_id, "markdown"
    )
    json_bytes, json_name, json_type = session.export_delivery(package.package_id, "json")
    markdown_text = markdown.decode("utf-8")
    exported = json.loads(json_bytes)
    assert package.package_id in markdown_name
    assert markdown_type.startswith("text/markdown")
    assert "Review status: 内部审核完成" in markdown_text
    assert "Package status: current" in markdown_text
    assert package.package_id in json_name
    assert json_type.startswith("application/json")
    assert exported["brief_version"] == package.source_brief_revision
    assert exported["review_status"] == "内部审核完成"
    assert exported["lifecycle_status"] == "current"
    assert exported["package"]["package_id"] == package.package_id
    assert exported["unresolved_items"]


def test_http_deliver_flow_survives_refresh_and_navigation(local_server):
    _, _, set_cookie = http_json(
        local_server, "POST", "/api/capture/analyze", capture_request().model_dump(mode="json")
    )
    cookie = set_cookie.split(";", 1)[0]
    status, confirmed, _ = http_json(local_server, "POST", "/api/brief/confirm", cookie=cookie)
    assert status == 200
    assert confirmed["status"] == "confirmed"

    status, generated, _ = http_json(
        local_server, "POST", "/api/deliver/generate", cookie=cookie
    )
    package_id = generated["package"]["package_id"]
    assert status == 200
    assert generated["package"]["source_brief_revision"] == 1

    status, refreshed, _ = http_json(
        local_server, "GET", f"/api/deliver?package_id={package_id}", cookie=cookie
    )
    assert status == 200
    assert refreshed == generated

    status, workspace, _ = http_json(local_server, "GET", "/api/workspace", cookie=cookie)
    assert status == 200
    assert workspace["status"] == "confirmed"
    status, returned, _ = http_json(local_server, "GET", "/api/deliver", cookie=cookie)
    assert status == 200
    assert returned["package"]["package_id"] == package_id


def test_http_failed_deliver_write_keeps_saved_package(local_server):
    _, _, set_cookie = http_json(
        local_server, "POST", "/api/capture/analyze", capture_request().model_dump(mode="json")
    )
    cookie = set_cookie.split(";", 1)[0]
    http_json(local_server, "POST", "/api/brief/confirm", cookie=cookie)
    _, generated, _ = http_json(local_server, "POST", "/api/deliver/generate", cookie=cookie)
    package_id = generated["package"]["package_id"]

    status, error, _ = http_json(
        local_server,
        "PATCH",
        "/api/deliver/draft",
        {"package_id": package_id, "channel": "YouTube", "body": "bad"},
        cookie,
    )
    assert status == 422
    assert error["error"]["code"] == "validation_error"
    _, after, _ = http_json(
        local_server, "GET", f"/api/deliver?package_id={package_id}", cookie=cookie
    )
    assert after == generated


class RecordingAIAdapter:
    def __init__(self, fail_analyze=False, fail_generate=False):
        self.configured = True
        self.fail_analyze = fail_analyze
        self.fail_generate = fail_generate
        self.analyze_calls = 0
        self.generate_calls = 0

    def analyze(self, request):
        self.analyze_calls += 1
        if self.fail_analyze:
            raise WorkspaceOperationError(502, "mock_ai_failure", "模拟 AI 解析失败")
        return build_fixture_brief(request)

    def generate(self, session):
        self.generate_calls += 1
        if self.fail_generate:
            raise WorkspaceOperationError(502, "mock_ai_failure", "模拟 AI 生成失败")
        return bind_draft_package(
            build_fixture_drafts(session.selected_channels),
            session.saved_brief,
            session.revision,
            session.questions,
        )


@pytest.fixture
def server_factory():
    running = []

    def start(adapter=None, **server_options):
        server = create_server(port=0, ai_adapter=adapter, **server_options)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        running.append((server, thread))
        return server.server_address[1]

    yield start
    for server, thread in running:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_render_environment_enables_fixture_only_public_demo(monkeypatch):
    monkeypatch.delenv("BRIEFPILOT_PUBLIC_DEMO", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    assert public_demo_enabled() is False

    monkeypatch.setenv("BRIEFPILOT_PUBLIC_DEMO", "true")
    assert public_demo_enabled() is True

    monkeypatch.setenv("BRIEFPILOT_PUBLIC_DEMO", "false")
    monkeypatch.setenv("RENDER", "true")
    assert public_demo_enabled() is True


def test_server_port_uses_render_port_and_preserves_local_default(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    assert server_port_from_environment() == 8767

    monkeypatch.setenv("PORT", "10000")
    assert server_port_from_environment() == 10000

    monkeypatch.setenv("PORT", "not-a-port")
    with pytest.raises(ValueError, match="PORT"):
        server_port_from_environment()


def test_public_demo_is_fixture_only_and_never_reads_api_key(server_factory):
    key_reads = []

    def forbidden_key_read():
        key_reads.append(True)
        raise AssertionError("public demo must not read an API key")

    adapter = LiveAIAdapter(api_key_provider=forbidden_key_read)
    port = server_factory(adapter, live_ai_enabled=False)

    status, health, _ = http_json(port, "GET", "/api/health")
    assert status == 200
    assert health == {
        "status": "ok",
        "modes": ["local_fixture"],
        "public_demo": True,
        "live_ai_enabled": False,
        "live_ai_configured": False,
    }

    live_request = capture_request().model_copy(update={"mode": "live_ai"})
    status, error, _ = http_json(
        port, "POST", "/api/capture/analyze", live_request.model_dump(mode="json")
    )
    assert status == 403
    assert error["error"]["code"] == "live_ai_disabled"

    status, capture, set_cookie = http_json(
        port, "POST", "/api/capture/analyze", capture_request().model_dump(mode="json")
    )
    cookie = set_cookie.split(";", 1)[0]
    assert status == 200
    assert capture["mode"] == "local_fixture"
    assert http_json(port, "POST", "/api/brief/confirm", cookie=cookie)[0] == 200
    status, generated, _ = http_json(
        port, "POST", "/api/deliver/generate", cookie=cookie
    )
    assert status == 200
    package_id = generated["package"]["package_id"]
    export_status, markdown, content_type = http_download(
        port,
        f"/api/deliver/export?package_id={package_id}&format=markdown",
        cookie,
    )
    assert export_status == 200
    assert content_type.startswith("text/markdown")
    assert b"BriefPilot" in markdown
    assert key_reads == []


def test_public_demo_rejects_live_delivery_even_for_injected_live_session(server_factory):
    request = capture_request().model_copy(update={"mode": "live_ai"})
    store = SessionStore()
    session_id, session = store.replace(None, request, build_fixture_brief(request))
    session.confirm()
    adapter = RecordingAIAdapter()
    port = server_factory(
        adapter,
        live_ai_enabled=False,
        session_store=store,
    )

    status, error, _ = http_json(
        port,
        "POST",
        "/api/deliver/generate",
        cookie=f"briefpilot_session={session_id}",
    )
    assert status == 403
    assert error["error"]["code"] == "live_ai_disabled"
    assert adapter.generate_calls == 0


def test_fixture_mode_never_calls_injected_ai_adapter(server_factory):
    adapter = RecordingAIAdapter(fail_analyze=True, fail_generate=True)
    port = server_factory(adapter)
    request = capture_request().model_copy(update={"mode": "local_fixture"})
    status, capture, set_cookie = http_json(
        port, "POST", "/api/capture/analyze", request.model_dump(mode="json")
    )
    cookie = set_cookie.split(";", 1)[0]
    assert status == 200
    assert capture["mode"] == "local_fixture"
    http_json(port, "POST", "/api/brief/confirm", cookie=cookie)
    status, generated, _ = http_json(port, "POST", "/api/deliver/generate", cookie=cookie)
    assert status == 200
    assert generated["package"]["generation_mode"] == "local_fixture"
    assert adapter.analyze_calls == adapter.generate_calls == 0


def test_live_ai_mode_calls_adapter_for_capture_and_deliver(server_factory):
    adapter = RecordingAIAdapter()
    port = server_factory(adapter)
    request = capture_request("US", ["TikTok"]).model_copy(update={"mode": "live_ai"})
    status, capture, set_cookie = http_json(
        port, "POST", "/api/capture/analyze", request.model_dump(mode="json")
    )
    cookie = set_cookie.split(";", 1)[0]
    assert status == 200
    assert capture["mode"] == "live_ai"
    assert capture["brief"]["region"] == "美国（US）"
    http_json(port, "POST", "/api/brief/confirm", cookie=cookie)
    status, generated, _ = http_json(port, "POST", "/api/deliver/generate", cookie=cookie)
    assert status == 200
    assert generated["mode"] == "live_ai"
    assert generated["package"]["generation_mode"] == "live_ai"
    assert adapter.analyze_calls == adapter.generate_calls == 1


def test_live_ai_missing_key_returns_clear_error_without_model_call(server_factory):
    parse_calls = []
    adapter = LiveAIAdapter(
        api_key_provider=lambda: "",
        parse_function=lambda *_args, **_kwargs: parse_calls.append(True),
    )
    port = server_factory(adapter)
    request = capture_request().model_copy(update={"mode": "live_ai"})
    status, error, _ = http_json(
        port, "POST", "/api/capture/analyze", request.model_dump(mode="json")
    )
    assert status == 503
    assert error["error"]["code"] == "openai_not_configured"
    assert "未调用 AI" in error["error"]["message"]
    assert parse_calls == []


def test_live_ai_capture_uses_validated_brief_and_conservative_sources():
    parsed = build_fixture_brief(capture_request("unknown"))
    parsed.field_sources = {}
    adapter = LiveAIAdapter(
        api_key_provider=lambda: "test-key-not-sent",
        parse_function=lambda _text, _key: parsed,
    )
    request = capture_request("US", ["TikTok"]).model_copy(update={"mode": "live_ai"})
    brief = adapter.analyze(request)
    assert isinstance(brief, Brief)
    assert brief.region == "美国（US）"
    assert brief.field_sources["region"].source_type == "user_entered"
    assert brief.field_sources["region"].verification_status == "pending"
    assert all(source.verification_status != "verified" for source in brief.field_sources.values())


def test_invalid_live_ai_response_is_rejected_safely():
    adapter = LiveAIAdapter(
        api_key_provider=lambda: "test-key-not-sent",
        parse_function=lambda _text, _key: {"product": "incomplete"},
    )
    request = capture_request().model_copy(update={"mode": "live_ai"})
    with pytest.raises(WorkspaceOperationError) as error:
        adapter.analyze(request)
    assert error.value.code == "invalid_ai_output"


def bare_openai_exception(exception_type, **attributes):
    error = exception_type.__new__(exception_type)
    Exception.__init__(error, "sensitive upstream detail")
    for name, value in attributes.items():
        setattr(error, name, value)
    return error


@pytest.mark.parametrize(
    ("exception_type", "expected_code", "expected_guidance"),
    [
        (APIConnectionError, "openai_connection_failed", "网络、代理或 TLS"),
        (BadRequestError, "openai_bad_request", "模型和请求参数"),
        (PermissionDeniedError, "openai_permission_denied", "项目和模型权限"),
        (NotFoundError, "openai_not_found", "模型配置"),
        (InternalServerError, "openai_server_error", "稍后手动重试"),
        (APIStatusError, "openai_status_error", "安全日志"),
        (LengthFinishReasonError, "openai_output_limit", "调整上限"),
        (ContentFilterFinishReasonError, "openai_content_filtered", "检查输入内容"),
    ],
)
def test_live_ai_errors_are_classified_without_sensitive_details(
    exception_type, expected_code, expected_guidance, caplog
):
    upstream = bare_openai_exception(
        exception_type,
        status_code=418,
        code="safe_test_code",
        param="response_format.json_schema.schema",
        request_id="req_safe_test",
    )
    adapter = LiveAIAdapter(
        api_key_provider=lambda: "test-key-not-sent",
        parse_function=lambda *_args: (_ for _ in ()).throw(upstream),
    )

    with caplog.at_level("ERROR", logger="briefpilot.live_ai"):
        with pytest.raises(WorkspaceOperationError) as error:
            adapter.analyze(capture_request())

    assert error.value.code == expected_code
    assert expected_guidance in error.value.message
    assert error.value.correlation_id.startswith("ai-")
    assert "sensitive upstream detail" not in error.value.message
    assert "stage=Capture" in caplog.text
    assert f"exception_type={exception_type.__name__}" in caplog.text
    assert "http_status=418" in caplog.text
    assert "openai_error_code=safe_test_code" in caplog.text
    assert "error_param=response_format.json_schema.schema" in caplog.text
    assert "request_id=req_safe_test" in caplog.text
    assert f"correlation_id={error.value.correlation_id}" in caplog.text
    assert "sensitive upstream detail" not in caplog.text

    for handler in LOGGER.handlers:
        handler.flush()
    matching_line = next(
        line
        for line in reversed(LIVE_AI_LOG_PATH.read_text(encoding="utf-8").splitlines())
        if error.value.correlation_id in line
    )
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z live_ai_error "
        r"stage=Capture exception_type=[A-Za-z]+ http_status=418 "
        r"openai_error_code=safe_test_code "
        r"error_param=response_format\.json_schema\.schema "
        r"request_id=req_safe_test correlation_id=ai-[0-9a-f]{12}",
        matching_line,
    )


def test_live_ai_error_rejects_unsafe_error_parameter(caplog):
    upstream = bare_openai_exception(
        BadRequestError,
        status_code=400,
        code="invalid_request_error",
        param="messages[0].content secret-value",
        request_id="req_safe_test",
    )
    adapter = LiveAIAdapter(
        api_key_provider=lambda: "test-key-not-sent",
        parse_function=lambda *_args: (_ for _ in ()).throw(upstream),
    )

    with caplog.at_level("ERROR", logger="briefpilot.live_ai"):
        with pytest.raises(WorkspaceOperationError):
            adapter.analyze(capture_request())

    assert "error_param= request_id=req_safe_test" in caplog.text
    assert "secret-value" not in caplog.text


def test_live_ai_error_payload_exposes_only_safe_diagnostic_fields(server_factory):
    upstream = bare_openai_exception(
        APIConnectionError,
        status_code=None,
        code=None,
        request_id=None,
    )
    adapter = LiveAIAdapter(
        api_key_provider=lambda: "test-key-not-sent",
        parse_function=lambda *_args: (_ for _ in ()).throw(upstream),
    )
    port = server_factory(adapter)
    request = capture_request().model_copy(update={"mode": "live_ai"})

    status, payload, _ = http_json(
        port, "POST", "/api/capture/analyze", request.model_dump(mode="json")
    )

    assert status == 502
    assert payload["error"]["code"] == "openai_connection_failed"
    assert payload["error"]["correlation_id"].startswith("ai-")
    assert "sensitive upstream detail" not in json.dumps(payload, ensure_ascii=False)


def test_live_ai_deliver_error_records_deliver_stage(caplog):
    upstream = bare_openai_exception(
        APIConnectionError,
        status_code=None,
        code=None,
        request_id=None,
    )
    request = capture_request().model_copy(update={"mode": "live_ai"})
    session = WorkspaceSession.from_capture(request, build_fixture_brief(request))
    adapter = LiveAIAdapter(
        api_key_provider=lambda: "test-key-not-sent",
        generate_function=lambda *_args, **_kwargs: (_ for _ in ()).throw(upstream),
    )

    with caplog.at_level("ERROR", logger="briefpilot.live_ai"):
        with pytest.raises(WorkspaceOperationError) as error:
            adapter.generate(session)

    assert error.value.code == "openai_connection_failed"
    assert "stage=Deliver" in caplog.text


def test_live_ai_missing_chinese_summary_is_not_fabricated():
    request = capture_request().model_copy(update={"mode": "live_ai"})
    brief = build_fixture_brief(request)
    session = WorkspaceSession.from_capture(request, brief)

    def generate_without_summary(
        source_brief, channels, _api_key, source_brief_revision, clarifications
    ):
        generated = build_fixture_drafts(channels)
        generated.drafts[0].chinese_summary = ""
        return bind_draft_package(
            generated, source_brief, source_brief_revision, clarifications
        )

    adapter = LiveAIAdapter(
        api_key_provider=lambda: "test-key-not-sent",
        generate_function=generate_without_summary,
    )
    package = adapter.generate(session)
    assert package.drafts[0].chinese_summary == ""
    assert package.drafts[0].chinese_summary_status == "pending_update"


def test_failed_live_capture_does_not_replace_existing_fixture_workspace(server_factory):
    adapter = RecordingAIAdapter(fail_analyze=True)
    port = server_factory(adapter)
    status, original, set_cookie = http_json(
        port, "POST", "/api/capture/analyze", capture_request().model_dump(mode="json")
    )
    cookie = set_cookie.split(";", 1)[0]
    assert status == 200
    live_request = capture_request("US", ["TikTok"]).model_copy(update={"mode": "live_ai"})
    status, error, _ = http_json(
        port, "POST", "/api/capture/analyze", live_request.model_dump(mode="json"), cookie
    )
    assert status == 502
    assert error["error"]["code"] == "mock_ai_failure"
    _, after, _ = http_json(port, "GET", "/api/workspace", cookie=cookie)
    assert after == original


def test_failed_live_generation_keeps_existing_package(server_factory):
    adapter = RecordingAIAdapter()
    port = server_factory(adapter)
    request = capture_request().model_copy(update={"mode": "live_ai"})
    _, _, set_cookie = http_json(
        port, "POST", "/api/capture/analyze", request.model_dump(mode="json")
    )
    cookie = set_cookie.split(";", 1)[0]
    http_json(port, "POST", "/api/brief/confirm", cookie=cookie)
    _, first, _ = http_json(port, "POST", "/api/deliver/generate", cookie=cookie)
    adapter.fail_generate = True
    status, error, _ = http_json(port, "POST", "/api/deliver/generate", cookie=cookie)
    assert status == 502
    assert error["error"]["code"] == "mock_ai_failure"
    _, after, _ = http_json(port, "GET", "/api/deliver", cookie=cookie)
    assert after["package"] == first["package"]
    assert after["history"] == first["history"]
