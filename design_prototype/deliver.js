const tabs = [...document.querySelectorAll('[role="tab"]')];
const panels = [...document.querySelectorAll('[role="tabpanel"]')];
const toast = document.querySelector('#toast');
let delivery = null;
let requestInFlight = false;
const compactModeQuery = window.matchMedia('(max-width: 1040px)');

function renderModeTag() {
  const modeTag = document.querySelector('#mode-tag');
  modeTag.textContent = compactModeQuery.matches ? modeTag.dataset.compactLabel : modeTag.dataset.fullLabel;
}
compactModeQuery.addEventListener('change', renderModeTag);
const exportDialog = document.querySelector('#export-dialog');
let exportDialogTrigger = null;
const briefFieldLabels = {
  product: '产品', campaign_goal: '营销目标', audience: '目标受众',
  key_message: '核心信息', region: '目标市场', tone: '表达语气', constraints: '内容限制',
};

function closeExportDialog() {
  exportDialog.close();
  window.setTimeout(() => {
    if (exportDialogTrigger?.isConnected && !exportDialogTrigger.disabled) exportDialogTrigger.focus();
  }, 0);
}

function setBusy(isBusy) {
  requestInFlight = isBusy;
  document.body.toggleAttribute('aria-busy', isBusy);
  ['#generate-deliver', '#mark-reviewed', '#export-package', '#review-status'].forEach(selector => {
    const control = document.querySelector(selector);
    if (control) control.disabled = isBusy || (!delivery?.package && selector !== '#generate-deliver');
  });
  if (!isBusy && delivery) {
    document.querySelector('#generate-deliver').disabled = !delivery.can_generate;
    setPackageControlsDisabled(!delivery.package);
  }
}

function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => { toast.hidden = true; }, 2600);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: options.body ? {'Content-Type': 'application/json', ...(options.headers || {})} : options.headers,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error?.message || `请求失败（${response.status}）`);
  return payload;
}

function activateTab(tab) {
  tabs.forEach(item => {
    item.setAttribute('aria-selected', String(item === tab));
    item.tabIndex = item === tab ? 0 : -1;
  });
  panels.forEach(panel => { panel.hidden = panel.id !== tab.dataset.tab; });
}

tabs.forEach((tab, index) => {
  tab.addEventListener('click', () => activateTab(tab));
  tab.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length : (index - 1 + tabs.length) % tabs.length;
    tabs[next].focus(); activateTab(tabs[next]);
  });
});

const requestedTab = new URLSearchParams(window.location.search).get('tab');
const initialTab = tabs.find(tab => tab.dataset.tab === requestedTab);
if (initialTab) activateTab(initialTab);

function setPackageControlsDisabled(disabled) {
  document.querySelector('#review-status').disabled = disabled;
  document.querySelector('#mark-reviewed').disabled = disabled;
  document.querySelector('#export-package').disabled = disabled;
}

function renderHistory(state) {
  const select = document.querySelector('#package-history');
  select.replaceChildren();
  if (!state.history.length) {
    const option = document.createElement('option');
    option.textContent = '暂无历史稿';
    option.value = '';
    select.append(option);
    select.disabled = true;
    return;
  }
  const historicalCounts = state.history.slice(1).reduce((counts, item) => {
    const key = `${item.source_brief_revision}:${item.content_revision}`;
    counts.set(key, (counts.get(key) || 0) + 1);
    return counts;
  }, new Map());
  const historicalSeen = new Map();
  state.history.forEach((item, index) => {
    const option = document.createElement('option');
    option.value = item.package_id;
    const key = `${item.source_brief_revision}:${item.content_revision}`;
    const duplicateCount = historicalCounts.get(key) || 0;
    let stateLabel = '当前';
    if (index > 0) {
      const occurrence = (historicalSeen.get(key) || 0) + 1;
      historicalSeen.set(key, occurrence);
      stateLabel = duplicateCount > 1 ? `历史 ${occurrence}/${duplicateCount}` : '历史';
    }
    option.textContent = `Brief v${item.source_brief_revision}.0 · r${item.content_revision} · ${stateLabel}`;
    option.title = `Brief v${item.source_brief_revision}.0 · 内容修订 r${item.content_revision} · ${item.lifecycle_status}`;
    option.selected = item.package_id === state.selected_package_id;
    select.append(option);
  });
  select.disabled = false;
}

