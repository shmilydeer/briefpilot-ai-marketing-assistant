const brief = document.querySelector('#brief');
const count = document.querySelector('#count');
const feedback = document.querySelector('#feedback');
const dialog = document.querySelector('#demo');
const submitButton = document.querySelector('#capture-form [type="submit"]');
const runMode = document.querySelector('#run-mode');
const modeTag = document.querySelector('#mode-tag');
function updateModeLabel() {
  const live = runMode.value === 'live_ai';
  modeTag.textContent = live ? '实时 AI · 仅在确认后调用' : '本地测试 API · 固定响应';
}
function updateCount() { count.textContent = `${Array.from(brief.value).length} 字`; feedback.hidden = true; }
brief.addEventListener('input', updateCount);
runMode.addEventListener('change', updateModeLabel);
document.querySelector('#sample').addEventListener('click', () => {
  if (brief.value.trim() && !window.confirm('填入示例会替换当前文字。是否继续？')) return;
  brief.value = '【虚构示例，仅用于体验】\n我们计划在英国推广一款轻量随行杯，希望通过 TikTok 和 Instagram 触达 20–35 岁、通勤并关注日常设计感的消费者，建立新品认知。\n\n希望突出便携、易清洁和适合日常通勤的使用体验，语气自然、克制。计划下月上线，预算与具体发布时间尚未确认。请勿添加环保认证、折扣或客户批准等未提供信息。';
  document.querySelector('#market').value = 'UK';
  document.querySelectorAll('[name="channel"]').forEach(input => { input.checked = true; });
  updateCount(); brief.focus();
});
document.querySelector('#capture-form').addEventListener('submit', async event => {
  event.preventDefault();
  const channels = [...document.querySelectorAll('[name="channel"]:checked')].map(input => input.value);
  if (!brief.value.trim() || !channels.length) {
    feedback.textContent = !brief.value.trim() ? '请先填写原始需求，再体验分析流程。' : '请至少选择一个传播渠道。';
    feedback.hidden = false;
    if (!brief.value.trim()) brief.focus();
    return;
  }
  const selectedMode = runMode.value;
  if (selectedMode === 'live_ai' && !window.confirm('这将通过服务端调用真实 OpenAI API，可能产生费用。是否继续分析？')) return;
  feedback.hidden = true;
  submitButton.disabled = true;
  submitButton.textContent = selectedMode === 'live_ai' ? '正在调用 OpenAI…' : '正在请求固定测试数据…';
  try {
    const apiResponse = await fetch('/api/capture/analyze', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        raw_text: brief.value,
        market: document.querySelector('#market').value,
        channels,
        mode: selectedMode,
      }),
    });
    const payload = await apiResponse.json().catch(() => ({}));
    if (!apiResponse.ok) {
      throw new Error(payload.error?.message || `本地 API 返回 ${apiResponse.status}`);
    }
    if (!['local_fixture', 'live_ai'].includes(payload.mode) || !payload.brief) {
      throw new Error('本地 API 返回了无法识别的工作状态');
    }
    window.location.assign('/clarify.html');
  } catch (error) {
    feedback.textContent = `分析失败：${error.message}。你填写的原始需求仍保留在页面中。`;
    feedback.hidden = false;
  } finally {
    submitButton.disabled = false;
    submitButton.innerHTML = '分析需求 <span aria-hidden="true">→</span>';
  }
});
document.querySelector('#close-demo').addEventListener('click', () => dialog.close());

async function restoreCaptureFromSession() {
  try {
    const response = await fetch('/api/workspace', {headers: {'Accept': 'application/json'}});
    if (!response.ok) return;
    const state = await response.json();
    brief.value = state.raw_text || '';
    document.querySelector('#market').value = state.brief.region.includes('美国') ? 'US' : state.brief.region.includes('英国') ? 'UK' : 'unknown';
    document.querySelectorAll('[name="channel"]').forEach(input => {
      input.checked = state.selected_channels.includes(input.value);
    });
    runMode.value = state.mode || 'local_fixture';
    updateModeLabel();
    updateCount();
  } catch (_) {
    // A missing local service leaves the editable Capture form untouched.
  }
}

window.addEventListener('pageshow', restoreCaptureFromSession);
updateModeLabel();
