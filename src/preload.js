const { contextBridge, ipcRenderer, webUtils } = require('electron');
const on = (ch, cb) => { const h = (_e, d) => cb(d); ipcRenderer.on(ch, h); };
contextBridge.exposeInMainWorld('api', {
  config: () => ipcRenderer.invoke('config'),
  library: () => ipcRenderer.invoke('library'),
  download: (o) => ipcRenderer.invoke('download', o),
  openExternal: (u) => ipcRenderer.invoke('open-external', u),
  saveToken: (t) => ipcRenderer.invoke('save-token', t),
  whoami: () => ipcRenderer.invoke('whoami'),
  pick: (k) => ipcRenderer.invoke('pick', k),
  describe: (files) => ipcRenderer.invoke('describe', Array.from(files).map(f => webUtils.getPathForFile(f))),
  submit: (f) => ipcRenderer.invoke('submit', f),
  installed: () => ipcRenderer.invoke('installed'),
  install: (item) => ipcRenderer.invoke('install', item),
  uninstall: (id) => ipcRenderer.invoke('uninstall', id),
  toggle: (id, on) => ipcRenderer.invoke('toggle', { id, on }),
  setValue: (id, key, value) => ipcRenderer.invoke('set-value', { id, key, value }),
  resetValues: (id) => ipcRenderer.invoke('reset-values', id),
  setHotkey: (id, accel) => ipcRenderer.invoke('set-hotkey', { id, accel }),
  toggleOverlay: () => ipcRenderer.invoke('overlay-toggle'),
  hideOverlay: () => ipcRenderer.invoke('overlay-hide'),
  getOverlayHotkey: () => ipcRenderer.invoke('get-overlay-hotkey'),
  setOverlayHotkey: (a) => ipcRenderer.invoke('set-overlay-hotkey', a),
  onOverlayShown: (cb) => on('overlay-shown', cb),
  onStatus: (cb) => on('status', cb),
  onEnabled: (cb) => on('enabled', cb)
});
