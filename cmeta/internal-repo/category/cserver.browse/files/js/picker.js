/* Licensed under the Apache License, Version 2.0. See the COPYRIGHT and LICENSE files in the project root for details.
   cmetaPicker (2026-11-10) - the picker of artifacts the lists of an artifact use, one source for the knowledge browser
   (its detail panel) and the artifact page (cserver.cref inlines this file, as it inlines hl.js): a form with a box;
   what is typed is searched as one types (cserver.browse's search: the most recent artifacts first - the date in
   front of a name, else the last change; the AI contexts first for the AI uses), offered under the box; Enter or ";"
   takes the one lit (the arrows move it) as a chip, a cRef pasted whole is a chip at once, Backspace on an empty box
   takes the last chip out, Esc closes the list; the form's submit hands the chips (and what is still typed) to
   opts.submit. No dependency; its styles are added to the page once, on the colours --cmp-accent / --cmp-line /
   --cmp-bg the page sets on its root (plain defaults otherwise).

     cmetaPicker(form, {api: function(action, params) -> Promise (the actions of cserver.browse: search, templates),
                        self: <the UID of the artifact whose list it is: never offered>, key: 'connections' | 'ai_uses',
                        submit: function(values: [cRef or alias]) -> Promise})
   The form holds: an <input type=text>, a <span class="cmp-chips"> before it (made when missing), a
   <div class="cmp-list" hidden> after it (made when missing), a submit button. */
