const { app, BrowserWindow, ipcMain, dialog, shell, safeStorage, globalShortcut, screen } = require('electron');
const { spawn, execFile } = require('child_process');
const path = require('path');
const fs = require('fs');
const cfg = require('../config.json');

const RAW = `https://raw.githubusercontent.com/${cfg.owner}/${cfg.repo}/${cfg.branch}`;
const API = 'https://api.github.com';
const MAX_FILE = 25 * 1024 * 1024;
const MAX_TOTAL = 60 * 1024 * 1024;
const REPO_URL = `https://github.com/${cfg.owner}/${cfg.repo}`;

let win, overlay;
function createWindow() {
  win = new BrowserWindow({
    width: 1200, height: 780, minWidth: 900, minHeight: 600,
    backgroundColor: '#0f1117', title: 'Rematch Scripts', autoHideMenuBar: true,
    icon: path.join(__dirname, '..', 'build', 'icon.png'),
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true }
  });
  win.removeMenu();
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  win.webContents.setWindowOpenHandler(({ url }) => { if (/^https:\/\//.test(url)) shell.openExternal(url); return { action: 'deny' }; });
  win.webContents.on('will-navigate', (e) => e.preventDefault());
}

const single = app.requestSingleInstanceLock();
if (!single) app.quit();
app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });
app.whenReady().then(() => {
  loadState();
  createWindow();
  createOverlay();
  registerOverlayHotkey();
  for (const id of Object.keys(state.installed)) {
    registerHotkey(id);
    if (state.installed[id].enabled) startScript(id).catch(() => {});
  }
});
app.on('window-all-closed', () => app.quit());
app.on('before-quit', () => { app.isQuitting = true; });
app.on('will-quit', () => { globalShortcut.unregisterAll(); stopAll(); });


