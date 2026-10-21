const T = {
  ru: {
    nav_all:'Все скрипты', nav_menu:'Меню скриптов', nav_upload:'Загрузить свой', nav_settings:'Настройки', refresh:'Обновить', search:'Поиск…', back:'← Назад',
    up_title:'Загрузить скрипт', up_sub:'Доступно только владельцу библиотеки. Скрипт сразу появится у всех пользователей.',
    f_title:'Название', f_desc:'Описание', f_instr:'Инструкция (поддерживается **жирный**, `код`, списки)', f_photos:'Фото', f_files:'Файлы (zip и другие)',
    f_entry:'Файл запуска для меню (.py, необязательно)', f_settings:'Настройки для меню (JSON, необязательно)',
    drop_img:'Перетащи картинки сюда или', drop_files:'Перетащи файлы сюда или', choose:'выбери', submit:'Опубликовать',
    lang:'Язык интерфейса', tok_help:'GitHub-токен нужен только владельцу библиотеки для загрузки скриптов. Обычным пользователям он не нужен. Токен хранится в зашифрованном виде.',
    tok_label:'GitHub-токен (только для владельца)', save:'Сохранить', make_token:'Создать токен на GitHub',
    ov_label:'Клавиша оверлея', ov_help:'Открывает и закрывает окно со скриптами поверх игры. Нажми поле и нужное сочетание.', ov_open:'Открыть оверлей', hk_press:'Нажми клавишу…', hk_clear:'Убрать', hk_bad:'Эта клавиша недоступна',
    none:'Ничего не найдено.', files:'файлов', author:'Автор', dl_title:'Файлы', dl:'Скачать', dl_all:'Скачать всё', no_files:'Нет файлов',
    install:'Скачать и добавить в меню', update:'Обновить в меню', remove:'Убрать из меню', in_menu:'В меню', has_update:'Есть обновление', open_menu:'Открыть меню',
    installing:'Устанавливаю…', done_installed:'Добавлено в меню ✔', manual:'Или скачать файлы вручную',
    instr:'Инструкция', no_instr:'Автор не добавил инструкцию.', risk:'Скрипты запускаются на твоём компьютере. Используй только тем, кому доверяешь.',
    downloading:'Скачиваю…', saved_to:'Сохранено в: ', err:'Ошибка: ', not_cfg:'Приложение ещё не привязано к репозиторию: впиши свой GitHub-ник в config.json и пересобери.',
    sending:'Публикую, это может занять минуту…', sent:'Опубликовано ✔', open_pr:'Открыть на GitHub', tok_saved:'Токен сохранён', tok_removed:'Токен удалён',
    repo:'Репозиторий библиотеки: ', has_token:' · токен сохранён', owner_ok:' · вход как владелец',
    menu_title:'Меню скриптов', menu_sub:'Включай и выключай скрипты тумблером, шестерёнка открывает настройки. То же самое доступно в оверлее поверх игры.',
    menu_empty:'Здесь пока пусто. Открой «Все скрипты», выбери скрипт и нажми «Скачать и добавить в меню».',
    st_stopped:'Выключен', st_starting:'Запуск…', st_installing:'Установка библиотек…', st_running:'Работает', st_error:'Ошибка', st_nopython:'Нужен Python',
    gear:'Настройки', reset:'Сбросить настройки', hk_toggle:'Клавиша вкл/выкл скрипта', log:'Журнал', group_color:'Цвет мяча', group_minimap:'Миникарта',
    no_python:'Python не найден. Установи Python 3.10+ и поставь галочку «Add python.exe to PATH».', get_python:'Скачать Python',
    ov_title:'Rematch Scripts', ov_hint:'Esc или клавиша оверлея — закрыть', confirm_remove:'Убрать скрипт из меню и удалить его файлы?'
  },
  en: {
    nav_all:'All scripts', nav_menu:'Script menu', nav_upload:'Upload', nav_settings:'Settings', refresh:'Refresh', search:'Search…', back:'← Back',
    up_title:'Upload a script', up_sub:'Available to the library owner only. The script goes live for all users immediately.',
    f_title:'Title', f_desc:'Description', f_instr:'Instructions (supports **bold**, `code`, lists)', f_photos:'Photos', f_files:'Files (zip and others)',
    f_entry:'Entry file for the menu (.py, optional)', f_settings:'Menu settings (JSON, optional)',
    drop_img:'Drop images here or', drop_files:'Drop files here or', choose:'browse', submit:'Publish',
    lang:'Interface language', tok_help:'A GitHub token is only needed by the library owner to upload scripts. Regular users do not need it. It is stored encrypted.',
    tok_label:'GitHub token (owner only)', save:'Save', make_token:'Create token on GitHub',
    ov_label:'Overlay hotkey', ov_help:'Opens and closes the scripts window on top of the game. Click the field and press the combination.', ov_open:'Open overlay', hk_press:'Press a key…', hk_clear:'Clear', hk_bad:'This key is unavailable',
    none:'Nothing found.', files:'files', author:'Author', dl_title:'Files', dl:'Download', dl_all:'Download all', no_files:'No files',
    install:'Download & add to menu', update:'Update in menu', remove:'Remove from menu', in_menu:'In menu', has_update:'Update available', open_menu:'Open menu',
    installing:'Installing…', done_installed:'Added to menu ✔', manual:'Or download the files manually',
    instr:'Instructions', no_instr:'The author did not add instructions.', risk:'Scripts run on your computer. Only use ones from people you trust.',
    downloading:'Downloading…', saved_to:'Saved to: ', err:'Error: ', not_cfg:'The app is not linked to a repository yet: put your GitHub username in config.json and rebuild.',
    sending:'Publishing, this may take a minute…', sent:'Published ✔', open_pr:'Open on GitHub', tok_saved:'Token saved', tok_removed:'Token removed',
    repo:'Library repository: ', has_token:' · token saved', owner_ok:' · signed in as owner',
    menu_title:'Script menu', menu_sub:'Switch scripts on and off with the toggle; the gear opens settings. The same menu is available in the in-game overlay.',
    menu_empty:'Nothing here yet. Open "All scripts", pick one and press "Download & add to menu".',
    st_stopped:'Off', st_starting:'Starting…', st_installing:'Installing libraries…', st_running:'Running', st_error:'Error', st_nopython:'Python required',
    gear:'Settings', reset:'Reset settings', hk_toggle:'Hotkey to switch the script on/off', log:'Log', group_color:'Ball colour', group_minimap:'Minimap',
    no_python:'Python was not found. Install Python 3.10+ and tick "Add python.exe to PATH".', get_python:'Get Python',
    ov_title:'Rematch Scripts', ov_hint:'Esc or the overlay hotkey closes this', confirm_remove:'Remove the script from the menu and delete its files?'
  }
};
let lang = 'ru';
try { lang = localStorage.getItem('lang') || ((navigator.language || '').startsWith('ru') ? 'ru' : 'en'); } catch {}
const t = (k) => (T[lang] && T[lang][k]) ?? k;
function applyLang() {
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-i]').forEach(e => e.textContent = t(e.dataset.i));
  document.querySelectorAll('[data-ip]').forEach(e => e.placeholder = t(e.dataset.ip));
}
function setLang(l) { lang = l; try { localStorage.setItem('lang', l); } catch {} applyLang(); }
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
