const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const state = {posts: [], brand: {}, status: {}, events: [], automation: {}, filter: 'all', view: 'overview', editing: null, dirty: false, calendar: new Date()};
const labels = {draft: 'Rascunho', scheduled: 'Agendado', publishing: 'Enviando', published: 'Publicado', simulated: 'Simulado', failed: 'Falhou', review_required: 'Conferir no Instagram'};
const viewLabels = {reels: 'Estúdio de Reels', overview: 'Visão geral', posts: 'Conteúdos', calendar: 'Calendário', automation: 'Automação', brand: 'Minha marca', connection: 'Integração'};
let toastTimer;

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
function toast(message, error = false) {
  const target = $('#toast');
  target.textContent = message;
  target.classList.toggle('error', error);
  target.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { target.hidden = true; }, error ? 9000 : 4500);
}
async function api(path, options = {}) {
  const response = await fetch('/api' + path, {
    ...options,
    headers: options.body instanceof File ? {} : {'Content-Type': 'application/json', ...options.headers},
    body: options.body instanceof File ? options.body : options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if (response.status === 401) { window.location.assign('/login'); throw new Error('Entre para continuar.'); }
  let data;
  try { data = await response.json(); } catch { throw new Error('O servidor não respondeu como esperado.'); }
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map(item => `${item.loc.at(-1)}: ${item.msg}`).join('; ') : data.detail;
    throw new Error(detail || 'Não foi possível completar a ação.');
  }
  return data;
}
async function busy(button, action, message) {
  const original = button.textContent;
  button.disabled = true;
  if (message) button.textContent = message;
  try { await action(); } catch (error) { toast(error.message, true); }
  finally { button.textContent = original; button.disabled = false; }
}
function formatDate(value, options = {}) {
  return new Intl.DateTimeFormat('pt-BR', {timeZone: state.status.timezone || 'America/Sao_Paulo', day: '2-digit', month: 'short', ...options}).format(new Date(value));
}
function dateKey(value) {
  return new Intl.DateTimeFormat('sv-SE', {timeZone: state.status.timezone || 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date(value));
}
function showView(name) {
  if (!viewLabels[name]) return;
  state.view = name;
  $$('.view').forEach(element => { element.hidden = element.id !== `view-${name}`; });
  $$('.nav-item').forEach(element => element.classList.toggle('active', element.dataset.view === name));
  $('#breadcrumb').textContent = viewLabels[name];
  if (name === 'calendar') renderCalendar();
  if (name === 'connection') renderConnection();
  if (name === 'automation') api('/automation').then(data => { state.automation = data; renderAutomation(); }).catch(error => toast(error.message, true));
  window.dispatchEvent(new CustomEvent('workspace-view', {detail: name}));
  window.scrollTo({top: 0, behavior: 'instant'});
}
function badge(post) { return node('span', `badge ${post.status}`, labels[post.status] || post.status); }
function postCard(post) {
  const card = node('article', 'post-card');
  const image = node('img', 'post-thumb');
  image.src = '/media/' + encodeURIComponent(post.image);
  image.alt = post.alt_text;
  image.loading = 'lazy';
  card.append(image);
  const content = node('div', 'post-content');
  content.append(badge(post), node('h3', '', post.title), node('p', 'caption-excerpt', post.caption));
  const bottom = node('div', 'post-card-bottom');
  bottom.append(node('span', '', formatDate(post.scheduled_at || post.created_at)));
  const button = node('button', '', 'Abrir post ↗');
  button.addEventListener('click', () => openEditor(post.id));
  bottom.append(button);
  content.append(bottom);
  card.append(content);
  return card;
}
function emptyState(target, filtered = false) {
  const empty = node('div', 'empty-state');
  empty.append(node('div', 'empty-icon', '✧'), node('h3', '', filtered ? 'Ainda não há conteúdo por aqui.' : 'Toda conexão começa com uma ideia.'), node('p', '', filtered ? 'Experimente outro filtro ou crie um novo rascunho.' : 'Transforme seu conhecimento em um post com a identidade da Auto Posts.'));
  const button = node('button', 'secondary', '＋ Criar meu primeiro conteúdo');
  button.addEventListener('click', openCreate);
  empty.append(button);
  target.append(empty);
}
function renderPosts() {
  const overview = $('#overview-posts');
  overview.replaceChildren();
  state.posts.slice(0, 3).forEach(post => overview.append(postCard(post)));
  if (!state.posts.length) emptyState(overview);
  const all = $('#all-posts');
  all.replaceChildren();
  const filtered = state.posts.filter(post => state.filter === 'all' || (state.filter === 'attention' ? ['failed', 'review_required'].includes(post.status) : post.status === state.filter));
  filtered.forEach(post => all.append(postCard(post)));
  if (!filtered.length) emptyState(all, state.filter !== 'all');
  $('#nav-count').textContent = state.posts.length;
  $('#stat-total').textContent = state.posts.length;
  $('#stat-scheduled').textContent = state.posts.filter(post => post.status === 'scheduled').length;
  $('#stat-published').textContent = state.posts.filter(post => post.status === 'published').length;
  const simulated = state.posts.filter(post => post.status === 'simulated').length;
  $('#simulated-note').textContent = simulated ? `${simulated} ${simulated === 1 ? 'simulação realizada' : 'simulações realizadas'} à parte` : 'Somente envios reais confirmados';
  const upcoming = $('#upcoming');
  upcoming.replaceChildren();
  const scheduled = state.posts.filter(post => post.status === 'scheduled').sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));
  scheduled.slice(0, 3).forEach(post => {
    const row = node('div', 'upcoming-row');
    const date = node('div', 'date-square', formatDate(post.scheduled_at, {day: '2-digit', month: undefined}));
    date.append(node('span', '', formatDate(post.scheduled_at, {day: undefined, month: 'short'})));
    const body = node('div');
    body.append(node('strong', '', post.title), node('small', '', `${formatDate(post.scheduled_at, {hour: '2-digit', minute: '2-digit'})} · ${post.delivery_mode === 'demo' ? 'Simulação' : 'Envio real'}`));
    row.append(date, body);
    upcoming.append(row);
  });
  if (!scheduled.length) upcoming.append(node('div', 'upcoming-empty', 'Sua agenda está aberta.\nAprove um rascunho e escolha o melhor momento.'));
  if (state.view === 'calendar') renderCalendar();
}
function renderCalendar() {
  const year = state.calendar.getFullYear(), month = state.calendar.getMonth();
  $('#calendar-month').textContent = new Intl.DateTimeFormat('pt-BR', {month: 'long', year: 'numeric', timeZone: 'UTC'}).format(new Date(Date.UTC(year, month, 15)));
  const grid = $('#calendar-grid');
  grid.replaceChildren();
  const first = new Date(year, month, 1).getDay(), days = new Date(year, month + 1, 0).getDate();
  const cells = Math.ceil((first + days) / 7) * 7;
  const today = dateKey(Date.now());
  for (let index = 0; index < cells; index++) {
    const day = index - first + 1;
    const cell = node('div', 'calendar-cell');
    if (day < 1 || day > days) { cell.classList.add('empty'); grid.append(cell); continue; }
    const key = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    if (key === today) cell.classList.add('today');
    cell.append(node('span', 'day-number', day));
    state.posts.filter(post => ['scheduled', 'published', 'simulated'].includes(post.status) && dateKey(post.published_at || post.scheduled_at) === key).forEach(post => {
      const entry = node('button', `calendar-entry ${post.status}`, post.title);
      entry.title = `${labels[post.status]} · ${post.title}`;
      entry.addEventListener('click', () => openEditor(post.id));
      cell.append(entry);
    });
    grid.append(cell);
  }
}
function renderBrand() {
  for (const [key, value] of Object.entries(state.brand)) {
    const input = $('#brand-form').elements.namedItem(key);
    if (input) input.value = value;
  }
  $('#sidebar-brand').textContent = state.brand.name;
  $('#cover-credit').textContent = state.brand.signature || '';
  $$('.avatar').forEach(element => { element.textContent = state.brand.name?.slice(0, 1).toUpperCase() || 'A'; });
}
function renderConnection() {
  const target = $('#connection-checklist');
  target.replaceChildren();
  [[state.status.meta_configured, 'Credenciais Meta configuradas'], [state.status.public_url_configured, 'Endereço público das imagens'], [state.status.auth_enabled, 'Painel protegido por senha'], [state.status.mode === 'live', 'Modo de publicação real']].forEach(([ready, text]) => {
    const item = node('li', ready ? 'ready' : '');
    item.append(node('span', '', ready ? '✓' : '○'), node('span', '', text));
    target.append(item);
  });
  const activity = $('#activity');
  activity.replaceChildren();
  const actions = {created: 'Rascunho criado', edited: 'Conteúdo atualizado', scheduled: 'Agendado', cancelled: 'Agendamento cancelado', claimed: 'Envio iniciado', ...labels};
  state.events.slice(0, 12).forEach(event => {
    const row = node('div', 'activity-row'), body = node('div');
    const post = state.posts.find(item => item.id === event.post_id);
    body.append(node('strong', '', actions[event.action] || event.action), node('span', '', post?.title || 'Publicação'));
    row.append(body, node('time', '', formatDate(event.created_at, {hour: '2-digit', minute: '2-digit'})));
    activity.append(row);
  });
  if (!state.events.length) activity.append(node('p', 'help', 'A atividade aparecerá aqui quando você criar seu primeiro conteúdo.'));
}
async function refresh() {
  const [posts, events] = await Promise.all([api('/posts'), api('/events')]);
  state.posts = posts; state.events = events;
  renderPosts();
  if (state.view === 'connection') renderConnection();
}
function renderAutomation() {
  const rule = state.automation;
  $('#automation-enabled').checked = rule.active;
  $('#automation-topics').value = rule.topics.join('\n');
  $('#automation-time').value = rule.time;
  const days = rule.days.join(',');
  if (!$('#automation-days').querySelector(`option[value="${days}"]`)) {
    const option = node('option', '', 'Dias personalizados'); option.value = days;
    $('#automation-days').append(option);
  }
  $('#automation-days').value = days;
  $('#automation-objective').value = rule.objective;
  $('#automation-approved').checked = false;
  $('#automation-state').textContent = rule.active ? 'Ativa' : 'Desativada';
  $('#automation-state').className = 'badge ' + (rule.active ? 'published' : 'draft');
  $('#automation-next').textContent = rule.next_run ? `Próximo horário: ${formatDate(rule.next_run, {hour: '2-digit', minute: '2-digit'})} · ${state.status.timezone}` : 'A rotina está desativada ou precisa de nova autorização para este modo e conta.';
  $('#automation-mode-note').textContent = state.status.mode === 'demo' ? 'Modo demonstração: a rotina cria os conteúdos e simula os envios. Nada será publicado no Instagram.' : 'Modo real: esta autorização permite publicar automaticamente na conta conectada. Revise os temas antes de ativar.';
  const runs = $('#automation-runs'); runs.replaceChildren();
  rule.runs.slice(0, 8).forEach(run => {
    const row = node('div', 'activity-row'), body = node('div');
    body.append(node('strong', '', labels[run.status] || ({running:'Executando',cancelled:'Cancelada'}[run.status]) || run.status), node('span', '', run.detail || 'Rotina recorrente'));
    row.append(body, node('time', '', formatDate(run.created_at, {hour:'2-digit',minute:'2-digit'}))); runs.append(row);
  });
  if (!rule.runs.length) runs.append(node('p', 'help', 'Nenhuma execução realizada.'));
}
function openCreate() {
  $('#create-dialog').showModal();
  $('#topic').focus();
}
function editorDirty(dirty) {
  state.dirty = dirty;
  $('#approve-post').checked = false;
  updateApproval();
}
function updateApproval() {
  const permitted = $('#approve-post').checked && !state.dirty;
  $('#schedule-button').disabled = !permitted;
  $('#publish-button').disabled = !permitted;
}
function openEditor(postId) {
  const post = state.posts.find(item => item.id === postId);
  if (!post) return;
  state.editing = post.id;
  $('#edit-title').value = post.title;
  $('#edit-caption').value = post.caption;
  $('#edit-alt').value = post.alt_text;
  $('#edit-image').src = '/media/' + encodeURIComponent(post.image);
  $('#edit-image').alt = post.alt_text;
  $('#regenerate-image').checked = false;
  $('#image-upload').value = '';
  $('#caption-count').textContent = `${post.caption.length}/2200`;
  $('#post-state').replaceChildren(badge(post));
  if (post.scheduled_at) $('#post-state').append(node('span', '', ` · ${formatDate(post.scheduled_at, {hour: '2-digit', minute: '2-digit'})}`));
  $('#post-error').textContent = post.error || (post.status === 'simulated' ? 'Simulação concluída. Nenhum conteúdo foi enviado ao Instagram.' : post.status === 'published' ? `Envio confirmado pela Meta. ID: ${post.media_id}` : '');
  const editable = ['draft', 'failed', 'scheduled'].includes(post.status);
  $$('#edit-form input, #edit-form textarea, #edit-form button').forEach(element => { element.disabled = !editable; });
  $('#image-upload').disabled = !editable;
  $('#publish-controls').hidden = !['draft', 'failed'].includes(post.status);
  $('#cancel-schedule').hidden = post.status !== 'scheduled';
  $('#publish-button').textContent = state.status.mode === 'demo' ? 'Simular agora ↗' : 'Publicar no Instagram ↗';
  editorDirty(false);
  if (!$('#edit-dialog').open) $('#edit-dialog').showModal();
}

