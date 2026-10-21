// Общее меню скриптов: используется и в главном окне, и в оверлее.
(function () {
  const loc = (l) => typeof l === 'string' ? l : (l && (l[lang] || l.en || l.ru)) || '';
  const ST = { stopped: 'st_stopped', starting: 'st_starting', installing: 'st_installing', running: 'st_running', error: 'st_error', nopython: 'st_nopython' };
  const timers = {};
  let listenersSet = false;

  function accelFromEvent(e) {
    const k = e.key;
    if (['Control', 'Shift', 'Alt', 'Meta'].includes(k)) return null;
    let key = null;
    if (/^F\d{1,2}$/.test(k)) key = k;
    else if (/^[a-zA-Z0-9]$/.test(k)) key = k.toUpperCase();
    else key = { ' ': 'Space', Insert: 'Insert', Delete: 'Delete', Home: 'Home', End: 'End', PageUp: 'PageUp', PageDown: 'PageDown', ArrowUp: 'Up', ArrowDown: 'Down', ArrowLeft: 'Left', ArrowRight: 'Right', '`': '`', '-': '-', '=': '=' }[k] || null;
    if (!key) return null;
    const m = []; if (e.ctrlKey) m.push('Ctrl'); if (e.altKey) m.push('Alt'); if (e.shiftKey) m.push('Shift');
    return [...m, key].join('+');
  }

  function control(id, s, val) {
    const lab = esc(loc(s.label));
    if (s.type === 'bool') return `<div class="ctl row"><span>${lab}</span><label class="sw sm"><input type="checkbox" data-k="${esc(s.key)}" ${val ? 'checked' : ''}><i></i></label></div>`;
    if (s.type === 'select') return `<div class="ctl"><span>${lab}</span><select data-k="${esc(s.key)}">${(s.options || []).map(o => `<option value="${esc(o.value)}" ${o.value === val ? 'selected' : ''}>${esc(loc(o.label))}</option>`).join('')}</select></div>`;
    return `<div class="ctl"><span>${lab}</span><div class="rng"><input type="range" data-k="${esc(s.key)}" min="${s.min}" max="${s.max}" step="${s.step || 1}" value="${val}"><input type="number" class="num" data-n="${esc(s.key)}" min="${s.min}" max="${s.max}" step="${s.step || 1}" value="${val}"></div></div>`;
  }

  function card(rec, open) {
    let lastGroup = null, body = '';
    for (const s of rec.settings) {
      if ((s.group || null) !== lastGroup) { lastGroup = s.group || null; if (lastGroup) body += `<div class="grp">${esc(t('group_' + lastGroup))}</div>`; }
      body += control(rec.id, s, rec.values[s.key]);
    }
    const stTxt = t(ST[rec.status] || 'st_stopped');
    return `<div class="mcard" data-id="${esc(rec.id)}">
      <div class="mhead">
        <span class="dot st-${esc(rec.status)}"></span>
        <div class="mtitle"><b>${esc(rec.title)}</b><small class="mst">${esc(stTxt)}</small></div>
        ${rec.settings.length ? `<button class="ghost gear" title="${esc(t('gear'))}">⚙</button>` : ''}
        <label class="sw"><input type="checkbox" class="tg" ${rec.enabled ? 'checked' : ''}><i></i></label>
      </div>
      <div class="mnopy ${rec.status === 'nopython' ? '' : 'hidden'}">${esc(t('no_python'))} <a class="getpy">${esc(t('get_python'))}</a></div>
      <div class="mbody ${open ? '' : 'hidden'}">
        ${body}
        <div class="grp">${esc(t('hk_toggle'))}</div>
        <div class="ctl row"><input class="hk" readonly value="${esc(rec.hotkey || '')}" placeholder="${esc(t('hk_press'))}"><button class="ghost clrhk">${esc(t('hk_clear'))}</button></div>
        <div class="row end"><button class="ghost reset">${esc(t('reset'))}</button><button class="ghost rm">${esc(t('remove'))}</button></div>
        <details><summary>${esc(t('log'))}</summary><pre class="mlog">${esc((rec.log || []).slice(-30).join('\n'))}</pre></details>
      </div>
    </div>`;
  }

  window.mountMenu = function (root) {
    const open = new Set();
    let data = {};

    async function reload() {
      data = await api.installed();
      const ids = Object.keys(data);
      root.innerHTML = ids.length ? ids.map(id => card(data[id], open.has(id))).join('') : `<p class="muted">${esc(t('menu_empty'))}</p>`;
    }
    const cardOf = (el) => el.closest('.mcard');

    root.addEventListener('click', async (e) => {
      const c = cardOf(e.target); if (!c) return;
      const id = c.dataset.id;
      if (e.target.closest('.gear')) { c.querySelector('.mbody').classList.toggle('hidden'); open.has(id) ? open.delete(id) : open.add(id); }
      else if (e.target.closest('.reset')) { await api.resetValues(id); await reload(); }
      else if (e.target.closest('.rm')) { if (confirm(t('confirm_remove'))) { await api.uninstall(id); open.delete(id); await reload(); window.dispatchEvent(new Event('menu-changed')); } }
      else if (e.target.closest('.clrhk')) { await api.setHotkey(id, ''); c.querySelector('.hk').value = ''; }
      else if (e.target.closest('.getpy')) api.openExternal('https://www.python.org/downloads/');
    });

    root.addEventListener('change', async (e) => {
      const c = cardOf(e.target); if (!c) return;
      const id = c.dataset.id, el = e.target;
      if (el.classList.contains('tg')) { await api.toggle(id, el.checked); return; }
      if (el.dataset.n) {                       // число рядом со слайдером
        const r = c.querySelector(`input[type=range][data-k="${el.dataset.n}"]`); r.value = el.value; await api.setValue(id, el.dataset.n, el.value); return;
      }
      if (el.dataset.k) {
        if (el.type === 'checkbox') await api.setValue(id, el.dataset.k, el.checked);
        else if (el.tagName === 'SELECT') await api.setValue(id, el.dataset.k, el.value);
      }
    });

    root.addEventListener('input', (e) => {
      const el = e.target, c = cardOf(el); if (!c || el.type !== 'range') return;
      const id = c.dataset.id, k = el.dataset.k;
      const n = c.querySelector(`input[data-n="${k}"]`); if (n) n.value = el.value;
      clearTimeout(timers[id + k]);
      timers[id + k] = setTimeout(() => api.setValue(id, k, el.value), 120);
    });

    root.addEventListener('keydown', async (e) => {
      if (!e.target.classList.contains('hk')) return;
      e.preventDefault(); e.stopPropagation();
      if (e.key === 'Escape' || e.key === 'Backspace') { e.target.blur(); return; }
      const a = accelFromEvent(e); if (!a) return;
      const id = cardOf(e.target).dataset.id;
      const ok = await api.setHotkey(id, a);
      e.target.value = ok ? a : t('hk_bad'); if (!ok) setTimeout(() => { e.target.value = (data[id] && data[id].hotkey) || ''; }, 1200); else data[id].hotkey = a;
    });

    if (!listenersSet) {
      listenersSet = true;
      api.onStatus(({ id, status, log }) => {
        document.querySelectorAll(`.mcard[data-id="${CSS.escape(id)}"]`).forEach(c => {
          c.querySelector('.dot').className = 'dot st-' + status;
          c.querySelector('.mst').textContent = t(ST[status] || 'st_stopped');
          c.querySelector('.mnopy').classList.toggle('hidden', status !== 'nopython');
          const pre = c.querySelector('.mlog'); if (pre) pre.textContent = (log || []).slice(-30).join('\n');
        });
      });
      api.onEnabled(({ id, enabled }) => document.querySelectorAll(`.mcard[data-id="${CSS.escape(id)}"] .tg`).forEach(i => i.checked = enabled));
    }
    reload();
    return { reload };
  };
})();
