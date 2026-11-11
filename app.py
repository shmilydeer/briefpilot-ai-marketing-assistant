import json
import os
import streamlit as st
from models import Brief, DraftPackage
from logic import parse_brief, generate_drafts, quality_checks, export_markdown

st.set_page_config(page_title="BriefPilot · AI Marketing Brief", page_icon="🧭", layout="wide")
st.title("🧭 BriefPilot")
st.caption("Turn fuzzy marketing requests into editable briefs and reviewable social content. · MVP v0.1")
st.info("本工具生成的是待审核营销初稿，不会自动发布。所有品牌事实、推广承诺和合规性须由人工确认。")

try:
    api_key = os.environ.get("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY", "")
except Exception:
    api_key = os.environ.get("OPENAI_API_KEY", "")

if not api_key:
    st.error("尚未配置服务端 OPENAI_API_KEY；真实 AI 生成功能不可用。请参阅 README 的部署说明。")

example = "我们是一个刚开始做海外营销的独立咖啡杯品牌，想在英国面向20-35岁的通勤人群推广一款可重复使用的随行杯。想要活泼、真实的感觉，重点是提升新品认知。还没决定优惠信息。希望做TikTok和Instagram内容。"

st.subheader("Step 1 · 输入原始营销需求")
raw = st.text_area("客户原话 / Raw request", value=example, height=140, max_chars=5000)
channels = st.multiselect("目标渠道", ["TikTok", "Instagram"], default=["TikTok", "Instagram"])
if st.button("① AI 解析 Brief", type="primary", disabled=not bool(api_key)):
    try:
        with st.spinner("正在提取结构化需求…"):
            st.session_state.brief = parse_brief(raw, api_key)
        st.session_state.pop("package", None)
        st.session_state.review_status = "Draft — not approved"
    except Exception as e:
        st.error(f"Brief 解析失败：{type(e).__name__}。请检查 API 配置、额度或网络后重试。")

if "brief" in st.session_state:
    st.subheader("Step 2 · 核对并修改 Brief")
    brief = st.session_state.brief
    labels = {"brand":"品牌名称", "product":"产品 / 服务", "audience":"目标受众", "campaign_goal":"营销目标", "key_message":"核心卖点", "tone":"品牌语气", "offer":"真实优惠信息", "call_to_action":"CTA", "region":"目标市场", "constraints":"限制与注意事项"}
    with st.form("review_brief"):
        edited = {}
        for key,label in labels.items():
            edited[key] = st.text_input(label, value=getattr(brief,key), key="edit_"+key)
        if brief.missing_information:
            st.warning("原始信息缺失（AI 提示，供人工判断）：" + "；".join(brief.missing_information))
        if brief.assumptions:
            st.caption("待确认推断：" + "；".join(brief.assumptions))
        saved = st.form_submit_button("② 保存人工修订")
    if saved:
        st.session_state.brief = Brief(**edited, missing_information=brief.missing_information, assumptions=brief.assumptions)
        st.session_state.pop("package",None)
        st.success("Brief 已保存。后续内容使用这一人工确认版本。")

    if st.button("③ 生成渠道初稿", disabled=not bool(api_key) or not bool(channels)):
        try:
            with st.spinner("正在生成渠道内容…"):
                st.session_state.package = generate_drafts(st.session_state.brief, channels, api_key)
            st.session_state.review_status = "Draft — not approved"
        except Exception as e:
            st.error(f"内容生成失败：{type(e).__name__}。请检查 API 配置、额度或网络后重试。")

if "package" in st.session_state:
    pkg = st.session_state.package
    st.subheader("Step 3 · 检查内容并审核")
    for idx, draft in enumerate(pkg.drafts):
        with st.expander(f"{draft.channel} · 可编辑内容", expanded=True):
            draft.hook = st.text_input("Hook",value=draft.hook,key=f"hook_{idx}")
            draft.body = st.text_area("脚本 / Caption",value=draft.body,height=210,key=f"body_{idx}")
            draft.call_to_action = st.text_input("CTA", value=draft.call_to_action,key=f"cta_{idx}")
            draft.visual_direction = st.text_area("视觉方向",value=draft.visual_direction,key=f"visual_{idx}")
            st.caption("Hashtags: " + " ".join(draft.hashtags))
            if draft.notes_for_review:
                st.warning("待审核：" + "；".join(draft.notes_for_review))
    st.markdown("**基础质量检查（规则型，不是事实核验）**")
    checks = quality_checks(st.session_state.brief,pkg)
    for label, passed, tip in checks:
        st.write(("✅ " if passed else "⚠️ ")+label+("" if passed else f" — {tip}"))
    if pkg.claims_to_verify:
        st.error("必须人工核实的声明：" + "；".join(pkg.claims_to_verify))
    st.session_state.review_status = st.radio("人工审核状态", ["Draft — not approved", "Reviewed — changes needed", "Approved by human reviewer"], index=["Draft — not approved", "Reviewed — changes needed", "Approved by human reviewer"].index(st.session_state.get("review_status","Draft — not approved")))
    st.caption("Approved 只代表审核人员手动确认，软件不会自动认定营销承诺真实或合规。")
    output = {"status":st.session_state.review_status,"brief":st.session_state.brief.model_dump(),"content":pkg.model_dump(),"checks":[{"item":x,"passed":y} for x,y,_ in checks]}
    col1,col2 = st.columns(2)
    with col1:
        st.download_button("④ 导出 Markdown", export_markdown(st.session_state.brief,pkg,st.session_state.review_status),file_name="briefpilot_output.md",mime="text/markdown")
    with col2:
        st.download_button("导出 JSON",json.dumps(output,ensure_ascii=False,indent=2),file_name="briefpilot_output.json",mime="application/json")

st.divider()
st.caption("Prototype · Human-in-the-loop AI workflow · No auto-posting / No database / No tracking analytics")