function renderClarifications(questions) {
  const sheet = document.querySelector('#clarification-sheet');
  sheet.replaceChildren();
  if (!questions.length) {
    const empty = document.createElement('p');
    empty.textContent = '生成时没有记录澄清问题。';
    sheet.append(empty);
    return;
  }
  const stateNames = {open: '待答复', answered: '已回答', deferred: '暂缓', not_applicable: '不适用', applied: '已应用'};
  questions.forEach(question => {
    const article = document.createElement('article');
    const status = document.createElement('span');
    status.className = `question-state ${question.status === 'applied' || question.status === 'answered' ? 'resolved' : question.status === 'deferred' ? 'deferred' : 'open'}`;
    status.textContent = stateNames[question.status] || question.status;
    const content = document.createElement('div');
    const title = document.createElement('strong');
    title.textContent = question.question;
    const answer = document.createElement('p');
    answer.textContent = question.answer ? `生成时记录：${question.answer}` : '生成时没有已记录回答。';
    content.append(title, answer);
    const field = document.createElement('small');
    field.textContent = `关联字段 · ${briefFieldLabels[question.field_name] || '一般事项'}`;
    article.append(status, content, field);
    sheet.append(article);
  });
}

function renderDrafts(packageData) {
  const container = document.querySelector('#channel-drafts');
  container.replaceChildren();
  let hasPendingTranslation = false;
  packageData.drafts.forEach(draft => {
    const card = document.createElement('article');
    card.className = 'draft-card';
    card.dataset.channel = draft.channel;
    const header = document.createElement('header');
    const identity = document.createElement('div');
    const mark = document.createElement('span');
    mark.className = 'platform-mark';
    mark.textContent = draft.channel === 'TikTok' ? 'TK' : 'IG';
    const heading = document.createElement('div');
    const title = document.createElement('strong');
    title.textContent = `${draft.channel} 内容工作稿`;
    const meta = document.createElement('small');
    meta.textContent = `英文内容 · Hook：${draft.hook}`;
    heading.append(title, meta);
    identity.append(mark, heading);
    const lifecycle = document.createElement('span');
    lifecycle.className = 'draft-status';
    lifecycle.textContent = packageData.lifecycle_status;
    if (packageData.lifecycle_status === 'stale') lifecycle.classList.add('needs-update');
    header.append(identity, lifecycle);

    const label = document.createElement('label');
    label.textContent = '英文正文';
    const textarea = document.createElement('textarea');
    textarea.className = 'english-copy';
    textarea.value = draft.body;
    textarea.dataset.channel = draft.channel;
    textarea.addEventListener('input', () => {
      textarea.style.height = 'auto';
      textarea.style.height = `${textarea.scrollHeight}px`;
    });
    label.append(textarea);

    const translation = document.createElement('div');
    translation.className = 'translation';
    const translationLabel = document.createElement('span');
    translationLabel.textContent = '中文释义 ';
    const translationState = document.createElement('b');
    const pending = draft.chinese_summary_status === 'pending_update';
    hasPendingTranslation ||= pending;
    translationState.textContent = pending ? '待更新' : '已对应';
    if (pending) translationState.classList.add('needs-update');
    translationLabel.append(translationState);
    const translationText = document.createElement('p');
    translationText.textContent = draft.chinese_summary;
    translation.append(translationLabel, translationText);

    const detail = document.createElement('p');
    detail.className = 'expression';
    detail.textContent = `CTA：${draft.call_to_action} · 画面：${draft.visual_direction}`;
    card.append(header, label, translation, detail);
    container.append(card);
    textarea.style.height = 'auto';
    textarea.style.height = `${textarea.scrollHeight}px`;
  });
  document.querySelector('#translation-warning').hidden = !hasPendingTranslation;
}