document.addEventListener('click', event => {
  const navigation = event.target.closest('[data-view]');
  if (navigation) showView(navigation.dataset.view);
  if (event.target.closest('.create-trigger') || event.target.closest('#sidebar-create')) openCreate();
  if (event.target.closest('.close-dialog')) {
    if (event.target.closest('dialog')?.id === 'edit-dialog' && state.dirty && !window.confirm('Fechar e descartar as alterações que ainda não foram salvas?')) return;
    event.target.closest('dialog')?.close();
  }
});
$('#edit-dialog').addEventListener('cancel', event => {
  if (state.dirty && !window.confirm('Descartar as alterações que ainda não foram salvas?')) event.preventDefault();
});
$('#filters').addEventListener('click', event => {
  const button = event.target.closest('[data-filter]');
  if (!button) return;
  state.filter = button.dataset.filter;
  $$('.filter').forEach(element => element.classList.toggle('active', element === button));
  renderPosts();
});
$('#prev-month').addEventListener('click', () => { state.calendar = new Date(state.calendar.getFullYear(), state.calendar.getMonth() - 1, 1); renderCalendar(); });
$('#next-month').addEventListener('click', () => { state.calendar = new Date(state.calendar.getFullYear(), state.calendar.getMonth() + 1, 1); renderCalendar(); });
$('#create-form').addEventListener('submit', event => {
  event.preventDefault();
  busy($('#generate-button'), async () => {
    const post = await api('/posts/generate', {method: 'POST', body: {topic: $('#topic').value, objective: $('#objective').value}});
    await refresh();
    $('#create-dialog').close();
    $('#create-form').reset();
    openEditor(post.id);
    toast('Rascunho criado. Dê o seu toque antes de publicar.');
  }, 'Preparando legenda e arte…');
});
$('#brand-form').addEventListener('submit', event => {
  event.preventDefault();
  busy(event.currentTarget.querySelector('button'), async () => {
    state.brand = await api('/brand', {method: 'PUT', body: Object.fromEntries(new FormData($('#brand-form')))});
    renderBrand(); toast('Marca salva. Autorize novamente a rotina automática, se desejar mantê-la ativa.');
  }, 'Salvando…');
});
$('#automation-form').addEventListener('submit', event => {
  event.preventDefault();
  busy(event.currentTarget.querySelector('button'), async () => {
    const enabled = $('#automation-enabled').checked;
    if (enabled && state.status.mode === 'live' && !window.confirm('Autorizar a criação e publicação automática destes temas, sem revisar cada post?')) return;
    state.automation = await api('/automation', {method:'PUT',body:{enabled, time:$('#automation-time').value, days:$('#automation-days').value.split(',').map(Number), topics:$('#automation-topics').value.split('\n').filter(line => line.trim()), objective:$('#automation-objective').value, approved:$('#automation-approved').checked}});
    renderAutomation(); toast(enabled ? 'Rotina ativada para o próximo horário escolhido.' : 'Rotina desativada.');
  }, 'Salvando…');
});
$('#edit-form').addEventListener('input', () => { editorDirty(true); $('#caption-count').textContent = `${$('#edit-caption').value.length}/2200`; });
$('#edit-form').addEventListener('submit', event => {
  event.preventDefault();
  busy($('#save-post'), async () => {
    await api(`/posts/${state.editing}`, {method: 'PUT', body: {title: $('#edit-title').value, caption: $('#edit-caption').value, alt_text: $('#edit-alt').value, regenerate_image: $('#regenerate-image').checked}});
    await refresh(); openEditor(state.editing); toast('Alterações salvas. Revise e aprove o conteúdo.');
  }, 'Salvando…');
});
$('#image-upload').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  if (state.dirty) { toast('Salve as alterações do texto antes de enviar outra imagem.', true); event.target.value = ''; return; }
  if (file.size > 8000000) { toast('O limite por imagem é 8 MB.', true); event.target.value = ''; return; }
  event.target.disabled = true;
  try {
    await api(`/posts/${state.editing}/image`, {method: 'POST', body: file});
    await refresh(); openEditor(state.editing); toast('Imagem atualizada. Revise a descrição de acessibilidade.');
  } catch (error) { toast(error.message, true); }
  finally { event.target.disabled = false; }
});
$('#approve-post').addEventListener('change', updateApproval);
$('#schedule-button').addEventListener('click', () => busy($('#schedule-button'), async () => {
  const value = $('#schedule-at').value;
  if (!value) throw new Error('Escolha a data e a hora do agendamento.');
  await api(`/posts/${state.editing}/schedule`, {method: 'POST', body: {approved: $('#approve-post').checked, scheduled_at: new Date(value).toISOString()}});
  await refresh(); openEditor(state.editing); toast('Agendamento salvo. Mantenha o servidor em execução para processar a fila.');
}, 'Agendando…'));
$('#publish-button').addEventListener('click', () => {
  if (state.status.mode === 'live' && !window.confirm('Publicar agora este conteúdo na conta de Instagram conectada?')) return;
  busy($('#publish-button'), async () => {
    $('#schedule-button').disabled = true;
    const post = await api(`/posts/${state.editing}/publish`, {method: 'POST', body: {approved: $('#approve-post').checked}});
    await refresh(); openEditor(state.editing);
    if (['failed', 'review_required'].includes(post.status)) toast(post.error, true);
    else toast(post.status === 'simulated' ? 'Simulação concluída. Nenhum envio real foi feito.' : 'Publicação confirmada pela Meta.');
  }, 'Processando envio…');
});
$('#cancel-schedule').addEventListener('click', () => busy($('#cancel-schedule'), async () => {
  await api(`/posts/${state.editing}/cancel`, {method: 'POST'});
  await refresh(); openEditor(state.editing); toast('Agendamento cancelado. O conteúdo voltou para rascunho.');
}));
$('#test-connection').addEventListener('click', () => busy($('#test-connection'), async () => {
  const account = await api('/meta/test', {method: 'POST'});
  $('#connection-result').textContent = `Conta verificada: @${account.username || account.id}. ${state.status.mode === 'demo' ? 'Os envios continuam simulados até ativar o modo real.' : 'Modo real ativo. A conta pode receber publicações aprovadas.'}`;
}, 'Verificando…'));
$('#logout').addEventListener('click', async () => { try { await api('/logout', {method: 'POST'}); window.location.assign('/login'); } catch (error) { toast(error.message, true); } });

