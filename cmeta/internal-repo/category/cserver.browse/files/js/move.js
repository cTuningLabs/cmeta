/* cserver.browse - "Move to": an artifact into another repository of this server (2026-11-11, the user: "add 'move to'
   button to move it to another repo ... and when I click on cref too ... in a user-friendly way"). One dialog for the
   lists and the detail panel of /browse and for the artifact page (cserver.cref inlines this file): the repositories
   this viewer may write to (asked from the server: move_targets), the last one used first; the server renames the
   folder in one step on the same disk (a folder in use: nothing changes) and reindexes it; a note at the bottom of
   the window says where it went and offers Undo (the same move back).

     cmetaMove({api: function (action, params) -> Promise of the answer, uid, dark, done: function (answer, undone)})

   No dependency. Authors: Grigori Fursin. */

(function () {
  'use strict';

  var LAST = 'cmeta-move-last';
  var CSS =
    '.cmv-back{position:fixed;inset:0;background:rgba(15,18,24,.45);z-index:1000;display:flex;align-items:flex-start;justify-content:center;padding-top:12vh}' +
    '.cmv-box{--fg:#14161a;--muted:#6b7280;--line:#d8dce3;--bg:#fff;--soft:#f3f5f8;--accent:#2a78d6;--bad:#c62828;' +
      'background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:10px;box-shadow:0 12px 40px rgba(0,0,0,.25);' +
      'width:min(460px,92vw);padding:16px 18px;font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}' +
    '.cmv-dark .cmv-box,.cmv-box.cmv-dark{--fg:#e8eaee;--muted:#9aa3b2;--line:#343a46;--bg:#1b1f27;--soft:#232834;--accent:#3987e5;--bad:#ef6b6b}' +
    '.cmv-box h3{margin:0 0 4px;font-size:16px;overflow-wrap:anywhere}' +
    '.cmv-box p{margin:4px 0 10px;color:var(--muted)}.cmv-box p b{color:var(--fg)}' +
    '.cmv-filter{width:100%;box-sizing:border-box;font:inherit;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:var(--soft);color:var(--fg);margin-bottom:6px}' +
    '.cmv-list{max-height:260px;overflow:auto;border:1px solid var(--line);border-radius:6px}' +
    '.cmv-item{display:flex;justify-content:space-between;gap:10px;padding:5px 9px;cursor:pointer;border-bottom:1px solid var(--line)}' +
    '.cmv-item:last-child{border-bottom:0}.cmv-item:hover{background:var(--soft)}' +
    '.cmv-item.cmv-on{background:var(--accent);color:#fff}.cmv-item small{color:inherit;opacity:.7}' +
    '.cmv-note{font-size:12px;color:var(--muted);margin:8px 0 0}.cmv-err{color:var(--bad);font-size:13px;margin:8px 0 0;overflow-wrap:anywhere}' +
    '.cmv-acts{display:flex;justify-content:flex-end;gap:8px;margin-top:12px}' +
    '.cmv-btn{font:inherit;padding:5px 14px;border-radius:6px;border:1px solid var(--line);background:var(--soft);color:var(--fg);cursor:pointer}' +
    '.cmv-btn.cmv-go{background:var(--accent);border-color:var(--accent);color:#fff}.cmv-btn:disabled{opacity:.5;cursor:default}' +
    '.cmv-toast{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:1001;background:#1f2430;color:#fff;border-radius:8px;' +
      'padding:9px 14px;font:14px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;box-shadow:0 8px 28px rgba(0,0,0,.3);display:flex;gap:12px;align-items:center;max-width:92vw}' +
    '.cmv-toast button{font:inherit;color:#9cc7ff;background:none;border:1px solid #4a5568;border-radius:6px;padding:2px 10px;cursor:pointer}' +
    '.cmv-toast.cmv-bad{background:#7a1f1f}';

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text !== undefined) { e.textContent = text; }
    return e;
  }

  function style() {
    if (document.getElementById('cmv-style')) { return; }
    var s = el('style');
    s.id = 'cmv-style';
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  var toastTimer = null;
  function note(text, bad, action, label) {
    var t = document.getElementById('cmv-toast');
    if (t) { t.remove(); }
    t = el('div', 'cmv-toast' + (bad ? ' cmv-bad' : ''));
    t.id = 'cmv-toast';
    t.setAttribute('role', 'status');
    t.appendChild(el('span', '', text));
    if (action) {
      var b = el('button', '', label || 'Undo');
      b.type = 'button';
      b.addEventListener('click', function () { t.remove(); action(); });
      t.appendChild(b);
    }
    document.body.appendChild(t);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { if (t.parentNode) { t.remove(); } }, action ? 10000 : (bad ? 8000 : 4000));
  }

  function lastUsed() { try { return localStorage.getItem(LAST) || ''; } catch (e) { return ''; } }

  window.cmetaMove = function (o) {
    style();
    var back = el('div', 'cmv-back');
    var box = el('div', 'cmv-box' + (o.dark ? ' cmv-dark' : ''));
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    var title = el('h3', '', 'Move to another repository');
    var from = el('p', '', 'reading where it may go ...');
    var filter = el('input', 'cmv-filter');
    filter.type = 'search';
    filter.placeholder = 'Filter the repositories';
    var list = el('div', 'cmv-list');
    list.setAttribute('role', 'listbox');
    var err = el('div', 'cmv-err');
    err.hidden = true;
    var hint = el('p', 'cmv-note', 'The folder moves in one step (same name, same UID, same files; cRefs keep working). ' +
      'A folder in use - a shell, Far or an AI session in it - cannot move: then nothing changes.');
    var acts = el('div', 'cmv-acts');
    var go = el('button', 'cmv-btn cmv-go', 'Move');
    go.type = 'button';
    go.disabled = true;
    var cancel = el('button', 'cmv-btn', 'Cancel');
    cancel.type = 'button';
    acts.appendChild(cancel);
    acts.appendChild(go);
    [title, from, filter, list, err, hint, acts].forEach(function (x) { box.appendChild(x); });
    back.appendChild(box);
    document.body.appendChild(back);

    var repos = [], chosen = '', info = {};
    function close() { back.remove(); document.removeEventListener('keydown', keys, true); }
    function draw() {
      var q = filter.value.trim().toLowerCase();
      list.innerHTML = '';
      var shown = repos.filter(function (r) { return !q || r[0].toLowerCase().indexOf(q) >= 0; });
      // a typed filter picks its first match; without one, nothing is picked but the last one used - an Enter right
      // after the dialog opens never moves anything anywhere by chance
      if (shown.every(function (r) { return r[0] !== chosen; })) { chosen = q && shown.length ? shown[0][0] : ''; }
      if (!shown.length) { chosen = ''; list.appendChild(el('div', 'cmv-item', repos.length ? 'No repository matches.' : 'No other repository you may write to.')); }
      shown.forEach(function (r) {
        var item = el('div', 'cmv-item' + (r[0] === chosen ? ' cmv-on' : ''));
        item.setAttribute('role', 'option');
        item.setAttribute('data-repo', r[0]);
        item.appendChild(el('span', '', r[0]));
        item.appendChild(el('small', '', r[1] + ' artifacts'));
        item.addEventListener('click', function () { chosen = r[0]; draw(); });
        item.addEventListener('dblclick', function () { chosen = r[0]; move(); });
        list.appendChild(item);
      });
      go.disabled = !chosen;
      go.textContent = chosen ? 'Move to ' + chosen : 'Move';
      var on = list.querySelector('.cmv-on');
      if (on && on.scrollIntoView) { on.scrollIntoView({ block: 'nearest' }); }
    }
    function move() {
      if (!chosen) { return; }
      go.disabled = true;
      err.hidden = true;
      go.textContent = 'Moving ...';
      var to = chosen;
      o.api('move', { uid: o.uid, repo: to }).then(function (out) {
        if (!out || out.error) { err.textContent = (out && out.error) || 'no answer'; err.hidden = false; draw(); return; }
        try { localStorage.setItem(LAST, to); } catch (e) { /* private mode */ }
        close();
        if (o.done) { o.done(out, false); }
        note('Moved ' + info.name + ' from ' + out.from + ' to ' + out.to + '.', false, function () {
          o.api('move', { uid: o.uid, repo: out.from }).then(function (back2) {
            if (!back2 || back2.error) { note((back2 && back2.error) || 'Undo failed', true); return; }
            if (o.done) { o.done(back2, true); }
            note('Moved back to ' + back2.to + '.');
          }, function (e) { note((e && e.message) || String(e), true); });
        });
      }, function (e) { err.textContent = (e && e.message) || String(e); err.hidden = false; draw(); });
    }
    function keys(e) {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); }
      else if (e.key === 'Enter' && !go.disabled) { e.preventDefault(); move(); }
      else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        var names = Array.prototype.map.call(list.querySelectorAll('[data-repo]'), function (x) { return x.getAttribute('data-repo'); });
        var i = names.indexOf(chosen) + (e.key === 'ArrowDown' ? 1 : -1);
        if (names.length) { chosen = names[Math.max(0, Math.min(names.length - 1, i))]; draw(); }
        e.preventDefault();
      }
    }
    document.addEventListener('keydown', keys, true);
    back.addEventListener('mousedown', function (e) { if (e.target === back) { close(); } });
    cancel.addEventListener('click', close);
    go.addEventListener('click', move);
    filter.addEventListener('input', draw);

    o.api('move_targets', { uid: o.uid }).then(function (out) {
      if (!out || out.error) { from.textContent = ''; err.textContent = (out && out.error) || 'no answer'; err.hidden = false; return; }
      info = out;
      title.textContent = 'Move ' + out.name;
      from.innerHTML = '';
      from.appendChild(document.createTextNode('from '));
      from.appendChild(el('b', '', out.from || '(registry)'));
      from.appendChild(document.createTextNode(' to:'));
      repos = out.repos || [];
      var last = lastUsed();
      chosen = repos.some(function (r) { return r[0] === last; }) ? last : '';
      draw();
      filter.focus();
    }, function (e) { from.textContent = ''; err.textContent = (e && e.message) || String(e); err.hidden = false; });
  };

  window.cmetaMoveNote = note;
})();