function render(state) {
  delivery = state;
  const liveMode = state.mode === 'live_ai';
  const modeTag = document.querySelector('#mode-tag');
  modeTag.dataset.fullLabel = liveMode ? '实时 AI · LIVE AI' : '本地固定测试 · LOCAL FIXTURE';
  modeTag.dataset.compactLabel = liveMode ? '实时 AI' : '本地测试';
  renderModeTag();
  document.querySelector('#mode-eyebrow').textContent = `03 / DELIVER · ${liveMode ? 'LIVE AI' : 'LOCAL FIXTURE'}`;
  document.querySelector('#generate-deliver').textContent = liveMode ? '调用 AI 生成新稿' : '生成新测试稿';
  document.querySelector('#footer-mode').textContent = `${liveMode ? '实时 AI 工作稿' : '本地固定测试数据'} · 不代表客户批准`;
  renderHistory(state);
  document.querySelector('#generate-deliver').disabled = !state.can_generate;
  document.querySelector('#generate-deliver').title = state.can_generate ? '生成新的固定测试稿，旧稿继续保留' : state.generation_blocker;
  document.querySelector('#brief-status').textContent = `最新 Brief v${state.latest_brief_revision}.0 · ${state.latest_brief_status}`;
  document.querySelector('#deliver-blocker').hidden = state.can_generate || Boolean(state.package);
  document.querySelector('#blocker-copy').textContent = state.generation_blocker;

  const pkg = state.package;
  if (!pkg) {
    setPackageControlsDisabled(true);
    document.querySelector('#package-state').textContent = state.generation_blocker || '尚未生成交付物';
    document.querySelector('#marketing-title').textContent = '尚未生成营销简报';
    document.querySelector('#stale-banner').hidden = true;
    return;
  }

  setPackageControlsDisabled(false);
  const brief = pkg.source_brief_snapshot;
  const packageIsLive = pkg.generation_mode === 'live_ai';
  document.querySelector('#data-source-label').textContent = packageIsLive ? 'OpenAI structured output · 已人工确认 Brief' : '固定虚构测试数据';
  document.querySelector('#generation-label').textContent = packageIsLive ? '实时 AI 工作稿' : '本地固定测试稿';
  document.querySelector('#generation-copy').textContent = packageIsLive ? '由服务端调用 OpenAI 生成；仍需人工与合规审核。' : '未调用真实 AI；文案仅用于验证工作流。';
  document.querySelector('#package-state').textContent = `交付包 ${pkg.lifecycle_status} · 内容 r${pkg.content_revision}`;
  document.querySelector('#stale-banner').hidden = pkg.lifecycle_status !== 'stale';
  document.querySelector('#stale-reason').textContent = pkg.stale_reason || '该交付物对应旧 Brief，需要复审。';
  document.querySelector('#marketing-kicker').textContent = `绑定 Brief v${pkg.source_brief_revision}.0 独立快照`;
  document.querySelector('#marketing-title').textContent = `${brief.region || '待识别市场'} · ${brief.product || '待确认产品'}营销简报`;
  document.querySelector('#lead-message').textContent = brief.key_message || '核心信息待确认';
  document.querySelector('#lead-summary').textContent = `面向${brief.audience || '待确认受众'}，以${brief.tone || '待确认语气'}开展内部创意探索。`;
  document.querySelector('#marketing-version').textContent = `v${pkg.source_brief_revision}.0`;
  document.querySelector('#fact-goal').textContent = brief.campaign_goal || '待确认';
  document.querySelector('#fact-region').textContent = brief.region || '待确认';
  document.querySelector('#fact-audience').textContent = brief.audience || '待确认';
  document.querySelector('#point-message').textContent = brief.key_message || '待确认';
  document.querySelector('#point-constraints').textContent = brief.constraints || '未记录';
  document.querySelector('#point-channels').textContent = pkg.drafts.map(item => item.channel).join(' · ');
  document.querySelector('#rail-current').textContent = `${pkg.lifecycle_status} · ${pkg.lifecycle_status === 'stale' ? '待复审' : '当前'}`;
  document.querySelector('#rail-version').textContent = `Brief v${pkg.source_brief_revision}.0`;
  document.querySelector('#rail-content-version').textContent = `r${pkg.content_revision}`;
  document.querySelector('#rail-review').textContent = pkg.review_status;
  document.querySelector('#review-status').value = pkg.review_status;
  document.querySelector('#risk-count').textContent = `未解决事项 · ${state.unresolved_items.length}`;
  const riskItems = document.querySelector('#risk-items');
  riskItems.replaceChildren();
  (state.unresolved_items.length ? state.unresolved_items : ['生成快照中没有记录未解决事项。']).forEach(item => {
    const line = document.createElement('p'); line.textContent = item; riskItems.append(line);
  });
  document.querySelector('#version-note').textContent = `当前内容绑定 Brief v${pkg.source_brief_revision}.0`;
  document.querySelector('#clarification-version').textContent = `Brief v${pkg.source_brief_revision}.0`;
  document.querySelector('#handoff-kicker').textContent = `创意制作输入 · Brief v${pkg.source_brief_revision}.0 · 内容 r${pkg.content_revision}`;
  document.querySelector('#handoff-review').textContent = pkg.review_status;
  document.querySelector('#footer-version').textContent = `交付物绑定 Brief v${pkg.source_brief_revision}.0 · ${pkg.lifecycle_status}`;
  renderClarifications(pkg.clarification_snapshot);
  renderDrafts(pkg);
}

