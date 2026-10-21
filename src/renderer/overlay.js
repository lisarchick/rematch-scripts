const $ = (s) => document.querySelector(s);
applyLang();
const m = mountMenu($('#menu'));
api.onOverlayShown(() => { try { lang = localStorage.getItem('lang') || lang; } catch {} applyLang(); m.reload(); });
$('#ov-close').onclick = () => api.hideOverlay();
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !e.target.classList.contains('hk')) api.hideOverlay(); });
