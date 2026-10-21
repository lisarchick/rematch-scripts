const $ = (s) => document.querySelector(s);
const fmt = (b) => b > 1048576 ? (b / 1048576).toFixed(1) + (lang === 'ru' ? ' МБ' : ' MB') : Math.max(1, Math.round(b / 1024)) + (lang === 'ru' ? ' КБ' : ' KB');
let cfg, items = [], installed = {}, currentId = null, owner = false, menuCtl;
const upl = { images: [], files: [] };

function md(src) {
  let s = esc(src);
  s = s.replace(/```([\s\S]*?)```/g, (_, c) => `<pre>${c.trim()}</pre>`);
  s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>');
  return s.replace(/(<\/pre>)\n|\n/g, (m, p) => p ? p : '<br>');
}

function show(view) {
  for (const v of ['all', 'detail', 'menu', 'upload', 'settings']) $('#view-' + v).classList.toggle('hidden', v !== view);
  document.querySelectorAll('.nav').forEach(n => n.classList.toggle('active', n.dataset.view === (view === 'detail' ? 'all' : view)));
  if (view === 'menu') menuCtl.reload();
}
document.querySelectorAll('.nav').forEach(n => n.onclick = () => show(n.dataset.view));
$('#back').onclick = () => { currentId = null; show('all'); };
$('#open-overlay').onclick = () => api.toggleOverlay();

const imgUrl = (it, n) => `${cfg.raw}/library/${encodeURIComponent(it.id)}/images/${encodeURIComponent(n)}`;
const badge = (it) => {
  const r = installed[it.id]; if (!r) return '';
  return (it.version || 1) > (r.version || 1) ? `<span class="badge warn">${t('has_update')}</span>` : `<span class="badge">${t('in_menu')}</span>`;
};

function render() {
  const q = $('#search').value.trim().toLowerCase();
  const list = items.filter(i => !q || (i.title + i.description + i.author).toLowerCase().includes(q));
  $('#grid').innerHTML = list.map(i => `
    <div class="card" data-id="${esc(i.id)}">
      <div class="thumb" ${i.images[0] ? `style="background-image:url('${imgUrl(i, i.images[0])}')"` : ''}>${i.images[0] ? '' : '📦'}</div>
      <div class="body"><h3>${esc(i.title)} ${badge(i)}</h3><p>${esc(i.description)}</p>
      <div class="meta">${esc(i.author)} · ${t('files')}: ${i.files.length}</div></div>
    </div>`).join('') || `<p class="muted">${t('none')}</p>`;
  document.querySelectorAll('.card').forEach(c => c.onclick = () => openDetail(c.dataset.id));
}

function openDetail(id) {
  currentId = id;
  const it = items.find(i => i.id === id); if (!it) return;
  const rec = installed[id];
  const canInstall = !!it.entry;
  const upd = rec && (it.version || 1) > (rec.version || 1);
  $('#detail').innerHTML = `
    <h1>${esc(it.title)}</h1><div class="muted">${t('author')}: ${esc(it.author)}</div>
    ${it.images.length ? `<div class="gallery">${it.images.map(n => `<img src="${imgUrl(it, n)}">`).join('')}</div>` : ''}
    <p>${esc(it.description)}</p>
    ${canInstall ? `<div class="box inst">
      ${!rec || upd ? `<button class="primary big" id="inst">${upd ? t('update') : t('install')}</button>` : `<button class="primary big" id="gomenu">${t('open_menu')}</button><button class="ghost" id="uninst">${t('remove')}</button>`}
      <span class="muted" id="inst-msg"></span></div>` : ''}
    <div class="box"><h3>${t('instr')}</h3><div>${md(it.instructions) || `<span class="muted">${t('no_instr')}</span>`}</div></div>
    <details class="box"><summary>${t('manual')}</summary>
      ${it.files.map(f => `<div class="file"><span>${esc(f.name)} <small class="muted">${fmt(f.size)}</small></span><button class="ghost" data-f="${esc(f.name)}">${t('dl')}</button></div>`).join('') || `<span class="muted">${t('no_files')}</span>`}
      ${it.files.length > 1 ? `<div class="row"><button class="ghost" id="dl-all">${t('dl_all')}</button></div>` : ''}
      <div class="muted small" id="dl-msg" style="margin-top:8px"></div>
    </details>
    <p class="muted small">${t('risk')}</p>`;
  const dl = async (names) => {
    $('#dl-msg').textContent = t('downloading');
    try { const d = await api.download({ id: it.id, names, title: it.title }); $('#dl-msg').textContent = t('saved_to') + d; }
    catch (e) { $('#dl-msg').textContent = t('err') + e.message; }
  };
  $('#detail').querySelectorAll('[data-f]').forEach(b => b.onclick = () => dl([b.dataset.f]));
  $('#dl-all') && ($('#dl-all').onclick = () => dl(it.files.map(f => f.name)));
  $('#detail').querySelectorAll('.gallery img').forEach(im => im.onclick = () => { $('#lightbox img').src = im.src; $('#lightbox').classList.remove('hidden'); });
  $('#inst') && ($('#inst').onclick = async () => {
    $('#inst').disabled = true; $('#inst-msg').textContent = t('installing');
    try { await api.install(it); installed = await api.installed(); render(); openDetail(id); $('#inst-msg').textContent = t('done_installed'); }
    catch (e) { $('#inst-msg').textContent = t('err') + e.message; $('#inst').disabled = false; }
  });
  $('#gomenu') && ($('#gomenu').onclick = () => show('menu'));
  $('#uninst') && ($('#uninst').onclick = async () => { if (confirm(t('confirm_remove'))) { await api.uninstall(id); installed = await api.installed(); render(); openDetail(id); } });
  show('detail');
}
$('#lightbox').onclick = () => $('#lightbox').classList.add('hidden');

