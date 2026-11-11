/* Licensed under the Apache License, Version 2.0. See the COPYRIGHT and LICENSE files in the project root for details.
   cserver.settings - the settings of this machine as a browser's settings page: one card per config artifact, a row per
   key with its field or switch; a change is saved at once (?native_action=set / unset) with Undo in the message; the
   search box prunes the rows as one types (the words in a key, what it does, its config, who reads it), the chips keep
   the keys set here or not set; the state (q, show) is in the address; A- / A+ and the theme - the one of every page of
   this server, cmeta.theme - are kept in the browser. No dependency. */
(function () {
  'use strict';
  var CFG = window.CONFIG || {};
  var root = document.getElementById('cst');
  if (!root) return;
  var $ = function (id) { return document.getElementById(id); };
  var KEY = 'cserver.settings.', SHARED_THEME = 'cmeta.theme';
  function stored(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function store(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } }
  function h(tag, attrs) {
    var e = document.createElement(tag), a = attrs || {};
    Object.keys(a).forEach(function (k) { if (k === 'class') e.className = a[k]; else e.setAttribute(k, a[k]); });
    for (var i = 2; i < arguments.length; i++) {
      var kid = arguments[i];
      if (kid === null || kid === undefined || kid === false) continue;
      e.appendChild(typeof kid === 'string' ? document.createTextNode(kid) : kid);
    }
    return e;
  }
  var DATA = null, st = {q: (CFG.state && CFG.state.q) || '', show: (CFG.state && CFG.state.show) || ''};
  var toastTimer = null;

  /* ---------------------------------------------------------------- the server */
  function call(action, params) {
    return fetch((CFG.api_url || '?') + 'native_action=' + action, {method: 'POST', headers: {'Content-Type': 'application/json'},
                                                                      body: JSON.stringify(params || {})})
      .then(function (r) {
        return r.text().then(function (text) {
          var d;
          try { d = JSON.parse(text); } catch (e) { throw new Error('HTTP ' + r.status + ': ' + text.slice(0, 300)); }
          if (d && d.error) throw new Error(d.error);
          return d;
        });
      });
  }
  function toast(text, bad) {
    var t = $('cst-toast');
    t.textContent = text;
    t.className = 'cst-toast shown' + (bad ? ' bad' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.className = 'cst-toast'; }, bad ? 6000 : 2600);
  }
  function toastUndo(text, fn) {
    var t = $('cst-toast');
    t.textContent = text + ' ';
    var b = h('button', {type: 'button', class: 'cst-toast-act'}, 'Undo');
    b.addEventListener('click', function () { t.className = 'cst-toast'; clearTimeout(toastTimer); fn(); });
    t.appendChild(b);
    t.className = 'cst-toast shown act';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.className = 'cst-toast'; }, 9000);
  }

  /* ---------------------------------------------------------------- the theme, the size */
  function setDark(dark) {
    root.classList.toggle('dark', !!dark);
    if (!CFG.hosted) document.body.style.backgroundColor = dark ? getComputedStyle(root).getPropertyValue('--cst-bg').trim() : '';
  }
  if (CFG.hosted) {
    root.classList.add('hosted');
    $('cst-theme').hidden = true;
    var follow = function () { var t = document.documentElement.getAttribute('data-ctp-theme'); setDark(t ? t === 'dark' : CFG.dark_mode === true); };
    follow();
    new MutationObserver(follow).observe(document.documentElement, {attributes: true, attributeFilter: ['data-ctp-theme']});
  } else {
    var t0 = stored(SHARED_THEME);
    setDark(t0 ? t0 === 'dark' : CFG.dark_mode === true);
    $('cst-theme').addEventListener('click', function () {
      var dark = !root.classList.contains('dark');
      setDark(dark);
      store(SHARED_THEME, dark ? 'dark' : 'light');
    });
    window.addEventListener('storage', function (e) { if (e.key === SHARED_THEME && e.newValue) setDark(e.newValue === 'dark'); });
  }
  var scale = 1;
  function setScale(s, keep) {
    scale = Math.max(0.7, Math.min(2.2, Math.round(s * 10) / 10));
    $('cst-body').style.zoom = String(scale);
    if (keep) store(KEY + 'scale', String(scale));
  }
  setScale(parseFloat(stored(KEY + 'scale')) || 1, false);
  $('cst-smaller').addEventListener('click', function () { setScale(scale - 0.1, true); });
  $('cst-bigger').addEventListener('click', function () { setScale(scale + 0.1, true); });

  /* ---------------------------------------------------------------- the search */
  function words() { return st.q.toLowerCase().split(/\s+/).filter(Boolean); }
  function hits(g, k, ws) {
    if (!ws.length) return true;
    var hay = [k.key, k.desc, g.name, g.desc, k.readers.join(' '), k.type].join(' ').toLowerCase();
    return ws.every(function (w) { return hay.indexOf(w) >= 0; });
  }
  function keep() {
    var q = new URLSearchParams(location.search);
    ['q', 'show'].forEach(function (k) { if (st[k]) q.set(k, st[k]); else q.delete(k); });
    var s = q.toString();
    try { history.replaceState(null, '', location.pathname + (s ? '?' + s : '') + location.hash); } catch (e) { /* ignore */ }
  }

  /* ---------------------------------------------------------------- the rows */
  function valueText(k) {
    if (!k.set) return '';
    if (Array.isArray(k.value)) return k.value.join(', ');
    if (k.value !== null && typeof k.value === 'object') return JSON.stringify(k.value);
    return String(k.value === null || k.value === undefined ? '' : k.value);
  }
  function isYesNo(k) { return k.type === 'yes/no' || typeof k.value === 'boolean'; }
  function isNumber(k) { return (k.type === 'number' || k.type === 'int' || k.type === 'float') || (k.set && typeof k.value === 'number' && typeof k.value !== 'boolean'); }
  function isMapping(k) { return k.set && k.value !== null && typeof k.value === 'object' && !Array.isArray(k.value); }

  function rowEl(g, k) {
    var tags = [];
    if (k.set) tags.push(h('span', {class: 'cst-tag set', title: 'set on this machine'}, 'set'));
    if (k.secret) tags.push(h('span', {class: 'cst-tag secret', title: 'a secret: never shown'}, 'secret'));
    if (k.unread) tags.push(h('span', {class: 'cst-tag', title: 'no plugged artifact reads it'}, 'unread'));
    var left = h('div', {class: 'cst-left'}, h('div', {class: 'cst-key'}, h('code', {}, k.key)));
    tags.forEach(function (t) { left.firstChild.appendChild(t); });
    if (k.desc) left.appendChild(h('div', {class: 'cst-desc', title: k.desc}, k.desc));
    var hint = [];
    if (k.type) hint.push(k.type);
    if (k.default !== '' && k.default !== null && k.default !== undefined) hint.push('default ' + k.default);
    if (!k.default && k.examples && k.examples.length) hint.push('e.g. ' + k.examples.slice(0, 2).join(', '));
    if (hint.length) left.appendChild(h('div', {class: 'cst-hint'}, hint.join(' · ')));
    if (k.readers.length) left.appendChild(h('div', {class: 'cst-who', title: k.readers.join('\n')}, 'read by ' + k.readers.slice(0, 3).join(', ') + (k.readers.length > 3 ? ' +' + (k.readers.length - 3) : '')));
    var field = h('div', {class: 'cst-field'});
    var row = h('div', {class: 'cst-row' + (k.set ? '' : ' unset-key'), 'data-config': g.name, 'data-key': k.key}, left, field);
    var canEdit = !!(CFG.edit && DATA && DATA.values);

    if (isMapping(k)) {
      field.appendChild(h('span', {class: 'cst-ro'}, 'a mapping: change its keys one by one (', h('code', {}, k.key + '.<sub>'), ') or with cx config set'));
      return row;
    }
    if (isYesNo(k) && !k.secret) {
      var seg = h('span', {class: 'cst-seg', role: 'radiogroup'});
      var cur = k.set ? (String(k.value).toLowerCase() === 'yes' || String(k.value).toLowerCase() === 'true' || k.value === true || String(k.value) === '1' ? 'yes' : 'no') : '';
      ['yes', 'no'].forEach(function (v) {
        var b = h('button', {type: 'button', 'data-v': v, class: cur === v ? 'on' : '', role: 'radio', 'aria-checked': cur === v ? 'true' : 'false'}, v);
        if (!canEdit) b.disabled = true;
        b.addEventListener('click', function () { if (cur !== v) save(g, k, v, row); });
        seg.appendChild(b);
      });
      field.appendChild(seg);
      if (canEdit && k.set) field.appendChild(resetBtn(g, k, row));
      return row;
    }
    var input = h('input', {type: k.secret ? 'password' : (isNumber(k) ? 'number' : 'text'), value: k.secret ? '' : valueText(k),
                            placeholder: k.secret ? (k.set ? 'set here (hidden) - type to change' : 'not set') : (k.set ? '' : (k.default ? 'default: ' + k.default : 'not set')),
                            'aria-label': k.key, autocomplete: 'off', spellcheck: 'false'});
    if (isNumber(k)) input.setAttribute('step', 'any');
    if (!canEdit) input.disabled = true;
    var saveB = h('button', {type: 'button', class: 'cst-save', hidden: ''}, 'Save');
    function dirty() { return k.secret ? input.value !== '' : input.value !== valueText(k); }
    input.addEventListener('input', function () { saveB.hidden = !dirty(); input.classList.toggle('dirty', dirty()); });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && dirty()) { e.preventDefault(); save(g, k, input.value, row); }
      else if (e.key === 'Escape') { input.value = k.secret ? '' : valueText(k); saveB.hidden = true; input.classList.remove('dirty'); }
    });
    saveB.addEventListener('click', function () { save(g, k, input.value, row); });
    field.appendChild(input);
    field.appendChild(saveB);
    if (canEdit && k.set) field.appendChild(resetBtn(g, k, row));
    return row;
  }
  function resetBtn(g, k, row) {
    var b = h('button', {type: 'button', class: 'cst-reset', title: 'Take the key out (cx config unset)'}, 'Reset');
    b.addEventListener('click', function () { unset(g, k, row); });
    return b;
  }

  /* ---------------------------------------------------------------- a change, Undo */
  function describe(k, v) {
    if (k.secret) return '(hidden)';
    return Array.isArray(v) ? v.join(', ') : (v === null || v === undefined ? '' : String(v));
  }
  function apply(res) {
    // the entry as the server left it, the row drawn again
    DATA.groups.forEach(function (g) {
      if (g.name !== res.config) return;
      g.keys.forEach(function (k) {
        if (k.key !== res.key) return;
        k.set = !!res.set;
        k.value = k.secret ? null : (res.set ? res.value : null);
      });
      g.set_count = g.keys.filter(function (k) { return k.set; }).length;
    });
    render(res.config + '\u0001' + res.key);
  }
  function save(g, k, value, row) {
    var inputs = row.querySelectorAll('input, button');
    inputs.forEach(function (x) { x.disabled = true; });
    call('set', {config: g.name, key: k.key, value: value})
      .then(function (res) {
        if (!res.changed) { toast(k.key + ': unchanged'); render(); return; }
        var wasSet = res.was_set, old = res.old;
        apply(res);
        toastUndo(g.name + ' ' + k.key + ' = ' + describe(k, res.value) + (wasSet ? ' (was ' + describe(k, old) + ')' : ' (was not set)'), function () {
          (wasSet ? call('set', {config: g.name, key: k.key, value: Array.isArray(old) ? old.join(',') : String(old)})
                  : call('unset', {config: g.name, key: k.key}))
            .then(function (r2) { apply(r2); toast(k.key + ': put back'); })
            .catch(function (e) { toast('Not put back: ' + e.message, true); });
        });
      })
      .catch(function (e) { toast('Not saved: ' + e.message, true); render(); });
  }
  function unset(g, k, row) {
    row.querySelectorAll('input, button').forEach(function (x) { x.disabled = true; });
    call('unset', {config: g.name, key: k.key})
      .then(function (res) {
        var old = res.old;
        apply(res);
        toastUndo(g.name + ' ' + k.key + ': taken out' + (k.secret ? '' : ' (was ' + describe(k, old) + ')'), function () {
          if (k.secret) { toast('A secret is not put back: set it again', true); return; }
          call('set', {config: g.name, key: k.key, value: Array.isArray(old) ? old.join(',') : String(old)})
            .then(function (r2) { apply(r2); toast(k.key + ': put back'); })
            .catch(function (e) { toast('Not put back: ' + e.message, true); });
        });
      })
      .catch(function (e) { toast('Not taken out: ' + e.message, true); render(); });
  }

  /* ---------------------------------------------------------------- drawing */
  function render(flashKey) {
    if (!DATA) return;
    var ws = words(), box = $('cst-groups'), shown = 0, total = 0, setN = 0;
    box.innerHTML = '';
    DATA.groups.forEach(function (g) {
      var keys = g.keys.filter(function (k) {
        total++;
        if (k.set) setN++;
        if (st.show === 'set' && !k.set) return false;
        if (st.show === 'unset' && k.set) return false;
        return hits(g, k, ws);
      });
      if (!keys.length) return;
      shown += keys.length;
      var card = h('section', {class: 'cst-group', 'data-config': g.name});
      card.appendChild(h('div', {class: 'cst-ghead'}, h('h2', {}, h('code', {}, g.name)), h('span', {class: 'cst-gdesc'}, g.desc || ''),
                         h('span', {class: 'cst-gn'}, g.set_count + ' of ' + g.keys.length + ' set' + (g.here ? '' : ' - not on this machine yet'))));
      if (g.readers.length) {
        var rd = h('div', {class: 'cst-readers'});
        g.readers.slice(0, 12).forEach(function (r) { rd.appendChild(h('span', {class: 'cst-reader', title: 'reads this config'}, r)); });
        if (g.readers.length > 12) rd.appendChild(h('span', {class: 'cst-reader'}, '+' + (g.readers.length - 12)));
        card.appendChild(rd);
      }
      keys.forEach(function (k) {
        var row = rowEl(g, k);
        if (flashKey === g.name + '\u0001' + k.key) row.classList.add('flash');
        card.appendChild(row);
      });
      box.appendChild(card);
    });
    $('cst-empty').hidden = shown > 0;
    $('cst-count').textContent = (shown !== total ? shown + ' of ' : '') + total + ' keys · ' + setN + ' set';
    keep();
  }

  function load() {
    $('cst-error').hidden = true;
    return call('settings', {})
      .then(function (d) {
        DATA = d;
        var note = $('cst-note');
        if (!d.values) {
          note.textContent = 'The values set on this machine are shown to a browser on the server\'s own machine, or one past its password (configs_values of the cserver config says otherwise); the keys and what they do are listed.';
          note.hidden = false;
        } else if (!d.edit) {
          note.textContent = 'Read only here: a setting is changed from a browser on the server\'s own machine, or one that signed in with its password.';
          note.hidden = false;
        } else note.hidden = true;
        render();
      })
      .catch(function (e) { $('cst-error').textContent = 'Could not read the settings: ' + e.message; $('cst-error').hidden = false; });
  }

  /* ---------------------------------------------------------------- wire */
  if (CFG.configs_url) { $('cst-configs').href = CFG.configs_url; $('cst-configs').hidden = false; }
  $('cst-q').value = st.q;
  $('cst-q').addEventListener('input', function () { st.q = this.value.trim(); render(); });
  $('cst-q').addEventListener('keydown', function (e) { if (e.key === 'Escape') { this.value = ''; st.q = ''; render(); } });
  $('cst-show').addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (!b) return;
    st.show = b.getAttribute('data-show') || '';
    $('cst-show').querySelectorAll('button').forEach(function (x) { x.classList.toggle('on', x === b); });
    render();
  });
  if (st.show) $('cst-show').querySelectorAll('button').forEach(function (x) { x.classList.toggle('on', (x.getAttribute('data-show') || '') === st.show); });
  $('cst-reload').addEventListener('click', load);
  document.addEventListener('keydown', function (e) {
    var tag = (e.target && e.target.tagName) || '';
    if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(tag) && !e.target.isContentEditable) { e.preventDefault(); $('cst-q').focus(); }
  });
  load();
})();
