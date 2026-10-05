/* Licensed under the Apache License, Version 2.0. See the COPYRIGHT and LICENSE files in the project root for details.
 *
 * cserver.browse - search, browse and graph the artifacts of every plugged repository.
 *
 * One query drives three views: Search (a list, best matches first), Browse (a sortable table with facets)
 * and Graph (the results joined by their connections). The state lives in the URL, so a view can be shared and
 * a reload reproduces it; the footer shows the same query as a cx command.
 *
 * No third-party libraries: the page works offline, on the engine cserver and on cPlatform alike.
 */
(function () {
  'use strict';
  var CFG = window.CONFIG || {};
  var root = document.getElementById('cbr');
  if (!root) return;
  function $(id) { return document.getElementById(id); }

  var THEME_KEY = 'cserver.browse.theme';
  var VIEWS = ['search', 'browse', 'graph'];
  var GCFG = CFG.graph || {max_nodes: 300, max: 1000, depth_max: 12};

  // The state in the URL: the query, the view, the open artifact, and the graph (focus, depth, nodes, switches:
  // '' = the default, '1' / '0' = set)
  var URL_KEYS = ['q', 'repos', 'cats', 'after', 'before', 'sort', 'dir', 'uid', 'focus', 'depth', 'max_nodes',
                  'categories', 'core', 'isolated', 'neighbors', 'labels', 'links'];
  var st = {view: 'search'};
  URL_KEYS.forEach(function (k) { st[k] = ''; });
  Object.keys(st).forEach(function (k) { if (CFG.state && CFG.state[k]) st[k] = CFG.state[k]; });
  if (VIEWS.indexOf(st.view) < 0) st.view = 'search';
  st.offset = 0;
  st.limit = 50;

  var options = null;      // {repos: [[name, n]], cats: [[name, n]], total, catalog, index}
  var indexState = null;   // the connection index as the last answer reported it: {ready, links, ...}
  var last = null;         // the last search result
  var busyCount = 0;
  var runToken = 0;

  /* ------------------------------------------------------------------ helpers */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  function escRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  function h(tag, attrs) {
    var e = document.createElement(tag);
    var a = attrs || {};
    Object.keys(a).forEach(function (k) {
      if (k === 'class') e.className = a[k];
      else if (k === 'html') e.innerHTML = a[k];
      else e.setAttribute(k, a[k]);
    });
    for (var i = 2; i < arguments.length; i++) {
      var kid = arguments[i];
      if (kid == null || kid === false) continue;
      e.appendChild(typeof kid === 'string' ? document.createTextNode(kid) : kid);
    }
    return e;
  }
  function quoteIf(v) { return /[\s"]/.test(v) ? '"' + v.replace(/"/g, '') + '"' : v; }
  function busy(on, what) {
    busyCount = Math.max(0, busyCount + (on ? 1 : -1));
    var b = $('cbr-busy');
    if (on && what) b.querySelector('.what').textContent = what;
    b.hidden = busyCount === 0;
  }
  function showError(msg) {
    var e = $('cbr-error');
    e.textContent = msg || '';
    e.hidden = !msg;
  }
  function apiUrl(action) {
    var u = CFG.api_url || '?';
    var sep = /[?&]$/.test(u) ? '' : (u.indexOf('?') >= 0 ? '&' : '?');
    return u + sep + 'native_action=' + action;
  }
  // what === null: a quiet call (no spinner) - the progress polls
  function call(action, params, what) {
    var quiet = what === null;
    if (!quiet) busy(true, what || 'loading');
    return fetch(apiUrl(action), {method: 'POST', headers: {'Content-Type': 'application/json'},
                                  body: JSON.stringify(params || {})})
      .then(function (res) {
        return res.text().then(function (text) {
          var data;
          try { data = JSON.parse(text); } catch (e) { throw new Error('HTTP ' + res.status + ': ' + text.slice(0, 300)); }
          if (data && data.error) throw new Error(data.error);
          return data;
        });
      })
      .finally(function () { if (!quiet) busy(false); });
  }
  function on(v, dflt) { return v === '' || v == null ? dflt : v !== '0'; }
  function num(n) { return Number(n || 0).toLocaleString('en-US'); }
  function msText(ms) { return ms >= 1000 ? (ms / 1000).toFixed(1) + ' s' : Math.round(ms) + ' ms'; }
  function fmtSize(n) {
    if (n < 1024) return n + ' B';
    if (n < 1048576) return (n / 1024).toFixed(n < 10240 ? 1 : 0) + ' KB';
    return (n / 1048576).toFixed(1) + ' MB';
  }
  function qs(o) {
    return Object.keys(o).filter(function (k) { return o[k] !== '' && o[k] != null; })
      .map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(o[k]); }).join('&');
  }
  function copy(text, btn) {
    function done() { if (btn) { var t = btn.textContent; btn.textContent = 'copied'; setTimeout(function () { btn.textContent = t; }, 1200); } }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () { fallback(); });
    } else fallback();
    function fallback() {
      var ta = h('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch (e) { /* ignore */ }
      document.body.removeChild(ta);
    }
  }

  /* ------------------------------------------------------------------ state, URL, the query words */
  function params() {
    return {q: st.q, repos: st.repos, cats: st.cats, after: st.after, before: st.before, sort: st.sort, dir: st.dir,
            offset: st.offset, limit: st.limit};
  }
  function cliLine() {
    var s = 'cx cserver.browse query "' + (st.q || '').replace(/"/g, '\\"') + '"';
    ['repos', 'cats', 'after', 'before', 'sort', 'dir'].forEach(function (k) { if (st[k]) s += ' --' + k + '=' + st[k]; });
    return s;
  }
  function syncUrl() {
    try {
      var u = new URL(window.location.href);
      URL_KEYS.forEach(function (k) {
        if (st[k]) u.searchParams.set(k, st[k]); else u.searchParams.delete(k);
      });
      if (st.view !== 'search') u.searchParams.set('view', st.view); else u.searchParams.delete('view');
      history.replaceState(null, '', u.toString());
    } catch (e) { /* old browser: the state stays in the page */ }
    $('cbr-json').href = st.view === 'graph' ? apiUrl('graph') + '&' + qs(graphParams())
                                             : apiUrl('search') + '&' + qs(params());
    $('cbr-cli').textContent = cliLine();
  }
  function queryWords() {
    var out = [];
    (st.q.match(/-?[^\s"]*"[^"]*"|\S+/g) || []).forEach(function (t) {
      if (t.charAt(0) === '-' || /^[A-Za-z_][\w.\-]*:/.test(t) || t.indexOf('::') >= 0) return;
      t = t.replace(/^"|"$/g, '').toLowerCase();
      if (t.length > 1) out.push(t);
    });
    return out;
  }
  function hl(text) {
    var s = esc(text);
    queryWords().forEach(function (w) {
      s = s.replace(new RegExp('(' + escRe(esc(w)) + ')', 'gi'), '<mark>$1</mark>');
    });
    return s;
  }
  function addToQuery(tok) {
    if ((' ' + st.q + ' ').indexOf(' ' + tok + ' ') < 0) st.q = (st.q ? st.q + ' ' : '') + tok;
    $('cbr-q').value = st.q;
    run();
  }

  /* ------------------------------------------------------------------ theme */
  function applyTheme(dark) {
    root.classList.toggle('dark', !!dark);
    document.body.style.backgroundColor = dark ? getComputedStyle(root).getPropertyValue('--cbr-bg').trim() : '';
  }
  function initTheme() {
    var stored = null;
    try { stored = localStorage.getItem(THEME_KEY) || localStorage.getItem('cserver.projects.theme'); } catch (e) { /* ignore */ }
    applyTheme(stored ? stored === 'dark' : !!CFG.dark_mode);
    $('cbr-theme').addEventListener('click', function () {
      var dark = !root.classList.contains('dark');
      applyTheme(dark);
      try { localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light'); } catch (e) { /* ignore */ }
      if (graph) graph.setDark(dark);
      if (gdata) drawLegend(gdata);
    });
  }

  /* ------------------------------------------------------------------ the pickers */
  function picked(kind) { return (st[kind] || '').split(',').filter(Boolean); }
  function pickerLabel(kind) {
    var wrap = root.querySelector('.cbr-pick[data-kind="' + kind + '"]');
    var btn = wrap.querySelector('.cbr-pick-btn');
    var s = picked(kind);
    var what = kind === 'repos' ? 'Repositories' : 'Categories';
    var shown = s.length === 0 ? 'all' : (s.length === 1 ? s[0] : s.length + ' selected');
    btn.innerHTML = what + ': <b>' + esc(shown) + '</b> &#9662;';
    btn.classList.toggle('set', s.length > 0);
    btn.title = s.length ? s.join('\n') : 'All ' + what.toLowerCase();
  }
  var pickTimer = null;
  function scheduleRun() { clearTimeout(pickTimer); pickTimer = setTimeout(run, 450); }
  function buildPicker(kind) {
    var wrap = root.querySelector('.cbr-pick[data-kind="' + kind + '"]');
    var btn = wrap.querySelector('.cbr-pick-btn');
    var pop = wrap.querySelector('.cbr-pick-pop');
    var list = (options && options[kind]) || [];
    pop.innerHTML = '';
    var filter = h('input', {type: 'search', placeholder: 'filter ' + list.length + (kind === 'repos' ? ' repositories' : ' categories')});
    var allBtn = h('button', {type: 'button', class: 'cbr-link', title: 'No filter: every one'}, 'all');
    var shownBtn = h('button', {type: 'button', class: 'cbr-link', title: 'Tick every one the filter shows'}, 'tick the shown');
    var box = h('div', {class: 'cbr-pick-list'});
    function visible() {
      var f = filter.value.toLowerCase();
      return list.filter(function (x) { return !f || x[0].toLowerCase().indexOf(f) >= 0; });
    }
    function render() {
      box.innerHTML = '';
      var sel = {};
      picked(kind).forEach(function (x) { sel[x] = 1; });
      visible().forEach(function (x) {
        var cb = h('input', {type: 'checkbox'});
        cb.checked = !!sel[x[0]];
        cb.addEventListener('change', function () {
          var s = picked(kind).filter(function (v) { return v !== x[0]; });
          if (cb.checked) s.push(x[0]);
          st[kind] = s.join(',');
          pickerLabel(kind);
          scheduleRun();
        });
        box.appendChild(h('label', {}, cb, h('span', {class: 'nm', title: x[0]}, x[0]), h('span', {class: 'n'}, String(x[1]))));
      });
    }
    filter.addEventListener('input', render);
    filter.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); shownBtn.click(); } });
    allBtn.addEventListener('click', function () { st[kind] = ''; pickerLabel(kind); render(); scheduleRun(); });
    shownBtn.addEventListener('click', function () {
      st[kind] = visible().map(function (x) { return x[0]; }).join(',');
      pickerLabel(kind); render(); scheduleRun();
    });
    pop.appendChild(filter);
    pop.appendChild(h('div', {class: 'cbr-pick-acts'}, allBtn, shownBtn));
    pop.appendChild(box);
    render();
    btn.onclick = function () {
      var open = pop.hidden;
      closePickers();
      pop.hidden = !open;
      if (open) { render(); filter.focus(); }
    };
    pickerLabel(kind);
  }
  function closePickers() {
    root.querySelectorAll('.cbr-pick-pop').forEach(function (p) { p.hidden = true; });
  }

  /* ------------------------------------------------------------------ run a query */
  function run(keepOffset) {
    if (keepOffset !== true) st.offset = 0;
    syncUrl();
    showError('');
    if (st.view === 'graph') { last = null; return loadGraph(); }
    var my = ++runToken;
    return call('search', params(), 'searching')
      .then(function (r) {
        if (my !== runToken) return;          // a newer query has started meanwhile
        last = r;
        render();
      })
      .catch(function (e) { showError(e.message); });
  }
  function statusLine(r) {
    var s = r.total + ' of ' + r.of + ' artifacts';
    if (r.total) s += ' · ' + (r.offset + 1) + '–' + (r.offset + r.rows.length) + ' shown';
    s += ' · sorted by ' + r.sort + (r.sort === 'relevance' ? '' : (r.dir === 'desc' ? ' ↓' : ' ↑'));
    s += ' · ' + r.ms + ' ms';
    if (r.catalog && r.catalog.built) s += ' · index loaded ' + r.catalog.built;
    $('cbr-status').textContent = s;
  }
  function render() {
    if (!last) return;
    statusLine(last);
    if (st.view === 'search') renderList();
    else if (st.view === 'browse') renderBrowse();
  }

  /* ------------------------------------------------------------------ Search view */
  function chip(t) {
    var c = h('button', {type: 'button', class: 'cbr-chip', title: 'Add tag:' + t + ' to the query'}, t);
    c.addEventListener('click', function (e) { e.stopPropagation(); addToQuery('tag:' + quoteIf(t)); });
    return c;
  }
  function renderList() {
    var ol = $('cbr-list');
    ol.innerHTML = '';
    last.rows.forEach(function (r) {
      var title = h('button', {type: 'button', class: 'cbr-r-title', html: hl(r.alias)});
      title.addEventListener('click', function () { openDetail(r.uid); });
      var li = h('li', {}, title);
      if (r.name && r.name !== r.alias) li.appendChild(h('span', {class: 'cbr-r-name', html: hl(r.name)}));
      if (r.migrated_to) li.appendChild(h('span', {class: 'cbr-badge', title: 'migrated to ' + r.migrated_to}, 'migrated'));
      var when = r.updated ? 'updated ' + r.updated : (r.created ? 'created ' + r.created : '');
      li.appendChild(h('div', {class: 'cbr-r-meta'}, [r.cat, r.repo || '(registry)', when].filter(Boolean).join(' · ')));
      if (r.snippet) li.appendChild(h('div', {class: 'cbr-r-snip', html: hl(r.snippet)}));
      if (r.tags && r.tags.length) {
        var tg = h('div');
        r.tags.forEach(function (t) { tg.appendChild(chip(t)); });
        li.appendChild(tg);
      }
      ol.appendChild(li);
    });
    if (!last.rows.length) {
      ol.appendChild(h('li', {class: 'cbr-muted'}, 'Nothing matches. Try fewer words, or clear the pickers and the dates.'));
    }
    pager('search');
  }
  function pager(which) {
    var el = root.querySelector('[data-pager="' + which + '"]');
    el.innerHTML = '';
    if (!last || !last.total || (last.offset === 0 && last.total <= last.rows.length && st.limit === 50)) return;
    var prev = h('button', {type: 'button', class: 'cbr-btn'}, '‹ previous');
    prev.disabled = st.offset === 0;
    prev.addEventListener('click', function () { st.offset = Math.max(0, st.offset - st.limit); run(true); });
    var next = h('button', {type: 'button', class: 'cbr-btn'}, 'next ›');
    next.disabled = st.offset + st.limit >= last.total;
    next.addEventListener('click', function () { st.offset += st.limit; run(true); });
    var size = h('select', {});
    [25, 50, 100, 200, 500].forEach(function (n) {
      var o = h('option', {value: String(n)}, String(n));
      if (n === st.limit) o.selected = true;
      size.appendChild(o);
    });
    size.addEventListener('change', function () { st.limit = parseInt(size.value, 10); run(); });
    el.appendChild(prev);
    el.appendChild(h('span', {}, (last.offset + 1) + '–' + (last.offset + last.rows.length) + ' of ' + last.total));
    el.appendChild(next);
    el.appendChild(h('span', {}, 'per page'));
    el.appendChild(size);
  }

  /* ------------------------------------------------------------------ Browse view */
  var FACETS = [['repo', 'Repositories'], ['cat', 'Categories'], ['tag', 'Tags'], ['year', 'Created'], ['generator', 'Made by']];
  var facetOpen = {};
  function renderBrowse() {
    var tb = $('cbr-table').querySelector('tbody');
    tb.innerHTML = '';
    last.rows.forEach(function (r) {
      var a = h('td', {class: 'alias', html: hl(r.alias) + (r.name && r.name !== r.alias ? '<span class="nm">' + hl(r.name) + '</span>' : '') +
                       (r.migrated_to ? '<span class="cbr-badge">migrated</span>' : '')});
      var tags = h('td', {});
      (r.tags || []).slice(0, 6).forEach(function (t) { tags.appendChild(chip(t)); });
      var tr = h('tr', {}, a, h('td', {}, r.cat), h('td', {class: 'repo'}, r.repo || '(registry)'), tags,
                 h('td', {class: 'when'}, r.created), h('td', {class: 'when'}, r.updated));
      tr.addEventListener('click', function () { openDetail(r.uid); });
      tb.appendChild(tr);
    });
    if (!last.rows.length) tb.appendChild(h('tr', {}, h('td', {colspan: '6', class: 'cbr-muted'}, 'Nothing matches.')));
    $('cbr-table').querySelectorAll('th[data-sort]').forEach(function (th) {
      var on = th.getAttribute('data-sort') === last.sort;
      th.classList.toggle('sorted', on);
      th.textContent = th.getAttribute('data-label') + (on ? (last.dir === 'desc' ? ' ▾' : ' ▴') : '');
    });
    renderFacets();
    pager('browse');
  }
  function renderFacets() {
    var box = $('cbr-facets');
    box.innerHTML = '';
    if (!last.facets) return;
    FACETS.forEach(function (f) {
      var vals = last.facets[f[0]] || [];
      if (!vals.length) return;
      var sec = h('div', {class: 'cbr-facet'}, h('h3', {}, f[1]));
      var lim = facetOpen[f[0]] ? vals.length : 8;
      vals.slice(0, lim).forEach(function (x) {
        var b = h('button', {type: 'button', title: x[0]}, h('span', {class: 'nm'}, x[0]), h('span', {class: 'n'}, String(x[1])));
        b.addEventListener('click', function () { applyFacet(f[0], x[0]); });
        sec.appendChild(b);
      });
      if (vals.length > 8) {
        var more = h('button', {type: 'button', class: 'more'}, facetOpen[f[0]] ? 'fewer' : 'all ' + vals.length);
        more.addEventListener('click', function () { facetOpen[f[0]] = !facetOpen[f[0]]; renderFacets(); });
        sec.appendChild(more);
      }
      box.appendChild(sec);
    });
  }
  function applyFacet(kind, v) {
    if (kind === 'repo' || kind === 'cat') {
      var key = kind === 'repo' ? 'repos' : 'cats';
      st[key] = v;
      pickerLabel(key);
      run();
    } else if (kind === 'tag') {
      addToQuery('tag:' + quoteIf(v));
    } else if (kind === 'year') {
      if (!/^\d{4}$/.test(v)) return;
      st.after = v + '-01-01';
      st.before = (parseInt(v, 10) + 1) + '-01-01';
      $('cbr-after').value = st.after;
      $('cbr-before').value = st.before;
      run();
    } else if (kind === 'generator') {
      addToQuery(v === '(none)' ? '-has:generator' : 'generator.method:' + v);
    }
  }

  /* ------------------------------------------------------------------ the detail of one artifact */
  function cmdLine(text) {
    var b = h('button', {type: 'button', class: 'cbr-copy', title: 'Copy'}, 'copy');
    b.addEventListener('click', function () { copy(text, b); });
    return h('div', {class: 'cbr-cmd'}, h('code', {}, text), b);
  }
  var detailToken = 0;       // a later open or a close wins over an answer still on its way
  function openDetail(uid) {
    if (!uid) return;
    st.uid = uid;
    syncUrl();
    var my = ++detailToken;
    call('artifact', {uid: uid}, 'reading the artifact').then(function (d) {
      if (my !== detailToken) return;
      subtitle({index: d.index});
      var box = $('cbr-detail');
      box.innerHTML = '';
      var close = h('button', {type: 'button', class: 'cbr-d-close', title: 'Close (Esc)'}, '×');
      close.addEventListener('click', closeDetail);
      box.appendChild(h('div', {class: 'cbr-d-head'}, h('h2', {}, d.row.alias), close));
      if (d.row.name && d.row.name !== d.row.alias) box.appendChild(h('div', {class: 'cbr-d-name'}, d.row.name));
      box.appendChild(cmdLine(d.cref));
      var facts = h('table', {class: 'cbr-d-facts'});
      [['Category', d.row.cat], ['Repository', d.row.repo || '(registry)'], ['UID', d.row.uid],
       ['Created', d.row.created], ['Updated', d.row.updated], ['Path', d.path || '']].forEach(function (x) {
        if (x[1]) facts.appendChild(h('tr', {}, h('td', {}, x[0]), h('td', {}, x[1])));
      });
      box.appendChild(facts);
      if (d.row.migrated_to) {
        var m = h('p', {}, 'Migrated to ');
        if (d.migrated_to_uid) {
          var go = h('a', {href: '#'}, d.row.migrated_to);
          go.addEventListener('click', function (e) { e.preventDefault(); openDetail(d.migrated_to_uid); });
          m.appendChild(go);
        } else m.appendChild(document.createTextNode(d.row.migrated_to));
        box.appendChild(m);
      }
      if (d.row.tags && d.row.tags.length) {
        var tg = h('div');
        d.row.tags.forEach(function (t) { tg.appendChild(chip(t)); });
        box.appendChild(tg);
      }
      box.appendChild(focusBar(d.row.uid));
      linkList(box, 'Connects to', d.connections, function (c) { return c.cref; });
      linkList(box, 'Uses', d.uses, function (c) { return c.ref; });
      linkList(box, 'AI uses (reads the memory and skills of)', d.ai_uses, function (c) { return c.cref; });
      if (d.index && d.index.ready) {
        linkList(box, 'Connected from', d.incoming, null, d.incoming_total);
      } else if (d.index) {
        box.appendChild(h('h3', {}, 'Connected from'));
        box.appendChild(h('p', {class: 'cbr-muted'}, 'The connections are still being read (' + num(d.index.done) +
          ' of ' + num(d.index.total) + ' artifacts) - open this artifact again in a moment.'));
      }
      if (d.files) {
        box.appendChild(h('h3', {}, 'Files'));
        var fbox = h('div', {class: 'cbr-files'});
        var fbtn = h('button', {type: 'button', class: 'cbr-btn'}, 'List the files');
        fbtn.addEventListener('click', function () { listFiles(d.row.uid, fbox, fbtn); });
        box.appendChild(fbtn);
        box.appendChild(fbox);
      }
      box.appendChild(h('h3', {}, 'Commands'));
      (d.commands || []).forEach(function (c) { box.appendChild(cmdLine(c)); });
      box.appendChild(h('h3', {}, 'Meta (_cmeta)'));
      box.appendChild(h('pre', {}, JSON.stringify(d.meta, null, 2)));
      if (d.desc) {
        box.appendChild(h('h3', {}, 'Description (' + d.desc_file + ')'));
        box.appendChild(h('pre', {}, JSON.stringify(d.desc, null, 2)));
      }
      box.hidden = false;
      box.scrollTop = 0;
    }).catch(function (e) { showError(e.message); });
  }
  function closeDetail() {
    detailToken++;
    $('cbr-detail').hidden = true;
    st.uid = '';
    syncUrl();
  }
  // "Focus the graph here": everything within N connections of this artifact, in the Graph tab
  function depthSelect(cur) {
    var sel = h('select', {title: 'How many connections away'});
    [1, 2, 3, 4, 5, 6, GCFG.depth_max].forEach(function (v) {
      var o = h('option', {value: String(v)}, v === GCFG.depth_max ? 'all' : String(v));
      if (String(v) === String(cur || 2)) o.selected = true;
      sel.appendChild(o);
    });
    return sel;
  }
  function focusBar(uid) {
    var sel = depthSelect(st.depth);
    var b = h('button', {type: 'button', class: 'cbr-btn cbr-primary'}, 'Focus the graph here');
    b.addEventListener('click', function () { focusOn(uid, sel.value); });
    return h('div', {class: 'cbr-d-graph'}, b, h('label', {}, 'depth ', sel));
  }
  function focusOn(uid, depth) {
    st.focus = uid;
    st.depth = depth && String(depth) !== '2' ? String(depth) : '';
    closeDetail();
    setView('graph');
  }
  // A list of linked artifacts: each opens its detail; one not shown here stays as plain text
  function linkList(box, title, items, refOf, total) {
    if (!items || !items.length) return;
    var n = total || items.length;
    box.appendChild(h('h3', {}, title + ' (' + num(n) + ')'));
    var ul = h('ul', {class: 'cbr-links'});
    items.forEach(function (c) {
      if (c.found === false) {
        ul.appendChild(h('li', {class: 'missing', title: 'not shown by this server'}, refOf ? refOf(c) : c.alias));
        return;
      }
      var a = h('a', {href: '#', title: refOf ? refOf(c) : c.alias}, c.alias);
      a.addEventListener('click', function (e) { e.preventDefault(); openDetail(c.uid); });
      ul.appendChild(h('li', {}, a, h('span', {class: 'cbr-muted'}, '  ' + c.cat + (c.uses ? ' · uses it' : '') +
        (c.ai ? ' · its AI reads this one' : ''))));
    });
    if (n > items.length) {
      ul.appendChild(h('li', {class: 'cbr-muted'}, '... and ' + num(n - items.length) +
        ' more: focus the graph here to see them all'));
    }
    box.appendChild(ul);
  }

  /* ------------------------------------------------------------------ the files of one artifact */
  var blobUrl = null;
  function listFiles(uid, box, btn) {
    if (box.getAttribute('data-loaded')) {
      box.hidden = !box.hidden;
      btn.textContent = box.hidden ? 'List the files' : 'Hide the files';
      return;
    }
    call('files', {uid: uid}, 'listing the files').then(function (j) {
      box.innerHTML = '';
      box.hidden = false;
      box.setAttribute('data-loaded', '1');
      btn.textContent = 'Hide the files';
      box.appendChild(h('div', {class: 'cbr-muted'}, j.files.length + ' of ' + num(j.total) + (j.more ? '+' : '') +
        ' file' + (j.total === 1 ? '' : 's') + ' - the meta first; click one to read it'));
      var ul = h('ul', {class: 'cbr-flist'});
      var view = h('div', {class: 'cbr-fview'});
      j.files.forEach(function (f) {
        var li = h('li', {title: f.mtime}, h('span', {class: 'nm'}, f.rel), h('span', {class: 'n'}, fmtSize(f.size)));
        li.addEventListener('click', function () {
          ul.querySelectorAll('li.on').forEach(function (x) { x.classList.remove('on'); });
          li.classList.add('on');
          openFile(uid, f.rel, view);
        });
        ul.appendChild(li);
      });
      box.appendChild(ul);
      box.appendChild(view);
    }).catch(function (e) { box.hidden = false; box.textContent = e.message; });
  }
  function openFile(uid, rel, view) {
    call('file', {uid: uid, rel: rel}, 'reading ' + rel).then(function (j) {
      view.innerHTML = '';
      if (blobUrl) { URL.revokeObjectURL(blobUrl); blobUrl = null; }
      var close = h('button', {type: 'button', class: 'cbr-copy'}, 'close');
      close.addEventListener('click', function () { view.innerHTML = ''; });
      view.appendChild(h('div', {class: 'cbr-fhead'}, h('b', {}, j.rel), ' · ' + fmtSize(j.size) +
        (j.truncated ? ' · the first 512 KB' : '') + ' ', close));
      if (j.kind === 'text') {
        view.appendChild(h('pre', {}, j.text));
      } else if (j.kind === 'binary' && j.b64) {
        var bin = atob(j.b64), arr = new Uint8Array(bin.length);
        for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
        blobUrl = URL.createObjectURL(new Blob([arr], {type: j.mime}));
        view.appendChild(h('a', {href: blobUrl, target: '_blank', rel: 'noopener'}, 'open in a new tab'));
        if (j.mime.indexOf('image/') === 0) view.appendChild(h('img', {src: blobUrl, alt: j.rel}));
        else if (j.mime === 'application/pdf') view.appendChild(h('iframe', {src: blobUrl, title: j.rel}));
      } else {
        view.appendChild(h('p', {class: 'cbr-muted'}, j.note || 'not shown'));
      }
    }).catch(function (e) { view.textContent = e.message; });
  }

  /* ------------------------------------------------------------------ Graph view */
  var graph = null;          // the graph on screen (CBRGraph)
  var gdata = null;          // what the server sent for it
  var gToken = 0;
  var gTimes = {};           // the stages measured here: transfer, draw, layout
  function graphParams() {
    return {q: st.q, repos: st.repos, cats: st.cats, after: st.after, before: st.before, focus: st.focus,
            depth: st.depth, max_nodes: st.max_nodes, categories: st.categories, core: st.core,
            isolated: st.isolated, neighbors: st.neighbors};
  }
  function loadGraph() {
    var my = ++gToken, t0 = performance.now();
    syncGraphControls();
    // the first graph of a server process waits for the connections to be read (seconds, once)
    var what = indexState && indexState.ready ? 'building the graph'
                                              : 'building the graph (the first one reads every connection)';
    return call('graph', graphParams(), what)
      .then(function (g) {
        if (my !== gToken) return;
        gTimes = {transfer: Math.max(0, performance.now() - t0 - (g.timing.server || 0))};
        gdata = g;
        subtitle({index: g.index});
        renderGraph(g);
      })
      .catch(function (e) { if (my === gToken) showError(e.message); });
  }
  function isDark() { return root.classList.contains('dark'); }
  function renderGraph(g) {
    graph = CBRGraph.create($('cbr-svg'), g, {
      dark: isDark(),
      labelsAll: st.labels === '1',
      showLinks: st.links === '1',
      onSelect: function (n) {
        if (n.kind === 'artifact') openDetail(n.id);
        else if (n.kind === 'category' && n.uid) openDetail(n.uid);
      },
      onFocus: function (n) {
        if (n.kind === 'artifact') focusOn(n.id, st.depth);
        else if (n.kind === 'category') {         // a category: the graph of that category alone
          st.cats = n.cat;
          st.focus = '';
          pickerLabel('cats');
          if (options) buildPicker('cats');
          run();
        }
      },
      onZoom: function (k) { $('cbr-g-zoom').textContent = Math.round(k * 100) + '%'; },
      onBusy: function (on, n) { busy(on, 'arranging ' + num(n) + ' nodes'); },
      onSettled: function (ms) { gTimes.layout = ms; showTimes(); }
    });
    gTimes.draw = graph.buildMs();
    drawLegend(g);
    showNotices(g);
    showFocus(g);
    graphStatus(g);
    showTimes();
  }
  function graphStatus(g) {
    var s = g.stats;
    var t = num(s.matched) + (g.focus ? ' within ' + g.focus.depth + ' hop' + (g.focus.depth === 1 ? '' : 's')
                                      : ' matching') +
      ' · ' + num(s.drawn) + ' drawn in ' + num(s.categories) + ' categor' + (s.categories === 1 ? 'y' : 'ies') +
      ' · ' + num(s.links) + ' connection' + (s.links === 1 ? '' : 's') +
      (s.uses ? ', ' + num(s.uses) + ' uses' : '') +
      (s.ai_uses ? ', ' + num(s.ai_uses) + ' AI uses' : '') +
      (s.grown ? ' · +' + num(s.grown) + ' connected' : '') +
      (st.links === '1' || !g.options.categories || !s.links ? '' : ' (drawn on hover)');
    $('cbr-status').textContent = t;
  }
  // One line of timings, so a slow answer shows WHICH stage was slow
  function showTimes() {
    if (!gdata) return;
    var T = gdata.timing || {}, I = gdata.index || {};
    var bits = ['server <b>' + msText(T.server || 0) + '</b> (catalog ' + msText(T.catalog || 0) +
                ' · connections ' + msText(T.index || 0) + ' · selection ' + msText(T.select || 0) +
                ' · graph ' + msText(T.graph || 0) + ')'];
    if (gTimes.transfer != null) bits.push('transfer ' + msText(gTimes.transfer));
    if (gTimes.draw != null) bits.push('draw ' + msText(gTimes.draw));
    bits.push('layout ' + (gTimes.layout == null ? '...' : msText(gTimes.layout)));
    bits.push(num(gdata.nodes.length) + ' nodes / ' + num(gdata.links.length) + ' edges');
    if (I.ready) {
      bits.push('connection index: ' + num(I.total) + ' artifacts, ' + num(I.links) + ' connections, ' +
                num(I.uses) + ' uses' + (I.ai_uses ? ', ' + num(I.ai_uses) + ' AI uses' : '') + ', read in ' +
                msText(I.ms) + ' at ' + esc((I.built || '').slice(11, 16)));
    }
    $('cbr-g-time').innerHTML = bits.join(' &middot; ');
  }
  function showNotices(g) {
    var box = $('cbr-g-notices');
    box.innerHTML = '';
    (g.notices || []).forEach(function (t) { box.appendChild(h('div', {}, t)); });
  }
  function showFocus(g) {
    var el = $('cbr-g-focus');
    el.innerHTML = '';
    if (!st.focus) { el.hidden = true; return; }
    el.hidden = false;
    el.appendChild(document.createTextNode('Focus: '));
    el.appendChild(h('b', {}, g.focus ? g.focus.alias : st.focus));
    var sel = depthSelect(st.depth);
    sel.addEventListener('change', function () { st.depth = sel.value === '2' ? '' : sel.value; loadGraph(); syncUrl(); });
    el.appendChild(h('label', {}, ' depth ', sel));
    var x = h('button', {type: 'button', class: 'cbr-link', title: 'Back to the graph of the query'}, 'exit');
    x.addEventListener('click', function () { st.focus = ''; st.depth = ''; syncUrl(); loadGraph(); });
    el.appendChild(x);
  }
  function drawLegend(g) {
    var legend = $('cbr-legend');
    legend.innerHTML = '';
    var cats = g.cats || [];
    cats.slice(0, 12).forEach(function (c) {
      var sw = h('i');
      sw.style.background = CBRGraph.colour(c[0], isDark());
      var row = h('button', {type: 'button', title: c[0] + ': ' + c[1] + ' drawn - click to select it'},
                  sw, h('span', {class: 'nm'}, c[0]), h('span', {class: 'n'}, num(c[1])));
      row.addEventListener('click', function () { if (graph) graph.select('__cat__' + c[2]); });
      legend.appendChild(row);
    });
    if (cats.length > 12) {
      var rest = cats.slice(12).reduce(function (s, c) { return s + c[1]; }, 0);
      legend.appendChild(h('div', {class: 'cbr-muted'}, '+ ' + (cats.length - 12) + ' more categories (' + num(rest) + ')'));
    }
    legend.hidden = !cats.length || !on(st.categories, true);
  }
  // The graph switches follow the state (the URL), and change it
  function syncGraphControls() {
    var cats = on(st.categories, true);
    $('cbr-g-categories').checked = cats;
    $('cbr-g-core').checked = on(st.core, false);
    $('cbr-g-core').disabled = !cats;
    $('cbr-g-isolated').checked = on(st.isolated, false);
    $('cbr-g-isolated').disabled = cats;
    $('cbr-g-neighbors').checked = on(st.neighbors, false);
    $('cbr-g-neighbors').disabled = !!st.focus;
    $('cbr-g-labels').checked = st.labels === '1';
    $('cbr-g-max').value = st.max_nodes || '';
    $('cbr-g-max').placeholder = String(GCFG.max_nodes);
    $('cbr-g-max').max = String(GCFG.max);
    var lk = $('cbr-g-links');
    lk.classList.toggle('on', st.links === '1');
    lk.setAttribute('aria-pressed', st.links === '1' ? 'true' : 'false');
  }
  function initGraphControls() {
    // what changes the server's answer reloads the graph; names and connections are redrawn on the spot
    [['categories', true], ['core', false], ['isolated', false], ['neighbors', false]].forEach(function (x) {
      $('cbr-g-' + x[0]).addEventListener('change', function () {
        var v = $('cbr-g-' + x[0]).checked;
        st[x[0]] = v === x[1] ? '' : (v ? '1' : '0');
        syncUrl();
        loadGraph();
      });
    });
    $('cbr-g-max').addEventListener('change', function () {
      var raw = $('cbr-g-max').value.trim(), v = parseInt(raw, 10);
      if (raw === '' || !isFinite(v)) st.max_nodes = '';
      else st.max_nodes = String(Math.max(10, Math.min(GCFG.max, v)));
      syncUrl();
      loadGraph();
    });
    $('cbr-g-labels').addEventListener('change', function () {
      st.labels = $('cbr-g-labels').checked ? '1' : '';
      syncUrl();
      if (graph) graph.setLabels(st.labels === '1');
    });
    $('cbr-g-links').addEventListener('click', function () {
      st.links = st.links === '1' ? '' : '1';
      syncUrl();
      syncGraphControls();
      if (graph) graph.setLinks(st.links === '1');
      if (gdata) graphStatus(gdata);
    });
    $('cbr-g-fit').addEventListener('click', function () { if (graph) graph.fit(); });
    $('cbr-g-one').addEventListener('click', function () { if (graph) graph.reset(); });
    $('cbr-g-relayout').addEventListener('click', function () {
      if (graph) { gTimes.layout = null; showTimes(); graph.relayout(); }
    });
    var rt = 0;
    window.addEventListener('resize', function () {
      clearTimeout(rt);
      rt = setTimeout(function () { if (graph && st.view === 'graph') graph.resize(); }, 150);
    });
  }

  /* ------------------------------------------------------------------ views */
  function setView(v) {
    st.view = v;
    root.querySelectorAll('.cbr-tab').forEach(function (b) {
      var on = b.getAttribute('data-view') === v;
      b.classList.toggle('on', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    VIEWS.forEach(function (x) { $('cbr-view-' + x).hidden = x !== v; });
    syncUrl();
    if (v === 'graph') loadGraph();
    else if (last) render();
    else run();
  }

  /* ------------------------------------------------------------------ start */
  function init() {
    initTheme();
    $('cbr-q').value = st.q;
    $('cbr-after').value = st.after;
    $('cbr-before').value = st.before;
    $('cbr-table').querySelectorAll('th').forEach(function (th) {
      th.setAttribute('data-label', th.textContent);
      if (!th.getAttribute('data-sort')) return;
      th.addEventListener('click', function () {
        var s = th.getAttribute('data-sort');
        if (last && last.sort === s) st.dir = last.dir === 'desc' ? 'asc' : 'desc';
        else { st.sort = s; st.dir = (s === 'created' || s === 'updated') ? 'desc' : 'asc'; }
        st.sort = s;
        run();
      });
    });
    root.querySelectorAll('.cbr-tab').forEach(function (b) {
      b.addEventListener('click', function () { setView(b.getAttribute('data-view')); });
    });
    // a new query (or new dates) leaves a focus: the graph is of the query again; the pickers keep it (a scope)
    $('cbr-form').addEventListener('submit', function (e) {
      e.preventDefault();
      closePickers();
      st.q = $('cbr-q').value.trim();
      st.sort = '';
      st.dir = '';
      st.focus = '';
      run();
    });
    ['after', 'before'].forEach(function (k) {
      $('cbr-' + k).addEventListener('change', function () { st[k] = $('cbr-' + k).value; st.focus = ''; run(); });
    });
    $('cbr-clear').addEventListener('click', function () {
      st.q = st.repos = st.cats = st.after = st.before = st.sort = st.dir = st.focus = st.depth = '';
      $('cbr-q').value = ''; $('cbr-after').value = ''; $('cbr-before').value = '';
      pickerLabel('repos'); pickerLabel('cats');
      if (options) { buildPicker('repos'); buildPicker('cats'); }
      run();
    });
    $('cbr-help-btn').addEventListener('click', function () { $('cbr-help').hidden = !$('cbr-help').hidden; });
    $('cbr-reload').addEventListener('click', function () {
      call('reload', {}, 'reloading the index').then(function (o) {
        options = o;
        subtitle(o);
        buildPicker('repos');
        buildPicker('cats');
        run();
      }).catch(function (e) { showError(e.message); });
    });
    initGraphControls();
    root.querySelectorAll('[data-copy-from]').forEach(function (b) {
      b.addEventListener('click', function () { copy($(b.getAttribute('data-copy-from')).textContent, b); });
    });
    document.addEventListener('click', function (e) { if (!e.target.closest('.cbr-pick')) closePickers(); });
    document.addEventListener('keydown', function (e) {
      var tag = (e.target && e.target.tagName) || '';
      if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(tag)) { e.preventDefault(); $('cbr-q').focus(); }
      if (e.key === 'Escape') { closePickers(); if (!$('cbr-detail').hidden) closeDetail(); }
    });
    pickerLabel('repos');
    pickerLabel('cats');
    var wantUid = st.uid;
    call('options', {}, 'loading the index').then(function (o) {
      options = o;
      subtitle(o);
      buildPicker('repos');
      buildPicker('cats');
      setView(st.view);
      if (wantUid) openDetail(wantUid);
    }).catch(function (e) { showError(e.message); });
  }
  // The connections are read in the background; any answer that carries the state of that index updates this
  // line (no polling: on the engine cserver every call can land in another worker process, with its own index)
  function subtitle(o) {
    if (o && o.total != null) options = o;
    if (o && o.index) indexState = o.index;
    if (!options) return;
    $('cbr-sub').textContent = 'Search, browse and graph ' + num(options.total) + ' artifacts in ' +
      options.repos.length + ' repositories and ' + options.cats.length + ' categories' +
      (indexState && indexState.ready ? ', joined by ' + num(indexState.links) + ' connections.' : '.');
  }
  init();
})();