(function () {
  'use strict';
  if (window.cmetaPicker) { return; }
  var CSS = '.cmp-chips{display:contents}' +
    '.cmp-chip{display:inline-flex;align-items:center;gap:2px;max-width:100%;padding:1px 4px 1px 8px;border-radius:999px;background:var(--cmp-soft,rgba(42,120,214,.12));color:var(--cmp-accent,#2a78d6);font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}' +
    '.cmp-x{border:0;background:none;color:inherit;font:inherit;font-size:14px;line-height:1;padding:0 3px;cursor:pointer;border-radius:50%}.cmp-x:hover{background:var(--cmp-accent,#2a78d6);color:#fff}' +
    '.cmp-list{position:absolute;z-index:5;left:0;right:0;top:100%;max-height:240px;overflow:auto;margin-top:3px;padding:4px;border:1px solid var(--cmp-line,#e3e6ec);border-radius:8px;background:var(--cmp-bg,#fff);box-shadow:0 8px 28px rgba(0,0,0,.18)}' +
    '.cmp-opt{display:flex;flex-wrap:wrap;gap:2px 10px;align-items:baseline;padding:5px 8px;border-radius:6px;cursor:pointer;font-size:13px}.cmp-opt b{font-weight:500}.cmp-opt .cmp-sub{color:var(--cmp-muted,#6b7180);font-size:11.5px}' +
    '.cmp-opt:hover,.cmp-opt.lit{background:rgba(127,127,127,.12)}.cmp-opt.lit{box-shadow:inset 2px 0 0 var(--cmp-accent,#2a78d6)}';
  var styled = false;
  function h(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function dateOf(a) { var m = /^(\d{4})(\d\d|xx)?(\d\d|xx)?\./i.exec(a || ''); return m ? (m[1] + (m[2] || '') + (m[3] || '')).replace(/x/gi, '0') : ''; }
  function recent(a, b) {
    var da = dateOf(a.alias), db = dateOf(b.alias);
    if (da && db) { if (da !== db) return da < db ? 1 : -1; } else if (da || db) return da ? -1 : 1;
    var ua = a.updated || a.created || '', ub = b.updated || b.created || '';
    return ua < ub ? 1 : ua > ub ? -1 : 0;
  }
  var templates = null;
  function suggest(api, key, selfUid, text) {
    var q = text.trim(), low = q.toLowerCase(), opts = [];
    var tp = key !== 'ai_uses' ? Promise.resolve([]) : templates ? Promise.resolve(templates)
           : api('templates', {}).then(function (j) { templates = j.templates || []; return templates; }, function () { templates = []; return templates; });
    return tp.then(function (ts) {
      ts.forEach(function (t) {
        if (!low || (t.alias + ' ' + t.title + ' ' + t.name).toLowerCase().indexOf(low) >= 0) opts.push({value: t.alias, title: t.title || t.name, sub: 'AI context - ' + t.cat + '::' + t.name});
      });
      if (q.length < 2) return opts;
      return api('search', {q: q, limit: 40, facets: '0'}).then(function (j) {
        var rows = (j.rows || []).filter(function (r) { return r.uid !== selfUid; });
        rows.sort(recent);
        rows.slice(0, 10).forEach(function (r) {
          opts.push({value: r.cat + '::' + r.alias + ',' + r.uid, title: r.alias, sub: (r.name && r.name !== r.alias ? r.name + ' - ' : '') + r.cat + (r.repo ? ' - ' + r.repo : '')});
        });
        return opts;
      }, function () { return opts; });
    });
  }
  function picker(form, opts) {
    if (!styled) { var st = document.createElement('style'); st.textContent = CSS; document.head.appendChild(st); styled = true; }
    var inp = form.querySelector('input[type=text]'), btn = form.querySelector('button[type=submit]');
    var chips = form.querySelector('.cmp-chips'), list = form.querySelector('.cmp-list');
    if (!chips) { chips = h('span', 'cmp-chips'); form.insertBefore(chips, inp); }
    if (!list) { list = h('div', 'cmp-list'); list.hidden = true; list.setAttribute('role', 'listbox'); form.appendChild(list); }
    if (getComputedStyle(form).position === 'static') form.style.position = 'relative';
    var seq = 0, timer = null, picked = [], found = [], lit = -1;
    function paint() {
      chips.innerHTML = '';
      picked.forEach(function (p) {
        var c = h('span', 'cmp-chip', p.title); c.title = p.value;
        var x = h('button', 'cmp-x', '×'); x.type = 'button'; x.title = 'Take it out';
        x.addEventListener('click', function () { picked = picked.filter(function (y) { return y.value !== p.value; }); paint(); });
        c.appendChild(x); chips.appendChild(c);
      });
    }
    function close() { list.hidden = true; list.innerHTML = ''; found = []; lit = -1; }
    function show() {
      list.innerHTML = '';
      if (!found.length) { close(); return; }
      found.forEach(function (o, i) {
        var d = h('div', 'cmp-opt' + (i === lit ? ' lit' : '')); d.setAttribute('role', 'option'); d.title = o.value;
        d.appendChild(h('b', null, o.title)); d.appendChild(h('span', 'cmp-sub', o.sub));
        d.addEventListener('mousedown', function (e) { e.preventDefault(); take(i); });
        list.appendChild(d);
      });
      list.hidden = false;
    }
    function take(i) {
      var o = found[i];
      if (!o) return;
      if (!picked.some(function (p) { return p.value === o.value; })) picked.push(o);
      paint(); inp.value = ''; close(); inp.focus();
    }
    function ask() {
      var q = inp.value.trim();
      if (!q) { close(); return; }
      var my = ++seq;
      suggest(opts.api, opts.key, opts.self, q).then(function (o) {
        if (my !== seq || inp.value.trim() !== q) return;
        found = o.filter(function (x) { return !picked.some(function (p) { return p.value === x.value; }); });
        lit = found.length ? 0 : -1;
        show();
      });
    }
    inp.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(ask, 220); });
    inp.addEventListener('keydown', function (e) {
      var q = inp.value.trim();
      if (e.key === ';' || (e.key === 'Enter' && ((lit >= 0 && !list.hidden) || q.indexOf('::') > 0))) {
        e.preventDefault();
        if (lit >= 0 && !list.hidden) take(lit);
        else if (q.indexOf('::') > 0) { picked.push({value: q, title: q.replace(/,[0-9a-f]{16}(?=::|$)/gi, '')}); paint(); inp.value = ''; close(); }
        else if (q) ask();
      } else if (e.key === 'ArrowDown' && found.length) { e.preventDefault(); lit = (lit + 1) % found.length; show(); }
      else if (e.key === 'ArrowUp' && found.length) { e.preventDefault(); lit = (lit - 1 + found.length) % found.length; show(); }
      else if (e.key === 'Escape' && !list.hidden) { e.preventDefault(); e.stopPropagation(); close(); }
      else if (e.key === 'Backspace' && !inp.value && picked.length) { picked.pop(); paint(); }
    });
    inp.addEventListener('blur', function () { setTimeout(close, 150); });
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var v = inp.value.trim(), all = picked.map(function (p) { return p.value; });
      if (v) all.push(v);
      if (!all.length) { inp.focus(); return; }
      if (btn) btn.disabled = true;
      Promise.resolve(opts.submit(all)).then(function (keep) {
        if (btn) btn.disabled = false;
        if (keep !== true) { picked = []; paint(); inp.value = ''; close(); }
      }, function () { if (btn) btn.disabled = false; });
    });
    return {picked: function () { return picked.map(function (p) { return p.value; }); },
            reset: function () { picked = []; paint(); inp.value = ''; close(); }};
  }
  window.cmetaPicker = picker;
  window.cmetaPicker.recent = recent;
})();
