const toast = document.querySelector('#toast');
const feedback = document.querySelector('#clarify-feedback');
const impactBar = document.querySelector('#impact-bar');
const editableInputs = [...document.querySelectorAll('[data-field]')];
const fieldInputIds = {
  product: 'product', campaign_goal: 'goal', audience: 'audience',
  key_message: 'message', region: 'market-clarify', tone: 'tone', constraints: 'constraints',
};
const sourceLabels = {
  customer_original: '客户原文', user_entered: '用户填写',
  ai_inference: 'AI 推断', unknown: '来源未知',
};
const verificationLabels = {
  unverified: '客户提供 · 未核实', pending: '待核对',
  verified: '事实已核实', not_applicable: '不适用',
};
const briefFieldLabels = {
  product: '产品', campaign_goal: '营销目标', audience: '目标受众',
  key_message: '核心信息', region: '目标市场', tone: '表达语气', constraints: '内容限制',
};
let workspace = null;
let requestInFlight = false;
const dialogTriggers = new WeakMap();
const compactModeQuery = window.matchMedia('(max-width: 1040px)');

function renderModeTag() {
  const modeTag = document.querySelector('#mode-tag');
  modeTag.textContent = compactModeQuery.matches ? modeTag.dataset.compactLabel : modeTag.dataset.fullLabel;
}
compactModeQuery.addEventListener('change', renderModeTag);

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

function setControlsDisabled(disabled) {
  document.querySelectorAll('input, button').forEach(element => { element.disabled = disabled; });
}

function syncActionAvailability() {
  const save = document.querySelector('#save-draft');
  const confirm = document.querySelector('#confirm-brief');
  const enterDeliver = document.querySelector('#enter-deliver');
  save.disabled = requestInFlight || !workspace || !workspace.dirty;
  confirm.disabled = requestInFlight || !workspace || workspace.dirty || workspace.status === 'confirmed';
  enterDeliver.disabled = requestInFlight || !workspace || workspace.status !== 'confirmed' || workspace.dirty;
  document.querySelectorAll('.question-actions button, .suggestion button').forEach(button => {
    button.disabled = requestInFlight;
  });
}

function setBusy(isBusy) {
  requestInFlight = isBusy;
  document.body.toggleAttribute('aria-busy', isBusy);
  syncActionAvailability();
}

function openDialog(dialog, trigger) {
  dialogTriggers.set(dialog, trigger);
  dialog.showModal();
}

function restoreDialogFocus(dialog) {
  const trigger = dialogTriggers.get(dialog);
  if (trigger?.isConnected && !trigger.disabled) {
    trigger.focus();
    return;
  }
  feedback.setAttribute('tabindex', '-1');
  feedback.focus();
}

function closeDialog(dialog) {
  dialog.close();
  window.setTimeout(() => restoreDialogFocus(dialog), 0);
}

function renderSource(fieldName, source) {
  const sourceElement = document.querySelector(`#source-${fieldName}`);
  const verifyElement = document.querySelector(`#verify-${fieldName}`);
  if (!sourceElement || !verifyElement) return;
  const resolved = source || {source_type: 'unknown', source_excerpt: '', verification_status: 'pending'};
  sourceElement.textContent = sourceLabels[resolved.source_type] || '来源未知';
  sourceElement.className = `source ${resolved.source_type === 'customer_original' || resolved.source_type === 'user_entered' ? 'user-source' : 'inferred-source'}`;
  verifyElement.textContent = verificationLabels[resolved.verification_status] || '待核对';
  verifyElement.className = `verify ${resolved.verification_status === 'verified' ? 'verified' : 'pending'}`;
  const details = document.querySelector(`#evidence-${fieldName}`);
  const excerpt = document.querySelector(`#excerpt-${fieldName}`);
  if (details && excerpt) {
    details.hidden = !resolved.source_excerpt;
    excerpt.textContent = resolved.source_excerpt ? `“${resolved.source_excerpt}”` : '';
  }
}

function statusText(state) {
  if (state.status === 'confirmed') return `Brief v${state.revision}.0 · 已人工确认`;
  if (state.status === 'confirmed_with_changes') return `Brief v${state.revision}.0 · 已确认版本上有编辑`;
  if (state.status === 'needs_reconfirmation') return `Brief v${state.revision}.0 · 需重新确认`;
  return `Brief v${state.revision}.0 · 工作稿`;
}

function makeButton(label, action) {
  const button = document.createElement('button');
  button.type = 'button';
  button.dataset.action = action;
  button.textContent = label;
  return button;
}