async function load() {
  $('#notice').classList.add('hidden');
  if (!cfg.configured) { $('#notice').textContent = t('not_cfg'); $('#notice').classList.remove('hidden'); return; }
  try { installed = await api.installed(); items = await api.library(); render(); }
  catch (e) { $('#notice').textContent = e.message; $('#notice').classList.remove('hidden'); }
}
$('#refresh').onclick = load;
$('#search').oninput = render;
window.addEventListener('menu-changed', async () => { installed = await api.installed(); render(); });

// ---------- загрузка (только владелец) ----------
function chips(kind) {
  $('#list-' + (kind === 'images' ? 'img' : 'files')).innerHTML = upl[kind].map((f, i) => `<span class="chip">${esc(f.name)} · ${fmt(f.size)}<b data-k="${kind}" data-i="${i}">×</b></span>`).join('');
  document.querySelectorAll('.chip b').forEach(b => b.onclick = () => { upl[b.dataset.k].splice(+b.dataset.i, 1); chips(b.dataset.k); });
}
function add(kind, list) {
  if (kind === 'images') list = list.filter(f => /\.(png|jpe?g|gif|webp)$/i.test(f.name));
  for (const f of list) if (!upl[kind].some(x => x.path === f.path)) upl[kind].push(f);
  chips(kind);
}
function setupDrop(id, kind) {
  const el = $(id);
  el.ondragover = (e) => { e.preventDefault(); el.classList.add('over'); };
  el.ondragleave = () => el.classList.remove('over');
  el.ondrop = async (e) => { e.preventDefault(); el.classList.remove('over'); add(kind, await api.describe(e.dataTransfer.files)); };
}
setupDrop('#drop-img', 'images'); setupDrop('#drop-files', 'files');
$('#pick-img').onclick = async () => add('images', await api.pick('images'));
$('#pick-files').onclick = async () => add('files', await api.pick('files'));

$('#form').onsubmit = async (e) => {
  e.preventDefault();
  const btn = $('#submit'), msg = $('#submit-msg');
  btn.disabled = true; msg.textContent = t('sending');
  try {
    const url = await api.submit({ title: $('#f-title').value, description: $('#f-desc').value, instructions: $('#f-instr').value,
      entry: $('#f-entry').value, settings: $('#f-settings').value, images: upl.images, files: upl.files });
    msg.innerHTML = t('sent') + ' <a id="pr-link">' + t('open_pr') + '</a>';
    $('#pr-link').onclick = () => api.openExternal(url);
    $('#form').reset(); upl.images = []; upl.files = []; chips('images'); chips('files');
  } catch (err) { msg.textContent = t('err') + err.message; }
  btn.disabled = false;
};

// ---------- настройки ----------
async function checkOwner() {
  const w = await api.whoami(); owner = !!w.owner;
  $('#nav-upload').classList.toggle('hidden', !owner);
  repoInfo();
}
function repoInfo() { $('#repo-info').textContent = t('repo') + `${cfg.owner}/${cfg.repo}` + (cfg.hasToken ? t('has_token') : '') + (owner ? t('owner_ok') : ''); }
$('#save-token').onclick = async () => {
  const ok = await api.saveToken($('#token').value); $('#token').value = '';
  cfg.hasToken = ok; $('#token-msg').textContent = ok ? t('tok_saved') : t('tok_removed'); await checkOwner();
};
$('#make-token').onclick = () => api.openExternal('https://github.com/settings/tokens/new?scopes=public_repo&description=Rematch%20Scripts');
$('#lang').onchange = () => {
  setLang($('#lang').value); repoInfo(); render(); menuCtl.reload();
  if (!$('#view-detail').classList.contains('hidden') && currentId) openDetail(currentId);
};
$('#ov-key').addEventListener('keydown', async (e) => {
  e.preventDefault();
  if (e.key === 'Escape') { e.target.blur(); return; }
  const k = e.key;
  if (['Control', 'Shift', 'Alt', 'Meta'].includes(k)) return;
  let key = /^F\d{1,2}$/.test(k) ? k : /^[a-zA-Z0-9]$/.test(k) ? k.toUpperCase() : ({ Insert: 'Insert', Home: 'Home', End: 'End', Delete: 'Delete', PageUp: 'PageUp', PageDown: 'PageDown' }[k]);
  if (!key) return;
  const mods = [e.ctrlKey && 'Ctrl', e.altKey && 'Alt', e.shiftKey && 'Shift'].filter(Boolean);
  const accel = [...mods, key].join('+');
  const ok = await api.setOverlayHotkey(accel);
  e.target.value = ok ? accel : t('hk_bad');
  if (!ok) setTimeout(async () => { e.target.value = await api.getOverlayHotkey(); }, 1200);
});

(async () => {
  cfg = await api.config();
  $('#lang').value = lang;
  applyLang();
  menuCtl = mountMenu($('#menu'));
  $('#ov-key').value = await api.getOverlayHotkey();
  repoInfo(); load(); checkOwner();
})();