async function loadDelivery(packageId = null) {
  try {
    const requested = packageId || new URLSearchParams(window.location.search).get('package');
    const query = requested ? `?package_id=${encodeURIComponent(requested)}` : '';
    const state = await api(`/api/deliver${query}`);
    render(state);
  } catch (error) {
    setPackageControlsDisabled(true);
    document.querySelector('#package-state').textContent = error.message;
    document.querySelector('#deliver-blocker').hidden = false;
    document.querySelector('#blocker-copy').textContent = `${error.message} 返回 Capture 或 Clarify 恢复工作状态。`;
  }
}

document.querySelector('#package-history').addEventListener('change', async event => {
  if (!event.target.value) return;
  history.replaceState(null, '', `deliver.html?package=${encodeURIComponent(event.target.value)}`);
  await loadDelivery(event.target.value);
});

document.querySelector('#generate-deliver').addEventListener('click', async () => {
  if (requestInFlight || !delivery?.can_generate) return;
  setBusy(true);
  try {
    if (delivery?.mode === 'live_ai' && !window.confirm('这将通过服务端调用真实 OpenAI API，可能产生费用。是否继续生成？')) return;
    const state = await api('/api/deliver/generate', {method: 'POST'});
    history.replaceState(null, '', `deliver.html?package=${encodeURIComponent(state.package.package_id)}`);
    render(state);
    showToast(`${state.mode === 'live_ai' ? '新的 AI 工作稿' : '新的本地固定测试稿'}已生成；旧稿继续保留。`);
  } catch (error) { showToast(error.message); }
  finally { setBusy(false); }
});

document.querySelector('#channel-drafts').addEventListener('change', async event => {
  const textarea = event.target.closest('.english-copy');
  if (!textarea || !delivery?.package || requestInFlight) return;
  setBusy(true);
  try {
    const state = await api('/api/deliver/draft', {
      method: 'PATCH',
      body: JSON.stringify({package_id: delivery.package.package_id, channel: textarea.dataset.channel, body: textarea.value}),
    });
    render(state);
    showToast('英文正文已保存；审核失效，中文释义已标记待更新。');
  } catch (error) { showToast(`保存失败：${error.message}`); }
  finally { setBusy(false); }
});

async function updateReview(status) {
  if (!delivery?.package) return;
  const state = await api('/api/deliver/review', {
    method: 'POST', body: JSON.stringify({package_id: delivery.package.package_id, status}),
  });
  render(state);
}

document.querySelector('#review-status').addEventListener('change', async event => {
  if (requestInFlight) return;
  setBusy(true);
  try { await updateReview(event.target.value); showToast('内部审核状态已保存，不代表客户批准。'); }
  catch (error) { render(delivery); showToast(error.message); }
  finally { setBusy(false); }
});

document.querySelector('#mark-reviewed').addEventListener('click', async () => {
  if (requestInFlight) return;
  setBusy(true);
  try { await updateReview('内部审核完成'); showToast('当前内容修订已完成内部审核，不代表客户批准。'); }
  catch (error) { showToast(error.message); }
  finally { setBusy(false); }
});

document.querySelector('#export-package').addEventListener('click', event => {
  exportDialogTrigger = event.currentTarget;
  exportDialog.showModal();
});
document.querySelector('#cancel-export').addEventListener('click', closeExportDialog);
exportDialog.addEventListener('close', () => {
  if (exportDialogTrigger?.isConnected) exportDialogTrigger.focus();
});

async function downloadExport(format) {
  if (!delivery?.package) return;
  try {
    const response = await fetch(`/api/deliver/export?package_id=${encodeURIComponent(delivery.package.package_id)}&format=${format}`);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error?.message || '导出失败');
    }
    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') || '';
    const filename = disposition.match(/filename="([^"]+)"/)?.[1] || `briefpilot-export.${format === 'json' ? 'json' : 'md'}`;
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob); link.download = filename; link.click();
    URL.revokeObjectURL(link.href);
    closeExportDialog();
    showToast(`${format === 'json' ? 'JSON' : 'Markdown'} 已由 Python 后端生成。`);
  } catch (error) { showToast(error.message); }
}

document.querySelector('#download-markdown').addEventListener('click', () => downloadExport('markdown'));
document.querySelector('#download-json').addEventListener('click', () => downloadExport('json'));
window.addEventListener('pageshow', () => loadDelivery());