function renderQuestions(questions, isDirty) {
  const container = document.querySelector('#questions');
  container.replaceChildren();
  questions.forEach((question, index) => {
    const card = document.createElement('article');
    card.className = 'question';
    card.dataset.questionId = question.id;
    card.dataset.state = question.status;

    const title = document.createElement('div');
    title.className = 'question-title';
    const number = document.createElement('span');
    number.textContent = String(index + 1);
    const copy = document.createElement('div');
    const strong = document.createElement('strong');
    strong.id = `question-title-${question.id}`;
    strong.textContent = question.question;
    const small = document.createElement('small');
    small.textContent = `关联字段 · ${briefFieldLabels[question.field_name] || '一般事项'}`;
    copy.append(strong, small);
    title.append(number, copy);

    const input = document.createElement('input');
    input.className = 'answer-input';
    input.id = `question-answer-${question.id}`;
    input.setAttribute('aria-labelledby', strong.id);
    input.placeholder = '输入客户回答';
    input.value = question.answer || '';
    const inputLabel = document.createElement('label');
    inputLabel.className = 'sr-only';
    inputLabel.htmlFor = input.id;
    inputLabel.textContent = `回答：${question.question}`;

    const actions = document.createElement('div');
    actions.className = 'question-actions';
    actions.append(makeButton('记录回答', 'answer'), makeButton('暂缓', 'defer'), makeButton('不适用', 'not_applicable'));

    const suggestion = document.createElement('div');
    suggestion.className = 'suggestion';
    suggestion.hidden = question.status !== 'answered';
    const suggestionLabel = document.createElement('span');
    suggestionLabel.textContent = '待应用建议';
    const suggestionText = document.createElement('p');
    suggestionText.textContent = question.answer || '';
    suggestion.append(suggestionLabel, suggestionText);
    if (fieldInputIds[question.field_name]) suggestion.append(makeButton('应用建议', 'apply'));

    const stateLabel = document.createElement('small');
    stateLabel.className = `question-state ${question.status}`;
    stateLabel.textContent = {open: '待处理', answered: '已记录，尚未应用', deferred: '已暂缓', not_applicable: '不适用', applied: isDirty ? '已应用，等待保存' : '已应用'}[question.status] || question.status;
    const footer = document.createElement('div');
    footer.className = 'question-footer';
    footer.append(actions, stateLabel);
    card.append(title, inputLabel, input, footer, suggestion);
    container.append(card);
  });
}

function questionCountText(questions) {
  if (!questions.length) return '暂无澄清问题';
  const unresolved = questions.filter(item => ['open', 'deferred'].includes(item.status)).length;
  return unresolved ? `${unresolved} 项待处理` : '全部已处理';
}

function render(state, message = '') {
  workspace = state;
  setControlsDisabled(false);
  const liveMode = state.mode === 'live_ai';
  const modeTag = document.querySelector('#mode-tag');
  modeTag.dataset.fullLabel = liveMode ? '实时 AI · LIVE AI' : '本地固定测试 · LOCAL FIXTURE';
  modeTag.dataset.compactLabel = liveMode ? '实时 AI' : '本地测试';
  renderModeTag();
  document.querySelector('#mode-eyebrow').textContent = `02 / CLARIFY · ${liveMode ? 'LIVE AI' : 'LOCAL FIXTURE'}`;
  Object.entries(fieldInputIds).forEach(([fieldName, inputId]) => {
    document.querySelector(`#${inputId}`).value = state.brief[fieldName] || '';
    renderSource(fieldName, state.brief.field_sources[fieldName]);
  });
  document.querySelector('#channels').value = state.selected_channels.join(' · ');
  document.querySelector('#brief-title').textContent = `${state.brief.region || '待识别市场'} · ${state.brief.product || '待确认产品'}`;
  document.querySelector('#brief-version').textContent = statusText(state);
  document.querySelector('#save-state').textContent = state.dirty
    ? '已暂存到本地会话 · 尚未保存为 Brief 版本'
    : state.status === 'confirmed'
      ? `Brief v${state.revision}.0 已保存并人工确认`
      : state.status === 'needs_reconfirmation'
        ? `Brief v${state.revision}.0 已保存 · 待重新确认`
        : `Brief v${state.revision}.0 已保存 · 尚未人工确认`;
  document.querySelector('#unresolved-count').textContent = state.unresolved_items.length;
  const verified = Object.values(state.brief.field_sources).filter(item => item.verification_status === 'verified').length;
  document.querySelector('#confirmed-count').textContent = `${verified} / 7`;
  impactBar.hidden = state.impact_fields.length === 0;
  if (state.impact_fields.length) {
    const impactLabels = state.impact_fields.map(field => briefFieldLabels[field] || field).join('、');
    document.querySelector('#impact-copy').textContent = state.dirty
      ? `关键字段 ${impactLabels} 已修改；保存后将更新版本与确认状态。`
      : `关键字段 ${impactLabels} 的变化已保存；当前 Brief 需要重新确认。`;
  }
  document.querySelector('#question-count').textContent = questionCountText(state.questions);
  const enterDeliver = document.querySelector('#enter-deliver');
  enterDeliver.textContent = liveMode ? '调用 AI 生成并进入' : '生成测试交付物并进入';
  enterDeliver.title = state.status !== 'confirmed' || state.dirty ? '请先保存并人工确认当前 Brief' : (liveMode ? '将通过服务端调用 OpenAI，可能产生费用' : '生成固定本地测试交付物');
  renderQuestions(state.questions, state.dirty);
  feedback.textContent = message || (state.dirty ? '修改已暂存到本地会话，尚未保存为 Brief 版本。' : `当前显示已保存的 Brief v${state.revision}.0。`);
  syncActionAvailability();
}