// ---------- оверлей поверх игры ----------
function createOverlay() {
  overlay = new BrowserWindow({
    width: 440, height: 700, show: false, frame: false, alwaysOnTop: true, skipTaskbar: true, resizable: false,
    backgroundColor: '#0f1117', title: 'Rematch Scripts Overlay',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true }
  });
  overlay.setAlwaysOnTop(true, 'screen-saver');
  overlay.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  overlay.loadFile(path.join(__dirname, 'renderer', 'overlay.html'));
  overlay.webContents.setWindowOpenHandler(({ url }) => { if (/^https:\/\//.test(url)) shell.openExternal(url); return { action: 'deny' }; });
  overlay.webContents.on('will-navigate', (e) => e.preventDefault());
  overlay.on('close', (e) => { if (!app.isQuitting) { e.preventDefault(); overlay.hide(); } });
}
function toggleOverlay() {
  if (!overlay || overlay.isDestroyed()) createOverlay();
  if (overlay.isVisible()) { overlay.hide(); return; }
  const wa = screen.getPrimaryDisplay().workArea;
  const h = Math.min(720, wa.height - 40);
  overlay.setBounds({ x: wa.x + wa.width - 460, y: wa.y + 20, width: 440, height: h });
  overlay.setAlwaysOnTop(true, 'screen-saver');
  overlay.show(); overlay.focus();
  overlay.webContents.send('overlay-shown');
}
let ovAccel = '';
function registerOverlayHotkey() {
  if (ovAccel) { try { globalShortcut.unregister(ovAccel); } catch {} ovAccel = ''; }
  const a = state.overlayHotkey; if (!a) return true;
  try { if (globalShortcut.register(a, toggleOverlay)) { ovAccel = a; return true; } } catch {}
  return false;
}
ipcMain.handle('overlay-toggle', () => { toggleOverlay(); });
ipcMain.handle('overlay-hide', () => { if (overlay && !overlay.isDestroyed()) overlay.hide(); });
ipcMain.handle('get-overlay-hotkey', () => state.overlayHotkey);
ipcMain.handle('set-overlay-hotkey', (_e, accel) => {
  accel = String(accel || '').trim(); const prev = state.overlayHotkey;
  if (Object.values(state.installed).some(r => r.hotkey === accel)) return false;
  state.overlayHotkey = accel;
  if (!registerOverlayHotkey()) { state.overlayHotkey = prev; registerOverlayHotkey(); return false; }
  saveState(); return true;
});

// ---------- токен GitHub (шифруется системой) ----------
const tokenFile = () => path.join(app.getPath('userData'), 'gh.token');
function getToken() {
  try {
    const b = fs.readFileSync(tokenFile());
    return safeStorage.isEncryptionAvailable() ? safeStorage.decryptString(b) : b.toString('utf8');
  } catch { return ''; }
}
function setToken(t) {
  if (!t) { try { fs.unlinkSync(tokenFile()); } catch {} return; }
  fs.writeFileSync(tokenFile(), safeStorage.isEncryptionAvailable() ? safeStorage.encryptString(t) : Buffer.from(t));
}

// ---------- библиотека ----------
ipcMain.handle('config', () => ({ ...cfg, raw: RAW, repoUrl: REPO_URL, hasToken: !!getToken(), configured: cfg.owner !== 'YOUR_GITHUB_USERNAME' }));

ipcMain.handle('library', async () => {
  const r = await fetch(`${RAW}/library/index.json?t=${Date.now()}`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`Library load failed / Не удалось загрузить библиотеку (HTTP ${r.status})`);
  return r.json();
});

const safeSeg = (s) => String(s).replace(/[^\p{L}\p{N}._ -]/gu, '_').slice(0, 80);

async function fetchTo(dir, id, names) {
  fs.mkdirSync(dir, { recursive: true });
  for (const n of names) {
    const r = await fetch(`${RAW}/library/${encodeURIComponent(id)}/files/${encodeURIComponent(n)}?t=${Date.now()}`, { cache: 'no-store' });
    if (!r.ok) throw new Error(`Download failed / Ошибка скачивания ${n} (HTTP ${r.status})`);
    fs.writeFileSync(path.join(dir, path.basename(n)), Buffer.from(await r.arrayBuffer()));
  }
}

ipcMain.handle('download', async (_e, { id, names, title }) => {
  const dir = path.join(app.getPath('downloads'), 'RematchScripts', safeSeg(title || id));
  await fetchTo(dir, id, names);
  shell.openPath(dir);
  return dir;
});
ipcMain.handle('open-external', (_e, url) => { if (/^https:\/\//.test(url)) shell.openExternal(url); });

// ---------- меню: установленные скрипты ----------
const stateFile = () => path.join(app.getPath('userData'), 'state.json');
const scriptsDir = () => path.join(app.getPath('userData'), 'scripts');
let state = { installed: {} };
const procs = new Map();      // id -> child process
const status = new Map();     // id -> { status, log[] }

function loadState() { try { state = JSON.parse(fs.readFileSync(stateFile(), 'utf8')); } catch { state = { installed: {} }; } state.installed ||= {}; if (!('overlayHotkey' in state)) state.overlayHotkey = 'F10'; }
function saveState() { try { fs.mkdirSync(path.dirname(stateFile()), { recursive: true }); fs.writeFileSync(stateFile(), JSON.stringify(state, null, 1)); } catch {} }
const idOk = (id) => /^[\w.-]+$/.test(id) && id !== '.' && id !== '..';
const dirOf = (id) => path.join(scriptsDir(), id);

function st(id) { if (!status.has(id)) status.set(id, { status: 'stopped', log: [] }); return status.get(id); }
function send(ch, d) { for (const w of BrowserWindow.getAllWindows()) if (!w.isDestroyed()) w.webContents.send(ch, d); }
function push(id) { send('status', { id, ...st(id) }); }
function log(id, text) {
  const s = st(id);
  for (const line of String(text).split(/\r?\n/)) if (line.trim()) s.log.push(line);
  if (s.log.length > 200) s.log = s.log.slice(-200);
  push(id);
}
function setStatus(id, v) { st(id).status = v; push(id); }

function defaults(schema) { const v = {}; for (const s of schema || []) v[s.key] = s.default; return v; }
function writeConfig(id) {
  const rec = state.installed[id];
  fs.writeFileSync(path.join(dirOf(id), 'rematch_config.json'), JSON.stringify(rec.values));
}

ipcMain.handle('installed', () => Object.fromEntries(Object.entries(state.installed).map(([id, r]) => [id, { ...r, ...st(id) }])));

ipcMain.handle('install', async (_e, item) => {
  if (!idOk(item.id)) throw new Error('Bad id');
  const entry = path.basename(item.entry || '');
  if (!entry.endsWith('.py')) throw new Error('Script has no Python entry file / У скрипта нет файла запуска (.py)');
  const wasRunning = procs.has(item.id);
  if (wasRunning) stopScript(item.id);
  await fetchTo(dirOf(item.id), item.id, item.files.map(f => f.name));
  const prev = state.installed[item.id];
  const values = { ...defaults(item.settings), ...(prev ? prev.values : {}) };
  // оставляем только ключи, которые есть в схеме
  for (const k of Object.keys(values)) if (!(item.settings || []).some(s => s.key === k)) delete values[k];
  state.installed[item.id] = {
    id: item.id, title: item.title, version: item.version || 1, entry, settings: item.settings || [],
    values, enabled: prev ? prev.enabled : false, hotkey: prev ? prev.hotkey : '', depsOk: false
  };
  saveState(); writeConfig(item.id);
  if (wasRunning) startScript(item.id).catch(() => {});
  return true;
});

ipcMain.handle('uninstall', (_e, id) => {
  if (!state.installed[id]) return false;
  stopScript(id); unregisterHotkey(id);
  try { fs.rmSync(dirOf(id), { recursive: true, force: true }); } catch {}
  delete state.installed[id]; status.delete(id); saveState();
  return true;
});

ipcMain.handle('set-value', (_e, { id, key, value }) => {
  const rec = state.installed[id]; if (!rec) return false;
  const def = rec.settings.find(s => s.key === key); if (!def) return false;
  if (def.type === 'number') { value = Number(value); if (!Number.isFinite(value)) return false; value = Math.min(def.max ?? value, Math.max(def.min ?? value, value)); }
  else if (def.type === 'bool') value = !!value;
  else if (def.type === 'select') { if (!(def.options || []).some(o => o.value === value)) return false; }
  else return false;
  rec.values[key] = value; saveState(); writeConfig(id);
  if (def.restart && procs.has(id)) { stopScript(id); setTimeout(() => startScript(id).catch(() => {}), 500); }
  return true;
});

ipcMain.handle('reset-values', (_e, id) => {
  const rec = state.installed[id]; if (!rec) return false;
  rec.values = defaults(rec.settings); saveState(); writeConfig(id);
  if (procs.has(id)) { stopScript(id); setTimeout(() => startScript(id).catch(() => {}), 500); }
  return rec.values;
});

ipcMain.handle('toggle', async (_e, { id, on }) => {
  const rec = state.installed[id]; if (!rec) return false;
  if (on) { rec.enabled = true; saveState(); startScript(id).catch(() => {}); }
  else { rec.enabled = false; saveState(); stopScript(id); }
  return true;
});

// ---------- глобальные горячие клавиши для включения/выключения ----------
const hotkeys = new Map();
function unregisterHotkey(id) { const a = hotkeys.get(id); if (a) { try { globalShortcut.unregister(a); } catch {} hotkeys.delete(id); } }
function registerHotkey(id) {
  unregisterHotkey(id);
  const rec = state.installed[id]; if (!rec || !rec.hotkey) return true;
  try {
    const ok = globalShortcut.register(rec.hotkey, () => {
      const r = state.installed[id]; if (!r) return;
      r.enabled = !r.enabled; saveState();
      if (r.enabled) startScript(id).catch(() => {}); else stopScript(id);
      send('enabled', { id, enabled: r.enabled });
    });
    if (ok) hotkeys.set(id, rec.hotkey);
    return ok;
  } catch { return false; }
}
ipcMain.handle('set-hotkey', (_e, { id, accel }) => {
  const rec = state.installed[id]; if (!rec) return false;
  accel = String(accel || '').trim();
  if (accel && accel === state.overlayHotkey) return false;
  const prev = rec.hotkey; rec.hotkey = accel;
  const ok = registerHotkey(id);
  if (!ok) { rec.hotkey = prev; registerHotkey(id); return false; }
  saveState(); return true;
});

// ---------- запуск процессов ----------
let pyCache = null;
function findPython() {
  if (pyCache) return Promise.resolve(pyCache);
  const cands = process.platform === 'win32'
    ? [{ cmd: 'py', pre: ['-3'] }, { cmd: 'python', pre: [] }, { cmd: 'python3', pre: [] }]
    : [{ cmd: 'python3', pre: [] }, { cmd: 'python', pre: [] }];
  return new Promise((resolve) => {
    const next = (i) => {
      if (i >= cands.length) return resolve(null);
      execFile(cands[i].cmd, [...cands[i].pre, '--version'], { windowsHide: true, timeout: 8000 }, (err) => {
        if (err) return next(i + 1);
        pyCache = cands[i]; resolve(pyCache);
      });
    };
    next(0);
  });
}

function killTree(proc) {
  try {
    if (process.platform === 'win32') execFile('taskkill', ['/pid', String(proc.pid), '/T', '/F'], { windowsHide: true }, () => {});
    else proc.kill('SIGTERM');
  } catch {}
}

function runOnce(py, args, cwd, id) {
  return new Promise((resolve) => {
    const p = spawn(py.cmd, [...py.pre, ...args], { cwd, windowsHide: true });
    p.stdout.on('data', d => log(id, d)); p.stderr.on('data', d => log(id, d));
    p.on('error', e => { log(id, String(e)); resolve(1); });
    p.on('close', code => resolve(code));
  });
}

async function startScript(id) {
  const rec = state.installed[id]; if (!rec || procs.has(id)) return;
  const s = st(id); s.log = []; setStatus(id, 'starting');
  const py = await findPython();
  if (!py) { log(id, 'Python not found / Python не найден. https://www.python.org/downloads/'); setStatus(id, 'nopython'); return; }
  const cwd = dirOf(id);
  if (!rec.depsOk && fs.existsSync(path.join(cwd, 'requirements.txt'))) {
    log(id, 'Installing dependencies / Устанавливаю зависимости…');
    setStatus(id, 'installing');
    const code = await runOnce(py, ['-m', 'pip', 'install', '-r', 'requirements.txt'], cwd, id);
    if (code !== 0) { setStatus(id, 'error'); return; }
    rec.depsOk = true; saveState();
  }
  if (!state.installed[id] || !state.installed[id].enabled) { setStatus(id, 'stopped'); return; }  // выключили во время установки
  writeConfig(id);
  const p = spawn(py.cmd, [...py.pre, '-u', rec.entry], {
    cwd, windowsHide: true,
    env: { ...process.env, REMATCH_CONFIG: path.join(cwd, 'rematch_config.json'), PYTHONIOENCODING: 'utf-8' }
  });
  procs.set(id, p);
  setStatus(id, 'running');
  p.stdout.on('data', d => log(id, d)); p.stderr.on('data', d => log(id, d));
  p.on('error', e => { log(id, String(e)); procs.delete(id); setStatus(id, 'error'); });
  p.on('close', (code) => {
    if (procs.get(id) === p) procs.delete(id);
    const cur = state.installed[id];
    setStatus(id, code === 0 || code === null || !cur || !cur.enabled ? 'stopped' : 'error');
    if (code && cur && cur.enabled) { cur.enabled = false; saveState(); send('enabled', { id, enabled: false }); }
  });
}

function stopScript(id) {
  const p = procs.get(id);
  if (p) { procs.delete(id); killTree(p); }
  setStatus(id, 'stopped');
}
function stopAll() { for (const id of [...procs.keys()]) stopScript(id); }

// ---------- настройки ----------
ipcMain.handle('save-token', (_e, t) => { setToken((t || '').trim()); return !!getToken(); });

// владелец ли текущий токен (только владелец может загружать)
ipcMain.handle('whoami', async () => {
  const token = getToken();
  if (!token) return { owner: false };
  try {
    const r = await fetch(`${API}/user`, { headers: { Authorization: `Bearer ${token}`, 'User-Agent': 'rematch-scripts' } });
    if (!r.ok) return { owner: false };
    const me = await r.json();
    return { owner: me.login.toLowerCase() === cfg.owner.toLowerCase(), login: me.login };
  } catch { return { owner: false }; }
});

// ---------- выбор файлов ----------
ipcMain.handle('pick', async (_e, kind) => {
  const filters = kind === 'images'
    ? [{ name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'gif', 'webp'] }]
    : [{ name: 'All files', extensions: ['*'] }];
  const r = await dialog.showOpenDialog(win, { properties: ['openFile', 'multiSelections'], filters });
  return r.canceled ? [] : r.filePaths.map(describe);
});
function describe(p) { return { path: p, name: path.basename(p), size: fs.statSync(p).size }; }
ipcMain.handle('describe', (_e, paths) => paths.filter(p => fs.existsSync(p) && fs.statSync(p).isFile()).map(describe));

// ---------- публикация (только владелец, сразу в main) ----------
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9а-яё]+/gi, '-').replace(/^-|-$/g, '').slice(0, 40) || 'script';
const safeName = (n) => n.replace(/[^\w.\- ()а-яА-ЯёЁ]/g, '_');

async function gh(token, method, url, body) {
  const r = await fetch(url.startsWith('http') ? url : API + url, {
    method,
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'Content-Type': 'application/json', 'User-Agent': 'rematch-scripts' },
    body: body ? JSON.stringify(body) : undefined
  });
  const txt = await r.text();
  let j; try { j = txt ? JSON.parse(txt) : {}; } catch { j = {}; }
  if (!r.ok) throw new Error(`GitHub ${r.status}: ${j.message || txt.slice(0, 200)}`);
  return j;
}

ipcMain.handle('submit', async (_e, form) => {
  const token = getToken();
  if (!token) throw new Error('Add the owner token in Settings / Добавь токен владельца в «Настройках».');
  const me = await gh(token, 'GET', '/user');
  if (me.login.toLowerCase() !== cfg.owner.toLowerCase()) throw new Error('Only the library owner can upload / Загружать может только владелец библиотеки.');
  if (!form.title?.trim()) throw new Error('Enter a title / Укажи название.');
  if (!form.files?.length) throw new Error('Add at least one file / Добавь хотя бы один файл.');

  let settings = [];
  if (form.settings && form.settings.trim()) {
    try { settings = JSON.parse(form.settings); if (!Array.isArray(settings)) throw 0; }
    catch { throw new Error('Settings JSON is invalid / Некорректный JSON настроек.'); }
  }
  const entry = (form.entry || '').trim();
  if (entry && !form.files.some(f => f.name === entry)) throw new Error('Entry file is not among the files / Файла запуска нет среди файлов.');

  let total = 0;
  for (const f of [...form.files, ...form.images]) {
    const s = fs.statSync(f.path).size;
    if (s > MAX_FILE) throw new Error(`File too large (>25 MB) / Файл больше 25 МБ: ${f.name}`);
    total += s;
  }
  if (total > MAX_TOTAL) throw new Error('Total size over 60 MB / Суммарный размер больше 60 МБ.');

  const id = form.updateId && idOk(form.updateId) ? form.updateId : `${slug(form.title)}-${Date.now().toString(36)}`;
  const base = `/repos/${cfg.owner}/${cfg.repo}`;
  const head = await gh(token, 'GET', `${base}/git/ref/heads/${cfg.branch}`);
  const baseSha = head.object.sha;

  const entries = [];
  const blob = async (localPath, repoPath) => {
    const b = await gh(token, 'POST', `${base}/git/blobs`, { content: fs.readFileSync(localPath).toString('base64'), encoding: 'base64' });
    entries.push({ path: repoPath, mode: '100644', type: 'blob', sha: b.sha });
  };
  const meta = {
    title: form.title.trim().slice(0, 100), author: me.login,
    description: (form.description || '').slice(0, 2000), instructions: (form.instructions || '').slice(0, 10000),
    version: Date.now(), entry, settings
  };
  const mb = await gh(token, 'POST', `${base}/git/blobs`, { content: JSON.stringify(meta, null, 2), encoding: 'utf-8' });
  entries.push({ path: `library/${id}/script.json`, mode: '100644', type: 'blob', sha: mb.sha });
  for (const f of form.files) await blob(f.path, `library/${id}/files/${safeName(f.name)}`);
  for (const f of form.images) await blob(f.path, `library/${id}/images/${safeName(f.name)}`);

  const tree = await gh(token, 'POST', `${base}/git/trees`, { base_tree: baseSha, tree: entries });
  const commit = await gh(token, 'POST', `${base}/git/commits`, { message: `Add/update script: ${meta.title}`, tree: tree.sha, parents: [baseSha] });
  await gh(token, 'PATCH', `${base}/git/refs/heads/${cfg.branch}`, { sha: commit.sha });
  return `${REPO_URL}/tree/${cfg.branch}/library/${id}`;
});
