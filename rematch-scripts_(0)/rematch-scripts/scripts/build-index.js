// Собирает library/index.json из library/*/script.json. Запускается GitHub Action после изменений в library/.
const fs = require('fs');
const path = require('path');
const lib = path.join(__dirname, '..', 'library');
const list = (d) => fs.existsSync(d) ? fs.readdirSync(d).filter(f => fs.statSync(path.join(d, f)).isFile()) : [];
const out = [];
for (const id of fs.readdirSync(lib)) {
  const dir = path.join(lib, id);
  const meta = path.join(dir, 'script.json');
  if (!fs.statSync(dir).isDirectory() || !fs.existsSync(meta)) continue;
  try {
    const m = JSON.parse(fs.readFileSync(meta, 'utf8'));
    out.push({
      id,
      title: String(m.title || id).slice(0, 100),
      author: String(m.author || 'unknown').slice(0, 50),
      description: String(m.description || '').slice(0, 2000),
      instructions: String(m.instructions || '').slice(0, 10000),
      version: Number(m.version) || 1,
      entry: typeof m.entry === 'string' ? m.entry : '',
      settings: Array.isArray(m.settings) ? m.settings : [],
      images: list(path.join(dir, 'images')),
      files: list(path.join(dir, 'files')).map(n => ({ name: n, size: fs.statSync(path.join(dir, 'files', n)).size })),
      updated: Number(m.version) || fs.statSync(meta).mtimeMs
    });
  } catch (e) { console.error('skip', id, e.message); }
}
out.sort((a, b) => b.updated - a.updated);
fs.writeFileSync(path.join(lib, 'index.json'), JSON.stringify(out, null, 1));
console.log('index.json:', out.length, 'scripts');