async function loadWorkspace() {
  try {
    render(await api('/api/workspace'));
  } catch (error) {
    workspace = null;
    setControlsDisabled(true);
    feedback.textContent = `${error.message} 返回 Capture 后重新分析即可创建本地会话。`;
    document.querySelector('#brief-version').textContent = '暂无可用 Brief';
    document.querySelector('#save-state').textContent = '服务重启不会保留内存会话';
  }
}

editableInputs.forEach(input => input.addEventListener('change', async () => {
  if (requestInFlight) return;
  setBusy(true);
  try {
    const state = await api('/api/brief/draft', {
      method: 'PATCH',
      body: JSON.stringify({fields: {[input.dataset.field]: input.value}}),
    });
    render(state, '编辑已进入本地会话；点击“保存草稿”后才会形成新版本。');
  } catch (error) {
    feedback.textContent = `更新失败：${error.message}。已保存的工作状态未改变。`;
    showToast('更新失败，已保存状态仍保留。');
  } finally {
    setBusy(false);
  }
}));

document.querySelector('#questions').addEventListener('click', async event => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  const card = button.closest('.question');
  const action = button.dataset.action;
  const input = card.querySelector('.answer-input');
  if (requestInFlight) return;
  setBusy(true);
  try {
    let state;
    if (action === 'apply') {
      state = await api(`/api/clarifications/${card.dataset.questionId}/apply`, {method: 'POST'});
      render(state, '建议已显式应用到未保存草稿；字段来源已更新为“用户填写”。');
      showToast('建议已应用，等待保存草稿。');
    } else {
      state = await api(`/api/clarifications/${card.dataset.questionId}`, {
        method: 'POST', body: JSON.stringify({action, answer: input.value}),
      });
      const messages = {
        answer: '回答已记录，Brief 字段尚未改变。',
        defer: '问题已暂缓，仍保留为未解决事项。',
        not_applicable: '问题已标记为不适用。',
      };
      render(state, messages[action]);
      showToast(messages[action]);
    }
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(false);
  }
});

document.querySelector('#save-draft').addEventListener('click', async () => {
  if (requestInFlight || !workspace?.dirty) return;
  setBusy(true);
  try {
    const before = workspace?.revision;
    const state = await api('/api/brief/save', {method: 'POST'});
    const message = state.revision === before ? '内容没有实质变化，版本号保持不变。' : `草稿已保存为 Brief v${state.revision}.0。`;
    render(state, `${message} 保存草稿不等于人工确认。`);
    showToast(message);
  } catch (error) {
    showToast(`保存失败：${error.message}`);
  } finally {
    setBusy(false);
  }
});

const confirmDialog = document.querySelector('#confirm-dialog');
const impactDialog = document.querySelector('#impact-dialog');
confirmDialog.addEventListener('close', () => restoreDialogFocus(confirmDialog));
impactDialog.addEventListener('close', () => restoreDialogFocus(impactDialog));

document.querySelector('#confirm-brief').addEventListener('click', event => {
  if (workspace?.dirty || requestInFlight) return;
  document.querySelector('#unresolved-count').textContent = workspace?.unresolved_items.length || 0;
  openDialog(confirmDialog, event.currentTarget);
});
document.querySelector('#cancel-confirm').addEventListener('click', () => closeDialog(confirmDialog));
document.querySelector('#complete-confirm').addEventListener('click', async () => {
  if (requestInFlight) return;
  setBusy(true);
  try {
    const state = await api('/api/brief/confirm', {method: 'POST'});
    closeDialog(confirmDialog);
    render(state, '当前已保存版本已人工确认；这不代表客户批准或事实核实。');
    showToast('当前 Brief 已人工确认。');
  } catch (error) {
    closeDialog(confirmDialog);
    showToast(error.message);
  } finally {
    setBusy(false);
  }
});

document.querySelector('#enter-deliver').addEventListener('click', async () => {
  if (requestInFlight || workspace?.status !== 'confirmed' || workspace?.dirty) return;
  setBusy(true);
  try {
    if (workspace?.mode === 'live_ai' && !window.confirm('这将通过服务端调用真实 OpenAI API 生成工作稿，可能产生费用。是否继续？')) return;
    const state = await api('/api/deliver/generate', {method: 'POST'});
    if (!state.package) throw new Error('本地 API 未返回交付物');
    window.location.assign(`/deliver.html?package=${encodeURIComponent(state.package.package_id)}`);
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(false);
  }
});

document.querySelector('#review-impact').addEventListener('click', event => openDialog(impactDialog, event.currentTarget));
document.querySelector('#close-impact').addEventListener('click', () => closeDialog(impactDialog));
window.addEventListener('pageshow', loadWorkspace);