async function init() {
  try {
    [state.status, state.brand] = await Promise.all([api('/status'), api('/brand')]);
    const [year, month] = dateKey(Date.now()).split('-').map(Number);
    state.calendar = new Date(year, month - 1, 1);
    $('#today').textContent = formatDate(Date.now(), {year: 'numeric'});
    $('#year').textContent = year;
    $('#mode-chip').textContent = state.status.mode === 'demo' ? 'Modo demonstração' : 'Publicação real ativa';
    $('#mode-chip').classList.toggle('live', state.status.mode === 'live');
    $('#demo-banner').hidden = state.status.mode !== 'demo';
    $('#logout').hidden = !state.status.auth_enabled;
    $$('.timezone-label').forEach(element => { element.textContent = state.status.timezone; });
    $('#schedule-zone').textContent = Intl.DateTimeFormat().resolvedOptions().timeZone + ' (seu navegador)';
    $('#generation-note').textContent = state.status.ai_enabled ? 'A IA vai preparar uma legenda e uma arte. Revise todas as informações antes de publicar.' : 'Vamos usar um modelo local de texto e gerar uma arte JPEG. Personalize a legenda antes de aprovar.';
    renderBrand(); renderConnection(); await refresh();
    window.dispatchEvent(new CustomEvent('app-ready',{detail:state.status}));
    setInterval(() => { if (!document.hidden) refresh().catch(() => {}); }, 15000);
  } catch (error) { toast('Não foi possível carregar o painel. ' + error.message, true); }
}
init();
