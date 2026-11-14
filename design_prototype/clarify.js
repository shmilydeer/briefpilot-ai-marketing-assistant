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
    strong.textContent = question.question;
    const small = document.createElement('small');
    small.textContent = `关联字段 · ${briefFieldLabels[question.field_name] || '一般事项'}`;
    copy.append(strong, small);
    title.append(number, copy);

    const input = document.createElement('input');
    input.className = 'answer-input';
    input.placeholder = '输入客户回答';
    input.value = question.answer || '';

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
    stateLabel.className = 'question-state';
    stateLabel.textContent = {open: '待处理', answered: '已记录，尚未应用', deferred: '已暂缓', not_applicable: '不适用', applied: isDirty ? '已应用，等待保存' : '已应用'}[question.status] || question.status;
    card.append(title, input, actions, suggestion, stateLabel);
    container.append(card);
  });
}

function render(state, message = '') {
  workspace = state;
  setControlsDisabled(false);
  const liveMode = state.mode === 'live_ai';
  document.querySelector('#mode-tag').textContent = liveMode ? '实时 AI · 服务端调用' : '本地测试 · 固定响应';
  document.querySelector('#mode-eyebrow').textContent = `02 / CLARIFY · ${liveMode ? 'LIVE AI' : 'LOCAL FIXTURE'}`;
  Object.entries(fieldInputIds).forEach(([fieldName, inputId]) => {
    document.querySelector(`#${inputId}`).value = state.brief[fieldName] || '';
    renderSource(fieldName, state.brief.field_sources[fieldName]);
  });
  document.querySelector('#channels').value = state.selected_channels.join(' · ');
  document.querySelector('#brief-title').textContent = `${state.brief.region || '待识别市场'} · ${state.brief.product || '待确认产品'}`;
  document.querySelector('#brief-version').textContent = statusText(state);
  document.querySelector('#save-state').textContent = state.dirty ? '有未保存修改 · 已保存在本地会话' : state.fixture_notice;
  document.querySelector('#unresolved-count').textContent = state.unresolved_items.length;
  const verified = Object.values(state.brief.field_sources).filter(item => item.verification_status === 'verified').length;
  document.querySelector('#confirmed-count').textContent = `${verified} / 7`;
  impactBar.hidden = state.impact_fields.length === 0;
  if (state.impact_fields.length) document.querySelector('#impact-copy').textContent = state.dirty
    ? `关键字段 ${state.impact_fields.join('、')} 已修改；保存后将按 Python 规则更新版本与确认状态。`
    : `关键字段 ${state.impact_fields.join('、')} 的变化已保存；当前 Brief 需要重新确认。`;
  const unresolved = state.questions.filter(item => ['open', 'deferred'].includes(item.status)).length;
  document.querySelector('#question-count').textContent = unresolved ? `${unresolved} 项待处理` : '全部已处理';
  const enterDeliver = document.querySelector('#enter-deliver');
  enterDeliver.disabled = state.status !== 'confirmed' || state.dirty;
  enterDeliver.textContent = liveMode ? '调用 AI 生成并进入' : '生成测试交付物并进入';
  enterDeliver.title = enterDeliver.disabled ? '请先保存并人工确认当前 Brief' : (liveMode ? '将通过服务端调用 OpenAI，可能产生费用' : '生成固定本地测试交付物');
  renderQuestions(state.questions, state.dirty);
  feedback.textContent = message || (state.dirty ? '编辑已进入本地会话，尚未形成新版本。' : '当前页面与 Python 工作状态一致。');
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
  try {
    const state = await api('/api/brief/draft', {
      method: 'PATCH',
      body: JSON.stringify({fields: {[input.dataset.field]: input.value}}),
    });
    render(state, '编辑已进入本地会话；点击“保存草稿”后才会形成新版本。');
  } catch (error) {
    feedback.textContent = `更新失败：${error.message}。已保存的工作状态未改变。`;
    showToast('更新失败，已保存状态仍保留。');
  }
}));

document.querySelector('#questions').addEventListener('click', async event => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  const card = button.closest('.question');
  const action = button.dataset.action;
  const input = card.querySelector('.answer-input');
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
  }
});

document.querySelector('#save-draft').addEventListener('click', async () => {
  try {
    const before = workspace?.revision;
    const state = await api('/api/brief/save', {method: 'POST'});
    const message = state.revision === before ? '内容没有实质变化，版本号保持不变。' : `草稿已保存为 Brief v${state.revision}.0。`;
    render(state, `${message} 保存草稿不等于人工确认。`);
    showToast(message);
  } catch (error) {
    showToast(`保存失败：${error.message}`);
  }
});

document.querySelector('#confirm-brief').addEventListener('click', () => {
  document.querySelector('#unresolved-count').textContent = workspace?.unresolved_items.length || 0;
  document.querySelector('#confirm-dialog').showModal();
});
document.querySelector('#cancel-confirm').addEventListener('click', () => document.querySelector('#confirm-dialog').close());
document.querySelector('#complete-confirm').addEventListener('click', async () => {
  try {
    const state = await api('/api/brief/confirm', {method: 'POST'});
    document.querySelector('#confirm-dialog').close();
    render(state, '当前已保存版本已人工确认；这不代表客户批准或事实核实。');
    showToast('当前 Brief 已人工确认。');
  } catch (error) {
    document.querySelector('#confirm-dialog').close();
    showToast(error.message);
  }
});

document.querySelector('#enter-deliver').addEventListener('click', async () => {
  try {
    if (workspace?.mode === 'live_ai' && !window.confirm('这将通过服务端调用真实 OpenAI API 生成工作稿，可能产生费用。是否继续？')) return;
    const state = await api('/api/deliver/generate', {method: 'POST'});
    if (!state.package) throw new Error('本地 API 未返回交付物');
    window.location.assign(`/deliver.html?package=${encodeURIComponent(state.package.package_id)}`);
  } catch (error) {
    showToast(error.message);
  }
});

document.querySelector('#review-impact').addEventListener('click', () => document.querySelector('#impact-dialog').showModal());
document.querySelector('#close-impact').addEventListener('click', () => document.querySelector('#impact-dialog').close());
window.addEventListener('pageshow', loadWorkspace);
