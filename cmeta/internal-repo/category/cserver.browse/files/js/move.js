/* cserver.browse - "Move to": an artifact into another repository of this server (2026-11-11, the user: "add 'move to'
   button to move it to another repo ... and when I click on cref too ... in a user-friendly way"). One dialog for the
   lists and the detail panel of /browse and for the artifact page (cserver.cref inlines this file): the repositories
   this viewer may write to (asked from the server: move_targets), the last one used first; the server renames the
   folder in one step on the same disk (a folder in use: nothing changes) and reindexes it; a note at the bottom of
   the window says where it went and offers Undo (the same move back).

     cmetaMove({api: function (action, params) -> Promise of the answer, uid, dark, done: function (answer, undone)})

   Rename and Delete (2026-11-15) are its two other dialogs - cmetaRename, cmetaDelete, below.

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
    '.cmv-toast.cmv-bad{background:#7a1f1f}' +
    // Rename and Delete (2026-11-15): the new cRef under the name; Delete a red dialog, its switch "Yes, I am sure"
    // arms the red button
    '.cmv-ref{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;overflow-wrap:anywhere;color:var(--fg)}' +
    '.cmv-box.cmv-red{border-color:#e5484d;border-top:5px solid #e5484d}.cmv-red h3{color:#d93036}.cmv-dark.cmv-red h3{color:#ff6369}' +
    '.cmv-what{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;overflow-wrap:anywhere}' +
    '.cmv-sure{display:flex;align-items:center;gap:10px;padding:9px 11px;margin:6px 0 2px;border:1px solid rgba(229,72,77,.45);' +
      'border-radius:9px;background:rgba(229,72,77,.07);cursor:pointer;font-weight:600;position:relative}' +
    '.cmv-sure input{position:absolute;opacity:0;width:1px;height:1px}' +
    '.cmv-switch{position:relative;flex:none;width:38px;height:22px;border-radius:999px;background:var(--line);transition:background .15s}' +
    '.cmv-switch::after{content:"";position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:#fff;' +
      'box-shadow:0 1px 3px rgba(0,0,0,.3);transition:left .15s}' +
    '.cmv-sure input:checked+.cmv-switch{background:#e5484d}.cmv-sure input:checked+.cmv-switch::after{left:19px}' +
    '.cmv-sure input:focus-visible+.cmv-switch{box-shadow:0 0 0 3px rgba(229,72,77,.35)}' +
    '.cmv-btn.cmv-del{background:#c9c9cf;border-color:#c9c9cf;color:#fff}.cmv-dark .cmv-btn.cmv-del{background:#4a4f5a;border-color:#4a4f5a}' +
    '.cmv-btn.cmv-del.cmv-armed{background:#d93036;border-color:#d93036}';

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

  // a dialog over the page: its box, closed by Esc, Cancel or a click beside it -> {back, box, close, acts, err}
  function dialog(o, red, keys) {
    style();
    var back = el('div', 'cmv-back');
    var box = el('div', 'cmv-box' + (red ? ' cmv-red' : '') + (o.dark ? ' cmv-dark' : ''));
    box.setAttribute('role', red ? 'alertdialog' : 'dialog');
    box.setAttribute('aria-modal', 'true');
    var err = el('div', 'cmv-err');
    err.hidden = true;
    var acts = el('div', 'cmv-acts');
    back.appendChild(box);
    function close() { back.remove(); document.removeEventListener('keydown', onKey, true); }
    function onKey(e) {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); return; }
      if (keys) { keys(e); }
    }
    document.addEventListener('keydown', onKey, true);
    back.addEventListener('mousedown', function (e) { if (e.target === back) { close(); } });
    return { back: back, box: box, close: close, acts: acts, err: err };
  }

  /* Rename (2026-11-15, the user: "when I go to cRef for event, I also don't see delete or rename - can we add it there
     too for all (if allowed)?"): a new name for the artifact - its folder renamed where it is, the same UID, files and
     repository; the new cRef shows as one types; Enter or Rename renames, Esc closes. The page decides what follows
     (the artifact page opens at the new cRef, with Undo: the name it had).

       cmetaRename({api, uid, cat, alias, dark, done: function (answer)}) */
  window.cmetaRename = function (o) {
    var d = dialog(o, false, function (e) { if (e.key === 'Enter' && !go.disabled) { e.preventDefault(); rename(); } });
    var title = el('h3', '', 'Rename ' + o.cat + '::' + o.alias);
    var input = el('input', 'cmv-filter cmv-name');
    input.type = 'text';
    input.value = o.alias;
    input.spellcheck = false;
    input.setAttribute('aria-label', 'The new name');
    var ref = el('p', 'cmv-ref');
    var hint = el('p', 'cmv-note', 'Its folder is renamed in one step - the same UID, files and repository: a cRef that ' +
      'carries the UID keeps working, one by the name alone needs the new name. A folder in use - a shell, Far or an AI ' +
      'session in it - cannot be renamed: then nothing changes.');
    var go = el('button', 'cmv-btn cmv-go', 'Rename');
    go.type = 'button';
    var cancel = el('button', 'cmv-btn', 'Cancel');
    cancel.type = 'button';
    d.acts.appendChild(cancel);
    d.acts.appendChild(go);
    [title, input, ref, d.err, hint, d.acts].forEach(function (x) { d.box.appendChild(x); });
    document.body.appendChild(d.back);
    function show() {
      var v = input.value.trim();
      ref.textContent = 'its new cRef: ' + o.cat + '::' + (v || '…') + ',' + o.uid;
      go.disabled = !v || v === o.alias;
    }
    function rename() {
      var v = input.value.trim();
      if (!v || v === o.alias) { return; }
      go.disabled = true;
      input.disabled = true;
      d.err.hidden = true;
      go.textContent = 'Renaming ...';
      o.api('rename', { uid: o.uid, alias: v }).then(function (out) {
        if (!out || out.error) { throw new Error((out && out.error) || 'no answer'); }
        d.close();
        if (o.done) { o.done(out); }
      }).catch(function (e) {
        d.err.textContent = (e && e.message) || String(e);
        d.err.hidden = false;
        input.disabled = false;
        go.textContent = 'Rename';
        show();
        input.focus();
      });
    }
    input.addEventListener('input', show);
    cancel.addEventListener('click', d.close);
    go.addEventListener('click', rename);
    show();
    input.focus();
    // the name after its date selected (20261120.Dinner: Dinner), else all of it
    var m = /^\d{4}(?:[0-9a-z]{2}){0,2}[._ -]+/i.exec(o.alias);
    input.setSelectionRange(m && m[0].length < o.alias.length ? m[0].length : 0, o.alias.length);
  };

  /* Delete (2026-11-15): a red dialog - Delete with "Yes, I am sure" switched on deletes the artifact (the server puts
     its folder into the trash of this machine and takes it out of the index); with the switch off Delete only closes
     the dialog, as Cancel, Esc and a click beside it do. The page decides what follows (Undo: undelete_artifact with
     the trash slot of the answer).

       cmetaDelete({api, uid, name, repo, dark, done: function (answer)}) */
  window.cmetaDelete = function (o) {
    var d = dialog(o, true);
    var title = el('h3', '', 'Delete ' + o.name + '?');
    var what = el('p', 'cmv-what', o.name + (o.repo ? ' in ' + o.repo : ''));
    var how = el('p', '', 'Its folder leaves its repository for the trash of this machine (tmp::local:cserver-browse-trash) ' +
      'and it leaves the index; the next sync deletes it on the other machines. Undo in the message puts it back; the ' +
      'trash keeps it after that.');
    var sure = el('input');
    sure.type = 'checkbox';
    sure.name = 'sure';
    var label = el('label', 'cmv-sure');
    label.appendChild(sure);
    var sw = el('span', 'cmv-switch');
    sw.setAttribute('aria-hidden', 'true');
    label.appendChild(sw);
    label.appendChild(el('span', '', 'Yes, I am sure - delete it'));
    var go = el('button', 'cmv-btn cmv-del', 'Delete');
    go.type = 'button';
    var cancel = el('button', 'cmv-btn', 'Cancel');
    cancel.type = 'button';
    d.acts.appendChild(cancel);
    d.acts.appendChild(go);
    [title, what, how, label, d.err, d.acts].forEach(function (x) { d.box.appendChild(x); });
    document.body.appendChild(d.back);
    sure.addEventListener('change', function () { go.classList.toggle('cmv-armed', sure.checked); });
    go.addEventListener('click', function () {
      if (!sure.checked) { d.close(); return; }                 // not sure: back, nothing deleted
      go.disabled = true;
      d.err.hidden = true;
      go.textContent = 'Deleting ...';
      o.api('delete_artifact', { uid: o.uid }).then(function (out) {
        if (!out || out.error) { throw new Error((out && out.error) || 'no answer'); }
        d.close();
        if (o.done) { o.done(out); }
      }).catch(function (e) {
        d.err.textContent = (e && e.message) || String(e);
        d.err.hidden = false;
        go.disabled = false;
        go.textContent = 'Delete';
      });
    });
    cancel.addEventListener('click', d.close);
    sure.focus();
  };
})();
