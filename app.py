"""BriefPilot v0.2 — human-reviewed marketing content workflow."""
import json
import os
import streamlit as st
from models import Brief
from logic import (
    parse_brief, generate_drafts, quality_checks, export_markdown,
    changed_brief_fields, change_impact_fields, save_brief_revision,
    create_clarification_questions, update_clarification,
    apply_clarification_answer, unresolved_clarifications,
    reconcile_brief_issues, mark_user_sources, mark_package_stale,
    replace_package_safely,
)

st.set_page_config(page_title="BriefPilot｜可信 AI Brief 工作台", page_icon="✦", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
html,body,[class*="css"],[data-testid="stApp"],[data-testid="stAppViewContainer"] {font-family:'DM Sans',sans-serif;background:#F7F8FC!important;}
.block-container {max-width:1240px;padding-top:.85rem;padding-bottom:3rem;}
h1,h2,h3 {letter-spacing:-.025em;color:#202333;}
h1 {font-size:2.45rem!important;line-height:1.16!important;}
h2 {font-size:1.45rem!important;}
[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"] {display:none!important;}
div.stButton>button[kind="primary"],div.stFormSubmitButton>button[kind="primary"] {background:#6058D8;border-color:#6058D8;border-radius:13px;color:white;box-shadow:0 6px 18px rgba(96,88,216,.18);}
div.stButton>button,div.stFormSubmitButton>button {border-radius:13px;min-height:2.8rem;border-color:#DADDEC;font-weight:600;transition:border-color .16s ease,box-shadow .16s ease,transform .16s ease;}
div.stButton>button:hover,div.stFormSubmitButton>button:hover {border-color:#8B83E8;box-shadow:0 7px 20px rgba(96,88,216,.14);}
[data-testid="stTextArea"] textarea,[data-testid="stTextInput"] input,[data-baseweb="select"]>div {border-radius:13px!important;background:#FFF!important;border-color:#DDE0ED!important;}
[data-testid="stTextArea"] textarea:focus,[data-testid="stTextInput"] input:focus {border-color:#776FE1!important;box-shadow:0 0 0 3px rgba(96,88,216,.12)!important;}
div[data-testid="stAlert"] {border-radius:14px;border-width:1px;}
[data-testid="stVerticalBlockBorderWrapper"] {background:#FFF;border:1px solid #E4E6F0!important;border-radius:20px!important;box-shadow:0 10px 30px rgba(41,45,76,.055);}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.bp-capture-anchor) {border-color:#E1E3EF!important;border-radius:24px!important;box-shadow:0 18px 55px rgba(44,48,84,.09);padding:8px 10px 4px;}
[data-testid="stTabs"] [data-baseweb="tab-list"] {gap:8px;background:#EDEAFF;padding:5px;border-radius:14px;}
[data-testid="stTabs"] [data-baseweb="tab"] {border-radius:10px;padding:8px 16px;}
[data-testid="stTabs"] [aria-selected="true"] {background:#FFF;color:#443AAE;box-shadow:0 2px 8px rgba(47,43,98,.10);}
.bp-kicker {text-transform:uppercase;font-size:11px;font-weight:700;letter-spacing:.17em;color:#6058D8;}
.bp-hero {font-size:15px;color:#686C7D;margin-top:-4px;margin-bottom:22px;}
.bp-rail {display:flex;gap:8px;margin:14px 0 28px;flex-wrap:wrap;}
.bp-stage {border:1px solid #E1E3ED;background:#FFF;padding:9px 15px;border-radius:100px;font-size:13px;color:#747789;}
.bp-active {background:#EDEAFF;border-color:#CFC9FF;color:#443AAE;font-weight:700;}
.bp-done {background:#F1F7F3;border-color:#CBE5D2;color:#33724A;}
.bp-summary {display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:-4px 0 22px;}
.bp-pill {display:inline-flex;align-items:center;padding:6px 10px;border-radius:999px;background:#FFF;border:1px solid #E1E3ED;color:#55596C;font-size:12px;}
.bp-pill-purple {background:#EDEAFF;border-color:#D6D0FF;color:#443AAE;}
.bp-section {font-size:13px;font-weight:700;color:#4B4F62;text-transform:uppercase;letter-spacing:.08em;margin:6px 0 10px;}
.bp-source {font-size:12px;color:#747789;margin-top:-8px;margin-bottom:8px;}
.bp-footnote {font-size:12px;color:#7E8191;}
.bp-topbar {height:54px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #E6E8F1;margin-bottom:14px;}
.bp-brand {display:flex;align-items:center;gap:10px;color:#202333;font-weight:750;letter-spacing:-.01em;}
.bp-brand-mark {width:30px;height:30px;border-radius:10px;background:linear-gradient(145deg,#6058D8,#8D82F0);display:inline-flex;align-items:center;justify-content:center;color:#FFF;box-shadow:0 7px 16px rgba(96,88,216,.24);}
.bp-brand-note {font-size:12px;color:#7A7F90;font-weight:500;padding-left:10px;border-left:1px solid #E0E2EB;}
.bp-trust {font-size:12px;color:#697083;display:flex;align-items:center;gap:7px;}
.bp-trust-dot {width:7px;height:7px;border-radius:50%;background:#45A36B;box-shadow:0 0 0 4px rgba(69,163,107,.10);}
.bp-capture-progress {display:grid;grid-template-columns:repeat(3,1fr);gap:8px;max-width:560px;margin:0 0 14px;}
.bp-capture-step {padding:8px 12px;border-radius:11px;background:#FFF;border:1px solid #E4E6F0;color:#7A7F90;font-size:12px;font-weight:600;}
.bp-capture-step-active {background:#EDEAFF;border-color:#D7D1FF;color:#4D43BB;}
.bp-capture-hero {position:relative;overflow:hidden;border:1px solid #E1E3F0;border-radius:22px;padding:20px 28px 18px;margin-bottom:16px;background:linear-gradient(110deg,#FFFFFF 10%,#F3F1FF 100%);box-shadow:0 12px 34px rgba(43,46,83,.055);}
.bp-capture-hero:after {content:"";position:absolute;width:220px;height:220px;border-radius:50%;right:-85px;top:-120px;background:radial-gradient(circle,rgba(143,130,240,.20),rgba(143,130,240,0) 70%);}
.bp-capture-eyebrow {font-size:11px;color:#6058D8;font-weight:750;letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px;}
.bp-capture-hero h1 {font-size:30px!important;line-height:1.2!important;letter-spacing:-.035em;margin:0 0 7px;color:#202333;}
.bp-capture-hero p {font-size:15px;line-height:1.65;color:#626A7C;margin:0;max-width:680px;}
.bp-card-title {font-size:16px;font-weight:750;color:#202333;margin:0;}
.bp-card-note {font-size:13px;color:#747B8C;margin-top:3px;}
.bp-api-note {font-size:12px;color:#72798A;line-height:1.45;padding-top:5px;}
@media (max-width: 760px) {
  .block-container {padding:.6rem 1rem 2rem;}
  .bp-brand-note,.bp-trust {display:none;}
  .bp-capture-progress {grid-template-columns:1fr;}
  .bp-capture-hero {padding:20px;}
  .bp-capture-hero h1 {font-size:27px!important;}
}
</style>""", unsafe_allow_html=True)

SAMPLE = ("我们是一个刚开始做海外营销的独立咖啡杯品牌，想在英国面向20-35岁的通勤人群推广一款可重复使用的随行杯。"
          "希望风格活泼、真实，重点提升新品认知。还没决定优惠信息。希望做 TikTok 和 Instagram 内容。")
FIELDS = [
    ("brand", "品牌 / Brand"), ("product", "产品或服务 / Product"),
    ("audience", "目标受众 / Audience"), ("campaign_goal", "营销目标 / Goal"),
    ("key_message", "核心信息 / Key message"), ("tone", "品牌语气 / Tone"),
    ("offer", "确认过的优惠 / Offer"), ("call_to_action", "行动号召 / CTA"),
    ("region", "目标市场 / Market"), ("constraints", "约束和注意事项 / Constraints"),
]
FIELD_GROUPS = [
    ("活动基础信息", ["brand", "product", "campaign_goal", "region"]),
    ("受众与传播信息", ["audience", "key_message", "tone"]),
    ("执行要求与限制", ["offer", "call_to_action", "constraints"]),
]
FIELD_LABELS = dict(FIELDS)
MARKETS = {"待 AI 识别": "", "英国": "United Kingdom", "美国": "United States"}

def api_key():
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        return key
    try:
        return st.secrets.get("OPENAI_API_KEY", "")
    except Exception:
        return ""

def unresolved_items(brief):
    questions = st.session_state.get("clarification_questions", [])
    if questions:
        return unresolved_clarifications(questions)
    return list(dict.fromkeys(brief.missing_information + brief.assumptions))

def archive_current_package(status="已过期"):
    package = st.session_state.get("package")
    if package is None:
        return
    history = st.session_state.setdefault("package_history", [])
    history.append({
        "package": package.model_copy(deep=True),
        "brief_revision": package.source_brief_revision,
        "review_status": package.review_status,
        "status": status,
    })

def mark_current_package_stale():
    if "package" in st.session_state:
        st.session_state.package = mark_package_stale(st.session_state.package)
        st.session_state.package_status = "需要复审"
        st.session_state.review_status = "需要修改"

def load_brief_fields(brief):
    # Use version-specific form widget keys to prevent stale Streamlit widget state.
    st.session_state.brief_widget_revision = st.session_state.get("brief_widget_revision", 0) + 1
    for key, _ in FIELDS:
        st.session_state[f"brief_{st.session_state.brief_widget_revision}_{key}"] = getattr(brief, key)

def go(step):
    st.session_state.stage = step

if "stage" not in st.session_state:
    st.session_state.stage = 1
if "raw" not in st.session_state:
    st.session_state.raw = ""
if "channels" not in st.session_state:
    st.session_state.channels = ["TikTok", "Instagram"]
if "target_market" not in st.session_state:
    st.session_state.target_market = "待 AI 识别"

key = api_key()
if st.session_state.stage == 1:
    st.html(
        '<div class="bp-topbar">'
        '<div class="bp-brand"><span class="bp-brand-mark">✦</span><span>BriefPilot</span><span class="bp-brand-note">可信 AI Brief 工作流</span></div>'
        '<div class="bp-trust"><span class="bp-trust-dot"></span>人工审核 · 不自动发布</div>'
        '</div>'
        '<div class="bp-capture-progress">'
        '<div class="bp-capture-step bp-capture-step-active">01&nbsp;&nbsp;采集需求</div>'
        '<div class="bp-capture-step">02&nbsp;&nbsp;澄清确认</div>'
        '<div class="bp-capture-step">03&nbsp;&nbsp;生成交付</div>'
        '</div>'
        '<section class="bp-capture-hero">'
        '<div class="bp-capture-eyebrow">Capture · 需求采集</div>'
        '<h1>让每一份营销需求，都有清晰的起点。</h1>'
        '<p>输入客户原话或会议纪要，BriefPilot 会整理关键信息，并把需要确认的部分留给你判断。</p>'
        '</section>'
    )
else:
    st.markdown('<div class="bp-kicker">✦ BRIEFPILOT / 可信 AI BRIEF 工作台</div>', unsafe_allow_html=True)
    st.title("把零散需求变成可信、可审核的营销 Brief")
    st.markdown('<div class="bp-hero">从客户原始需求到人工确认 Brief，再到可复审的渠道创意稿。</div>', unsafe_allow_html=True)
    st.markdown('<div class="bp-rail">'+''.join(
        f'<span class="bp-stage {"bp-active" if st.session_state.stage == i else "bp-done" if st.session_state.stage > i else ""}">{i:02d} · {label}</span>'
        for i,label in [(1,"Capture 采集需求"),(2,"Clarify 澄清确认"),(3,"Deliver 生成交付")])+'</div>', unsafe_allow_html=True)

if st.session_state.stage == 1:
    with st.container(border=True):
        st.html('<div class="bp-capture-anchor"></div>')
        top_left, top_right = st.columns([4,1.15], vertical_alignment="center")
        with top_left:
            st.html('<div class="bp-card-title">客户原始需求</div><div class="bp-card-note">支持中文、英文或混合输入；不确定信息不会被自动补全。</div>')
        with top_right:
            if st.button("填入虚构示例", use_container_width=True):
                st.session_state.raw = SAMPLE
                st.rerun()
        st.text_area("客户原始需求", height=220, max_chars=5000, key="raw", placeholder="粘贴客户原话、邮件摘要或会议纪要……", help="请勿输入客户个人信息或高度敏感资料。", label_visibility="collapsed")
        market_col, channel_col = st.columns([1,1.5], gap="large")
        with market_col:
            st.selectbox("目标市场", list(MARKETS), key="target_market")
        with channel_col:
            st.multiselect("发布渠道", ["TikTok", "Instagram"], key="channels")
        footer_left, footer_right = st.columns([2.1,1], gap="large", vertical_alignment="center")
        with footer_left:
            if key:
                st.html('<div class="bp-api-note">营销正文默认使用英文，并提供简短中文释义。分析结果仍需人工确认。</div>')
            else:
                st.html('<div class="bp-api-note">AI 分析当前不可用。配置服务端 API 后即可继续；已输入内容会保留。</div>')
        with footer_right:
            analyze = st.button("分析需求 →", type="primary", use_container_width=True, disabled=not bool(key) or not bool(st.session_state.raw.strip()) or not bool(st.session_state.channels))
        if analyze:
            try:
                with st.spinner("正在提取结构化 Brief…"):
                    parsed_brief = parse_brief(st.session_state.raw, key)
                selected_market = MARKETS[st.session_state.target_market]
                if selected_market:
                    parsed_brief = parsed_brief.model_copy(update={"region": selected_market}, deep=True)
                    parsed_brief = mark_user_sources(parsed_brief, {"region"})
                previous = st.session_state.get("brief")
                if previous is None:
                    st.session_state.brief = parsed_brief
                    st.session_state.brief_revision = 1
                    st.session_state.brief_status = "草稿"
                    st.session_state.pop("confirmed_brief_revision", None)
                    st.session_state.change_impacts = []
                    st.session_state.clarification_questions = create_clarification_questions(parsed_brief)
                else:
                    saved, revision, confirmed_revision, changed = save_brief_revision(
                        previous,
                        parsed_brief,
                        st.session_state.get("brief_revision", 1),
                        st.session_state.get("confirmed_brief_revision"),
                    )
                    st.session_state.brief = saved
                    st.session_state.brief_revision = revision
                    if changed:
                        st.session_state.brief_status = "草稿"
                        st.session_state.pop("confirmed_brief_revision", None)
                        st.session_state.change_impacts = sorted(change_impact_fields(changed))
                        st.session_state.clarification_questions = create_clarification_questions(saved)
                        mark_current_package_stale()
                brief = st.session_state.brief
                st.session_state.source_raw = st.session_state.raw
                st.session_state.source_channels = tuple(st.session_state.channels)
                st.session_state.source_market = st.session_state.target_market
                load_brief_fields(brief)
                go(2)
                st.rerun()
            except Exception as exc:
                st.error(f"暂时无法完成分析（{type(exc).__name__}）。请稍后重试；你的原始输入已保留。")

elif st.session_state.stage == 2:
    if "brief" not in st.session_state:
        go(1); st.rerun()
    brief = st.session_state.brief
    revision_number = st.session_state.get("brief_revision", 1)
    brief_status = st.session_state.get("brief_status", "草稿")
    unresolved_count = len(unresolved_items(brief))
    st.subheader("02 · 澄清并确认 Brief")
    st.markdown(
        '<div class="bp-summary">'
        f'<span class="bp-pill bp-pill-purple">Brief v{revision_number}</span>'
        f'<span class="bp-pill">{brief_status}</span>'
        f'<span class="bp-pill">{unresolved_count} 项待处理</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    source_changed = (
        st.session_state.get("source_raw") != st.session_state.raw
        or st.session_state.get("source_channels") != tuple(st.session_state.channels)
        or st.session_state.get("source_market") != st.session_state.target_market
    )
    if source_changed:
        st.warning("客户原始需求或渠道选择已经变化。请重新分析后再确认 Brief。")
    revision = st.session_state.get("brief_widget_revision", 1)
    brief_col, clarify_col = st.columns([1.85,1], gap="large")
    with brief_col:
        with st.container(border=True):
            st.markdown("### 结构化 Brief")
            st.caption("来源表示信息从哪里进入 Brief；“客户提供”不等于产品声明已经事实核实。")
            with st.form("edit_brief"):
                for group_name, group_fields in FIELD_GROUPS:
                    st.markdown(f'<div class="bp-section">{group_name}</div>', unsafe_allow_html=True)
                    columns = st.columns(2)
                    for index, field in enumerate(group_fields):
                        with columns[index % 2]:
                            st.text_input(FIELD_LABELS[field], key=f"brief_{revision}_{field}")
                            source = brief.field_sources.get(field)
                            if source:
                                source_labels = {"customer_original":"客户原文", "user_entered":"用户填写", "ai_inference":"AI 推断", "unknown":"未知"}
                                verification_labels = {"unverified":"未核实", "pending":"待核对", "verified":"已核实", "not_applicable":"不适用"}
                                st.markdown(
                                    f'<div class="bp-source">来源：{source_labels[source.source_type]} · 核实状态：{verification_labels[source.verification_status]}</div>',
                                    unsafe_allow_html=True,
                                )
                                if source.source_excerpt:
                                    with st.expander("查看原文依据"):
                                        st.write(source.source_excerpt)
                save = st.form_submit_button("保存 Brief 草稿", type="primary", use_container_width=True)
                st.caption("保存不会自动确认；只有已保存内容会用于后续生成。")
    with clarify_col:
        with st.container(border=True):
            st.markdown("### AI 澄清区")
            st.caption("最多展示三个优先问题。回答不会自动覆盖 Brief。")
            questions = st.session_state.get("clarification_questions", [])[:3]
            if not questions:
                st.success("当前没有待处理的优先澄清问题。")
            for index, question in enumerate(questions):
                status_labels = {"open":"待回答", "answered":"待应用", "deferred":"暂缓", "not_applicable":"不适用", "applied":"已应用"}
                st.markdown(f"**{question.priority}. {question.question}**")
                st.caption(f"关联：{FIELD_LABELS.get(question.field_name, '通用事项')} · {status_labels[question.status]}")
                answer_key = f"clarification_answer_{question.id}"
                answer_value = st.text_area("回答或建议", value=question.answer, key=answer_key, height=80, label_visibility="collapsed", placeholder="输入客户回复或 Planner 判断…")
                q1,q2,q3 = st.columns(3)
                if q1.button("记录", key=f"answer_{question.id}", use_container_width=True):
                    try:
                        questions[index] = update_clarification(question, "answer", answer_value)
                        st.session_state.clarification_questions = questions
                        st.session_state.brief = reconcile_brief_issues(st.session_state.brief, questions)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
                if q2.button("暂缓", key=f"defer_{question.id}", use_container_width=True):
                    questions[index] = update_clarification(question, "defer")
                    st.session_state.clarification_questions = questions
                    st.rerun()
                if q3.button("不适用", key=f"na_{question.id}", use_container_width=True):
                    questions[index] = update_clarification(question, "not_applicable")
                    st.session_state.clarification_questions = questions
                    st.session_state.brief = reconcile_brief_issues(st.session_state.brief, questions)
                    st.rerun()
                if question.status == "answered" and question.field_name in FIELD_LABELS:
                    if st.button("应用到 Brief 草稿", key=f"apply_{question.id}", type="primary", use_container_width=True):
                        candidate, applied_question = apply_clarification_answer(st.session_state.brief, question)
                        saved, new_revision, _, changed = save_brief_revision(
                            st.session_state.brief, candidate, revision_number,
                            st.session_state.get("confirmed_brief_revision"),
                        )
                        questions[index] = applied_question
                        st.session_state.clarification_questions = questions
                        st.session_state.brief = reconcile_brief_issues(saved, questions)
                        st.session_state.brief_revision = new_revision
                        if changed:
                            st.session_state.brief_status = "草稿"
                            st.session_state.pop("confirmed_brief_revision", None)
                            st.session_state.change_impacts = sorted(change_impact_fields(changed))
                            mark_current_package_stale()
                        load_brief_fields(st.session_state.brief)
                        st.rerun()
                st.divider()
    if save:
        changes = {field: st.session_state[f"brief_{revision}_{field}"].strip() for field,_ in FIELDS}
        candidate = Brief(
            **changes,
            missing_information=brief.missing_information,
            assumptions=brief.assumptions,
            field_sources=brief.field_sources,
        )
        changed_fields = changed_brief_fields(brief, candidate)
        if changed_fields:
            candidate = mark_user_sources(candidate, changed_fields)
            saved_brief, new_revision, _, changed_fields = save_brief_revision(
                brief,
                candidate,
                st.session_state.get("brief_revision", 1),
                st.session_state.get("confirmed_brief_revision"),
            )
            st.session_state.brief = reconcile_brief_issues(saved_brief, st.session_state.get("clarification_questions", []))
            st.session_state.brief_revision = new_revision
            st.session_state.brief_status = "草稿"
            st.session_state.pop("confirmed_brief_revision", None)
            st.session_state.change_impacts = sorted(change_impact_fields(changed_fields))
            mark_current_package_stale()
            st.success(f"Brief 草稿已保存为 v{st.session_state.brief_revision}；原有确认状态已失效。")
        else:
            st.info("内容没有实质变化，Brief 版本保持不变。")
    current_values = {field: st.session_state[f"brief_{revision}_{field}"].strip() for field,_ in FIELDS}
    has_unsaved_changes = any(current_values[field] != getattr(st.session_state.brief, field) for field,_ in FIELDS)
    if has_unsaved_changes:
        st.warning("存在未保存修改。请先保存 Brief 草稿，再进行人工确认。")
    impact_fields = st.session_state.get("change_impacts", [])
    if impact_fields:
        impact_labels = {"campaign_goal":"营销目标", "region":"目标市场", "audience":"目标受众", "key_message":"核心信息"}
        st.warning("变更影响检查：" + "、".join(impact_labels[x] for x in impact_fields) + "发生变化，已有 TikTok / Instagram 创意稿需要重新检查。")
    if st.session_state.get("package_status") == "需要复审":
        st.error("当前保留的旧稿基于较早的 Brief，已标记为需要复审；生成新稿前不会被删除。")
    confirmed = brief_status == "已人工确认" and st.session_state.get("confirmed_brief_revision") == revision_number
    a,b,c=st.columns([1,1.2,2])
    with a:
        if st.button("← 返回采集", use_container_width=True):
            go(1); st.rerun()
    with b:
        if st.button("确认当前 Brief", use_container_width=True, disabled=has_unsaved_changes or source_changed):
            st.session_state.brief_status = "已人工确认"
            st.session_state.confirmed_brief_revision = st.session_state.get("brief_revision", 1)
            st.rerun()
    with c:
        confirmed = st.session_state.get("brief_status") == "已人工确认" and st.session_state.get("confirmed_brief_revision") == st.session_state.get("brief_revision")
        if st.button("生成渠道交付物 →", type="primary", use_container_width=True, disabled=not bool(key) or not confirmed or has_unsaved_changes):
            try:
                with st.spinner("正在生成可审核的渠道创意稿…"):
                    old_package = st.session_state.get("package")
                    new_package, generation_error = replace_package_safely(
                        old_package,
                        lambda: generate_drafts(
                            st.session_state.brief,
                            list(st.session_state.get("source_channels", st.session_state.channels)),
                            key,
                            st.session_state.brief_revision,
                            st.session_state.get("clarification_questions", []),
                        ),
                    )
                    if generation_error:
                        raise generation_error
                    archive_current_package()
                    st.session_state.package = new_package
                st.session_state.package_brief_revision = new_package.source_brief_revision
                st.session_state.package_status = "当前版本"
                st.session_state.review_status = new_package.review_status
                st.session_state.change_impacts = []
                st.session_state.draft_edit_version = st.session_state.get("draft_edit_version",0) + 1
                go(3); st.rerun()
            except Exception as exc:
                st.error(f"创意稿生成未完成（{type(exc).__name__}）。已保存 Brief 不受影响，请检查 API 后重试。")

else:
    if "brief" not in st.session_state or "package" not in st.session_state:
        go(2 if "brief" in st.session_state else 1); st.rerun()
    brief, package = st.session_state.brief, st.session_state.package
    source_brief = package.source_brief_snapshot or brief
    lifecycle_label = "当前版本" if package.lifecycle_status == "current" else "已过期"
    st.subheader("03 · 审核并导出交付物")
    st.markdown(
        '<div class="bp-summary">'
        f'<span class="bp-pill bp-pill-purple">Brief v{package.source_brief_revision}</span>'
        f'<span class="bp-pill">{lifecycle_label}</span>'
        f'<span class="bp-pill">{package.review_status}</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    if package.lifecycle_status == "stale":
        st.warning("这批交付物基于较早的 Brief，已标记为过期。内容仍保留，但发布或导出前应重新检查。")
    version = st.session_state.get("draft_edit_version",1)
    content_changed = False
    brief_tab, clarification_tab, creative_tab = st.tabs(["营销简报", "客户澄清表", "创意交接稿"])
    with brief_tab:
        st.caption("以下内容来自这批交付物绑定的 Brief 快照，不会随最新草稿变化。")
        for group_name, group_fields in FIELD_GROUPS:
            with st.container(border=True):
                st.markdown(f"### {group_name}")
                columns = st.columns(2)
                for index, field in enumerate(group_fields):
                    with columns[index % 2]:
                        st.markdown(f"**{FIELD_LABELS[field]}**")
                        st.write(getattr(source_brief, field) or "—")
                        source = source_brief.field_sources.get(field)
                        if source:
                            source_labels = {"customer_original":"客户原文", "user_entered":"用户填写", "ai_inference":"AI 推断", "unknown":"未知"}
                            st.caption(f"来源：{source_labels[source.source_type]} · 核实：{source.verification_status}")
    with clarification_tab:
        st.caption("展示生成这批交付物时的澄清记录快照。")
        if not package.clarification_snapshot:
            st.info("这批交付物没有保存结构化澄清记录。")
        for item in package.clarification_snapshot:
            with st.container(border=True):
                status_labels = {"open":"待回答", "answered":"已回答，待应用", "deferred":"暂缓", "not_applicable":"不适用", "applied":"已应用"}
                st.markdown(f"**{item.question}**")
                st.caption(f"关联：{FIELD_LABELS.get(item.field_name, '通用事项')} · 状态：{status_labels[item.status]}")
                if item.answer:
                    st.write(item.answer)
    with creative_tab:
        st.caption("英文正文用于目标市场投放；中文释义仅帮助团队快速审核，不替代正式翻译审校。")
        for i,draft in enumerate(package.drafts):
            with st.container(border=True):
                st.markdown(f"### {draft.channel}")
                old_values = (draft.hook, draft.body, draft.visual_direction, draft.call_to_action, draft.chinese_summary)
                draft.hook = st.text_input("英文 Hook", value=draft.hook, key=f"d{version}_{i}_hook")
                draft.body = st.text_area("英文脚本 / Caption", value=draft.body, height=180, key=f"d{version}_{i}_body")
                draft.visual_direction = st.text_area("视觉方向", value=draft.visual_direction, height=90, key=f"d{version}_{i}_visual")
                draft.call_to_action = st.text_input("英文 CTA", value=draft.call_to_action, key=f"d{version}_{i}_cta")
                if draft.chinese_summary:
                    draft.chinese_summary = st.text_area("中文释义", value=draft.chinese_summary, height=90, key=f"d{version}_{i}_summary")
                else:
                    st.info("这份旧稿没有模型生成的中文释义。为避免错配，系统不会自动填充固定翻译；重新生成后可获得对应释义。")
                content_changed = content_changed or old_values != (draft.hook, draft.body, draft.visual_direction, draft.call_to_action, draft.chinese_summary)
                st.caption("建议 Hashtags："+"  ".join(draft.hashtags))
                if draft.notes_for_review:
                    st.warning("发布前检查："+" · ".join(draft.notes_for_review))
        if content_changed:
            st.session_state.review_status = "需要修改"
            package.review_status = "需要修改"
            st.warning("创意内容已修改，之前的审核结论已失效，请重新审核。")
        st.markdown("### 基础质量检查")
        checks=quality_checks(source_brief,package)
        with st.container(border=True):
            for name,passed,tip in checks:
                st.write(("✅ " if passed else "⚠️ ")+name+("" if passed else f" — {tip}"))
            if package.claims_to_verify:
                st.error("必须人工核实的营销声明："+" · ".join(package.claims_to_verify))
        st.caption("质量检查只判断字段存在和风险标记，不验证真实性、法律合规、品牌适配或营销效果。")
    statuses=["草稿 — 未审核","需要修改","已由人工审核"]
    if st.session_state.get("review_status") not in statuses:
        st.session_state.review_status = package.review_status if package.review_status in statuses else "草稿 — 未审核"
    selected_review_status = st.selectbox("人工审核状态",statuses,key="review_status",help="人工审核不代表客户批准，也不代表系统已经验证营销声明真实或合规。")
    package.review_status = selected_review_status
    clarification_unresolved = unresolved_clarifications(package.clarification_snapshot)
    unresolved = clarification_unresolved + package.claims_to_verify + package.general_review_notes
    checks = quality_checks(source_brief, package)
    output={
        "purpose": "Human-reviewed marketing brief and creative handoff; not approved for automatic publishing",
        "brief_version": package.source_brief_revision,
        "brief_status": st.session_state.get("brief_status", "草稿"),
        "review_status": package.review_status,
        "package_status": package.lifecycle_status,
        "unresolved_items": unresolved,
        "brief":source_brief.model_dump(),
        "content":package.model_dump(),
        "checks":[{"item":name,"passed":passed} for name,passed,_ in checks],
    }
    a,b=st.columns(2)
    with a:
        st.download_button("↓ 下载 Markdown",export_markdown(source_brief,package,package.review_status,package.source_brief_revision,unresolved),file_name="briefpilot_output.md",mime="text/markdown",use_container_width=True)
    with b:
        st.download_button("↓ 下载 JSON",json.dumps(output,ensure_ascii=False,indent=2),file_name="briefpilot_output.json",mime="application/json",use_container_width=True)
    history = st.session_state.get("package_history", [])
    if history:
        with st.expander(f"历史创意稿（{len(history)} 个版本）"):
            for index,item in enumerate(reversed(history),1):
                st.write(f"历史稿 {index} · 基于 Brief v{item['brief_revision']} · {item['status']} · {item['review_status']}")
    if st.button("← 返回 Brief 复核或修改"):
        go(2); st.rerun()

st.divider()
st.markdown('<div class="bp-footnote">BriefPilot · AI 生成内容需经人工审核，不会自动发布，也不会自动核实营销声明。</div>',unsafe_allow_html=True)
