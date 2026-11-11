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
  var SHARED_THEME = 'cmeta.theme';           // the theme of every page of this server (2026-11-10)
  var VIEWS = ['browse', 'search', 'graph'];
  var GCFG = CFG.graph || {max_nodes: 300, max: 1000, depth_max: 12};

  // The state in the URL: the query, the view, the open artifact, and the graph (focus, depth, nodes, switches:
  // '' = the default, '1' / '0' = set). A bare page opens on Browse: the categories, nothing searched yet.
  // An artifact is named there by its cRef, never by a bare UID (unique only with its category's): the open one is
  // cref=<category UID>::<artifact UID>, a focus the same; st.uid is the page's own handle, resolved by the server.
  var URL_KEYS = ['q', 'repos', 'cats', 'after', 'before', 'sort', 'dir', 'cref', 'file', 'focus', 'depth', 'max_nodes',
                  'categories', 'core', 'isolated', 'neighbors', 'labels', 'links'];
  var st = {view: 'browse', uid: ''};
  URL_KEYS.forEach(function (k) { st[k] = ''; });
  Object.keys(st).forEach(function (k) { if (CFG.state && CFG.state[k]) st[k] = CFG.state[k]; });
  if (VIEWS.indexOf(st.view) < 0) st.view = 'browse';
  st.offset = 0;
  st.limit = 50;

  var options = null;      // {repos: [[name, n]], cats: [[name, n]], categories: [{alias, n, name, desc, repos}], total, catalog, index}
  var tocFold = {};        // the folded groups of the category index (by their prefix)
  var tocFilter = '';      // what the filter box above the category index holds
  var indexState = null;   // the connection index as the last answer reported it: {ready, links, ...}
  var last = null;         // the last search result
  var lastView = '';       // the tab it was made for (a Browse listing is not a Search result)
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

  // A location written in a text as {{{<category>::<alias>,<UID>}}}/<path> (how memories, records and docs name a
  // place inside an artifact) becomes a link that opens that artifact here - and that file, when a path follows
  var CREF_RE = /\{\{\{([^{}:]+)::([^{}]+?),([0-9a-fA-F]{16})\}\}\}((?:\/[^\s"'`<>)\]]*)?)/g;
  function withRefs(text) {
    var frag = document.createDocumentFragment(), last = 0, m;
    CREF_RE.lastIndex = 0;
    while ((m = CREF_RE.exec(text))) {
      var rel = m[4].replace(/[.,;:]+$/, '');
      var end = m.index + m[0].length - (m[4].length - rel.length);
      if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      frag.appendChild(refLink(m[3].toLowerCase(), rel.replace(/^\/+/, ''), text.slice(m.index, end), m[1], m[2]));
      last = end;
      CREF_RE.lastIndex = end;
    }
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    return frag;
  }
  // The page of one artifact (cserver.cref): /cref/<category>::<alias>,<UID>[/<path>] - the cRef stays in the
  // address bar (a host that serves this page says where its /cref/ is: CFG.cref_url). A row of the search or
  // the table opens it; the graph keeps its side panel and offers it.
  function crefUrl(cat, alias, uid, rel) {
    return (CFG.cref_url || ((CFG.url_server || '/') + 'cref/')) + encodeURI(cat + '::' + alias + ',' + uid) +
           (rel ? '/' + rel.split('/').map(encodeURIComponent).join('/') : '');
  }
  // this page with another state (a category, a repository, the graph of one artifact): the same address, new keys
  function pageUrl(changes) {
    var u = new URL(window.location.href);
    URL_KEYS.concat(['view']).forEach(function (k) { u.searchParams.delete(k); });
    Object.keys(changes).forEach(function (k) { if (changes[k]) u.searchParams.set(k, changes[k]); });
    return u.toString();
  }
  function refLink(uid, rel, label, cat, alias) {
    return h('a', {href: crefUrl(cat, alias, uid, rel), class: 'cbr-cref',
                   title: 'open ' + (rel ? rel + ' of ' : '') + (alias || 'this artifact')}, label);
  }
  // how this page names an artifact in its address: <category UID>::<artifact UID>
  function crefOf(catUid, uid) { return catUid ? catUid.toLowerCase() + '::' + uid : uid; }
  // A text block coloured by its kind (js/hl.js, when its name says one) with the cRefs inside as links; a plain
  // text keeps the cRef links alone
  function codePre(text, name) {
    var pre = h('pre', {});
    if (window.cmetaHL && cmetaHL.lang(name)) pre.innerHTML = cmetaHL(text, name, {cref_url: CFG.cref_url || ((CFG.url_server || '/') + 'cref/')});
    else pre.appendChild(withRefs(text));
    return pre;
  }
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
        var v = st[k];
        if (DEFAULT_PICK.hasOwnProperty(k)) {
          // a picker at the server's default stays out of the address; "all" goes in as "*" when that default
          // leaves some out, so that a reload keeps it
          if (v === DEFAULT_PICK[k]) v = ''; else if (!v && DEFAULT_PICK[k]) v = '*';
        }
        if (v) u.searchParams.set(k, v); else u.searchParams.delete(k);
      });
      if (st.view !== 'search') u.searchParams.set('view', st.view); else u.searchParams.delete('view');
      u.searchParams.delete('uid');            // an older link's bare UID: the cRef names the artifact now
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
  // One dark or light for every page of this server (2026-11-10): cmeta.theme in this browser, read first - this
  // page's own key until there is one, which then becomes the shared one -, written by the switch, and followed when
  // another page (another tab) changes it
  function applyTheme(dark) {
    root.classList.toggle('dark', !!dark);
    document.body.style.backgroundColor = dark ? getComputedStyle(root).getPropertyValue('--cbr-bg').trim() : '';
  }
  function setDark(dark) {
    applyTheme(dark);
    if (graph) graph.setDark(dark);
    if (gdata) drawLegend(gdata);
  }
  function initTheme() {
    var stored = null;
    try {
      stored = localStorage.getItem(SHARED_THEME);
      if (!stored) {
        stored = localStorage.getItem(THEME_KEY) || localStorage.getItem('cserver.projects.theme');
        if (stored) localStorage.setItem(SHARED_THEME, stored);
      }
    } catch (e) { /* ignore */ }
    applyTheme(stored ? stored === 'dark' : !!CFG.dark_mode);
    $('cbr-theme').addEventListener('click', function () {
      var dark = !root.classList.contains('dark');
      setDark(dark);
      try {
        localStorage.setItem(SHARED_THEME, dark ? 'dark' : 'light');
        localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light');
      } catch (e) { /* ignore */ }
    });
    window.addEventListener('storage', function (e) {
      if (e.key === SHARED_THEME && e.newValue && (e.newValue === 'dark') !== root.classList.contains('dark')) setDark(e.newValue === 'dark');
    });
  }

  /* ------------------------------------------------------------------ the pickers */
  // A picker holds what is ticked: names (none = all, "*" = all), a name with "-" in front left out ("-fgg-arc":
  // all but fgg-arc; "-*": none at all), as the server reads it. The server's unticked repositories (Clear goes back
  // to them, the address leaves them out) come in CFG.untick.
  var DEFAULT_PICK = {repos: ((CFG.untick && CFG.untick.repos) || []).map(function (x) { return '-' + x; }).join(','), cats: ''};
  function picked(kind) { return (st[kind] || '').split(',').filter(Boolean); }
  function pickParts(kind) {
    var keep = [], drop = [];
    picked(kind).forEach(function (x) {
      if (x.charAt(0) === '-') { if (x.length > 1) drop.push(x.slice(1)); } else if (x !== '*') keep.push(x);
    });
    return {keep: keep, drop: drop};
  }
  function nameIs(name, want) {
    // an alias, alias,UID, the part after "@", or a pattern - as the server matches them
    var n = String(name || '').toLowerCase(), w = String(want || '').toLowerCase();
    if (w.indexOf(',') >= 0) w = w.split(',').pop().trim();
    if (/[*?[]/.test(w)) return new RegExp('^' + escRe(w).replace(/\\\*/g, '.*').replace(/\\\?/g, '.') + '$').test(n);
    return n === w || (n.indexOf('@') >= 0 && n.split('@')[1] === w);
  }
  function isTicked(kind, name) {
    var p = pickParts(kind);
    if (p.keep.length && !p.keep.some(function (w) { return nameIs(name, w); })) return false;
    return !p.drop.some(function (w) { return nameIs(name, w); });
  }
  function encodePick(kind, on) {
    // the shortest value for the names ticked: all ('') , none ('-*'), the few left out, or the few kept
    var all = ((options && options[kind]) || []).map(function (x) { return x[0]; });
    var yes = all.filter(function (n) { return on[n]; }), no = all.filter(function (n) { return !on[n]; });
    if (!no.length) return '';
    if (!yes.length) return '-*';
    return no.length <= yes.length ? no.map(function (n) { return '-' + n; }).join(',') : yes.join(',');
  }
  function pickerLabel(kind) {
    var wrap = root.querySelector('.cbr-pick[data-kind="' + kind + '"]');
    var btn = wrap.querySelector('.cbr-pick-btn');
    var p = pickParts(kind);
    var what = kind === 'repos' ? 'Repositories' : 'Categories';
    var none = p.drop.indexOf('*') >= 0;
    var shown = none ? 'none' : p.keep.length ? (p.keep.length === 1 ? p.keep[0] : p.keep.length + ' selected') +
                                             (p.drop.length ? ' - ' + p.drop.length : '')
              : p.drop.length ? 'all but ' + (p.drop.length === 1 ? p.drop[0] : p.drop.length) : 'all';
    btn.innerHTML = what + ': <b>' + esc(shown) + '</b> &#9662;';
    btn.classList.toggle('set', shown !== 'all');
    btn.title = none ? 'None ticked' : (p.keep.length ? p.keep.join('\n') : 'All ' + what.toLowerCase()) +
                (p.drop.length ? '\nleft out:\n' + p.drop.join('\n') : '');
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
    var allBtn = h('button', {type: 'button', class: 'cbr-link', title: 'Tick every one'}, 'all');
    var noneBtn = h('button', {type: 'button', class: 'cbr-link', title: 'Untick every one (then tick the ones you want)'}, 'none');
    var shownBtn = h('button', {type: 'button', class: 'cbr-link', title: 'Tick only the ones the filter shows'}, 'only the shown');
    var box = h('div', {class: 'cbr-pick-list'});
    function visible() {
      var f = filter.value.toLowerCase();
      return list.filter(function (x) { return !f || x[0].toLowerCase().indexOf(f) >= 0; });
    }
    function render() {
      box.innerHTML = '';
      visible().forEach(function (x) {
        var cb = h('input', {type: 'checkbox'});
        cb.checked = isTicked(kind, x[0]);
        cb.addEventListener('change', function () {
          var on = {};
          list.forEach(function (y) { on[y[0]] = isTicked(kind, y[0]); });
          on[x[0]] = cb.checked;
          st[kind] = encodePick(kind, on);
          pickerLabel(kind);
          scheduleRun();
        });
        box.appendChild(h('label', {}, cb, h('span', {class: 'nm', title: x[0]}, x[0]), h('span', {class: 'n'}, String(x[1]))));
      });
    }
    filter.addEventListener('input', render);
    filter.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); shownBtn.click(); } });
    allBtn.addEventListener('click', function () { st[kind] = ''; pickerLabel(kind); render(); scheduleRun(); });
    noneBtn.addEventListener('click', function () { st[kind] = '-*'; pickerLabel(kind); render(); scheduleRun(); });
    shownBtn.addEventListener('click', function () {
      var on = {};
      visible().forEach(function (x) { on[x[0]] = true; });
      st[kind] = encodePick(kind, on);
      pickerLabel(kind); render(); scheduleRun();
    });
    pop.appendChild(filter);
    pop.appendChild(h('div', {class: 'cbr-pick-acts'}, allBtn, noneBtn, shownBtn));
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
    // the Search tab waits for words: without them it says what to do (the Browse tab lists the categories)
    if (st.view === 'search' && !st.q.trim()) { last = null; renderSearchHint(); return; }
    var my = ++runToken;
    return call('search', params(), 'searching')
      .then(function (r) {
        if (my !== runToken) return;          // a newer query has started meanwhile
        last = r; lastView = st.view;
        render();
      })
      .catch(function (e) { showError(e.message); });
  }
  function renderSearchHint() {
    $('cbr-list').innerHTML = '';
    root.querySelector('[data-pager="search"]').innerHTML = '';
    $('cbr-status').textContent = '';
    notices([]);
    var box = $('cbr-search-hint');
    box.innerHTML = '';
    box.hidden = false;
    box.appendChild(h('h2', {}, 'Search'));
    box.appendChild(h('p', {}, 'Type words above: a name, a tag, a customer, a GPU, anything in the meta or the descriptions. ' +
      'The best matches come first, with where each word was found. The repositories, the categories and the dates narrow the search.'));
    var p = h('p', {class: 'cbr-muted'}, 'Nothing typed yet - or ');
    var b = h('button', {type: 'button', class: 'cbr-link'}, 'browse the categories');
    b.addEventListener('click', function () { setView('browse'); });
    p.appendChild(b);
    p.appendChild(document.createTextNode(' instead.'));
    box.appendChild(p);
  }
  function statusLine(r) {
    var s = r.total + ' of ' + r.of + ' artifacts';
    if (r.total) s += ' · ' + (r.offset + 1) + '–' + (r.offset + r.rows.length) + ' shown';
    s += ' · sorted by ' + r.sort + (r.sort === 'relevance' ? '' : (r.dir === 'desc' ? ' ↓' : ' ↑'));
    s += ' · ' + r.ms + ' ms';
    var dsc = r.descs || {};
    if (dsc.asked) s += dsc.searched ? ' · meta and ' + num(dsc.count) + ' descriptions searched'
                                     : ' · the descriptions are not read yet: the meta alone was searched';
    if (r.catalog && r.catalog.built) s += ' · index loaded ' + r.catalog.built;
    // a server started before an engine upgrade keeps the core it loaded while its pages reload: say so
    if (r.catalog && r.catalog.stale_engine) showError('This server runs an older cMeta core than its pages (Repos.find_in_index without scope): restart it (cx app run cserver) to load the engine it was upgraded to.');
    $('cbr-status').textContent = s;
  }
  function render() {
    if (!last) return;
    statusLine(last);
    notices(last.notices);
    if (st.view === 'search') renderList();
    else if (st.view === 'browse') renderBrowse();
  }
  // what the server adds to a result: a category the query names is hidden here, an empty result on a server that hides some
  function notices(list) {
    var box = $('cbr-notices');
    if (!box) return;
    box.innerHTML = '';
    (list || []).forEach(function (t) { box.appendChild(h('div', {}, t)); });
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
    $('cbr-search-hint').hidden = true;
    last.rows.forEach(function (r) {
      var title = h('button', {type: 'button', class: 'cbr-r-title', html: hl(r.alias)});
      title.addEventListener('click', function () { window.location.href = crefUrl(r.cat, r.alias, r.uid); });
      var li = h('li', {}, title);
      if (r.name && r.name !== r.alias) li.appendChild(h('span', {class: 'cbr-r-name', html: hl(r.name)}));
      if (r.migrated_to) li.appendChild(h('span', {class: 'cbr-badge', title: 'migrated to ' + r.migrated_to}, 'migrated'));
      var when = r.updated ? 'updated ' + r.updated : (r.created ? 'created ' + r.created : '');
      li.appendChild(h('div', {class: 'cbr-r-meta'}, [r.cat, r.repo || '(registry)', when].filter(Boolean).join(' · '), rowOpen(r.uid)));
      if (r.snippet) li.appendChild(h('div', {class: 'cbr-r-snip', html: hl(r.snippet)}));
      if (r.tags && r.tags.length) {
        var tg = h('div');
        r.tags.forEach(function (t) { tg.appendChild(chip(t)); });
        li.appendChild(tg);
      }
      ol.appendChild(li);
    });
    if (!last.rows.length) {
      var unticked = ['repos', 'cats'].filter(function (k) { return pickParts(k).drop.indexOf('*') >= 0; });
      ol.appendChild(h('li', {class: 'cbr-muted'}, unticked.length
        ? 'No ' + (unticked[0] === 'repos' ? 'repository' : 'category') + ' is ticked - tick some in its picker.'
        : 'Nothing matches. Try fewer words, or clear the pickers and the dates.'));
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

  /* ------------------------------------------------------------------ Browse view: the categories, then the artifacts */
  // The index on the left: every category with how many of its artifacts the query keeps (the words, the
  // repositories and the dates - not the category picked), grouped by the first part of their names; a click opens
  // the category on the right, a second click closes it. The right side: what is here (nothing picked), or the
  // category's artifacts in a table, with the tags, years and repositories of the matches as chips to prune by.
  var FACETS = [['tag', 'Tags'], ['year', 'Created'], ['repo', 'Repositories'], ['generator', 'Made by']];
  var facetOpen = {};
  function catInfo(alias) {
    var list = (options && options.categories) || [];
    for (var i = 0; i < list.length; i++) if (list[i].alias === alias) return list[i];
    return null;
  }
  function tocGroups(counts) {
    // [{key, items: [[alias, n]]}]: dotted names grouped by their first part when two or more share it
    var byKey = {}, order = [];
    counts.forEach(function (x) {
      var k = x[0].indexOf('.') > 0 ? x[0].split('.')[0] : '';
      if (!byKey[k]) { byKey[k] = []; order.push(k); }
      byKey[k].push(x);
    });
    var out = [], rest = [];
    order.sort(function (a, b) { return a.toLowerCase() < b.toLowerCase() ? -1 : 1; }).forEach(function (k) {
      if (k && byKey[k].length > 1) out.push({key: k, items: byKey[k]});
      else rest = rest.concat(byKey[k]);
    });
    rest.sort(function (a, b) { return a[0].toLowerCase() < b[0].toLowerCase() ? -1 : 1; });
    if (rest.length) out.push({key: '', items: rest});
    return out;
  }
  function renderToc() {
    var box = $('cbr-toc-list');
    box.innerHTML = '';
    var counts = (last && last.toc) || (options && options.cats) || [];
    var f = tocFilter.toLowerCase();
    var shown = counts.filter(function (x) { return !f || x[0].toLowerCase().indexOf(f) >= 0; });
    var sel = st.cats;
    var total = 0;
    counts.forEach(function (x) { total += x[1]; });
    var all = h('button', {type: 'button', class: 'cbr-toc-all' + (sel ? '' : ' on'), title: 'Every category'},
                h('span', {class: 'nm'}, 'All categories'), h('span', {class: 'n'}, num(total)));
    all.addEventListener('click', function () { pickCategory(''); });
    box.appendChild(all);
    tocGroups(shown).forEach(function (g) {
      var gn = 0;
      g.items.forEach(function (x) { gn += x[1]; });
      var folded = !!tocFold[g.key] && !f;
      if (g.key) {
        var head = h('button', {type: 'button', class: 'cbr-toc-group' + (folded ? ' folded' : ''), 'aria-expanded': folded ? 'false' : 'true'},
                     h('span', {class: 'tri'}, folded ? '▸' : '▾'), h('span', {class: 'nm'}, g.key + '.*'),
                     h('span', {class: 'n', title: g.items.length + ' categories, ' + num(gn) + ' artifacts'}, g.items.length + ' · ' + num(gn)));
        head.addEventListener('click', function () { tocFold[g.key] = !tocFold[g.key]; renderToc(); });
        box.appendChild(head);
        if (folded && !(sel && sel.indexOf(g.key + '.') === 0)) return;
      }
      var ul = h('div', {class: 'cbr-toc-items' + (g.key ? ' in' : '')});
      g.items.forEach(function (x) {
        var info = catInfo(x[0]);
        var label = g.key ? x[0].slice(g.key.length + 1) : x[0];
        var b = h('button', {type: 'button', class: 'cbr-toc-item' + (sel === x[0] ? ' on' : ''),
                             title: x[0] + (info && info.name ? ' - ' + info.name : '')},
                  h('span', {class: 'nm'}, label), h('span', {class: 'n'}, num(x[1])));
        b.addEventListener('click', function () { pickCategory(sel === x[0] ? '' : x[0]); });
        ul.appendChild(b);
      });
      box.appendChild(ul);
    });
    if (!shown.length) box.appendChild(h('div', {class: 'cbr-muted', style: 'padding:6px'}, f ? 'No category matches the filter.' : 'No category to show.'));
  }
  function pickCategory(alias) {
    st.cats = alias || '';
    st.sort = '';
    st.dir = '';
    pickerLabel('cats');
    if (options) buildPicker('cats');
    if (st.view !== 'browse') setView('browse'); else run();
  }
  function renderCatHead() {
    var box = $('cbr-cat-head');
    box.innerHTML = '';
    var sel = st.cats;
    var words = st.q.trim();
    if (!sel && !words) {
      // nothing picked: what this server holds and how it is organised
      var o = options || {repos: [], cats: [], total: 0};
      var intro = h('div', {class: 'cbr-intro'});
      intro.appendChild(h('h2', {}, 'What is here'));
      intro.appendChild(h('p', {}, num(o.total) + ' artifacts in ' + o.cats.length + ' categories of ' + o.repos.length +
        ' repositories' + (last && last.total !== o.total ? ' - ' + num(last.total) + ' kept by the repositories and dates picked' : '') + '.'));
      intro.appendChild(h('p', {}, 'A ', h('b', {}, 'repository'), ' is a folder (a git repository, a shared folder) that holds ',
        h('b', {}, 'categories'), ' - one kind of thing each: a customer, a deal, a GPU, a data centre, a task, a report. ',
        'A category holds ', h('b', {}, 'artifacts'), ': one folder per thing, with its meta (', h('code', {}, '_cmeta'), ': who, when, tags), ',
        'its description (', h('code', {}, '_desc'), ': the facts and the connections to other artifacts) and its files - dated records live in ',
        h('code', {}, 'ck/YYYYMMDD/'), ', one folder per day the facts were observed, so nothing is ever overwritten. ',
        'Every artifact has an address, its ', h('b', {}, 'cRef'), ' (', h('code', {}, 'category::alias,UID'), '), that any page, document or tool can point at.'));
      intro.appendChild(h('p', {class: 'cbr-muted'}, 'Pick a category on the left to see its artifacts, type words above to search across them, ' +
        'or open the Graph tab to see how they connect. Click an artifact for its page: its text, its connections, its files.'));
      if (o.repos && o.repos.length) {
        var rp = h('div', {class: 'cbr-intro-repos'}, h('span', {class: 'cbr-muted'}, 'Repositories: '));
        o.repos.forEach(function (x) {
          var alone = picked('repos').length === 1 && picked('repos')[0] === x[0];
          var c = h('button', {type: 'button', class: 'cbr-chip' + (alone ? ' on' : (isTicked('repos', x[0]) ? '' : ' off')),
                               title: num(x[1]) + ' artifacts - click to keep this repository alone, again for the usual ones'},
                    x[0] + ' (' + num(x[1]) + ')');
          c.addEventListener('click', function () {
            st.repos = alone ? DEFAULT_PICK.repos : x[0];
            pickerLabel('repos'); if (options) buildPicker('repos'); run();
          });
          rp.appendChild(c);
        });
        intro.appendChild(rp);
      }
      box.appendChild(intro);
      return;
    }
    var head = h('div', {class: 'cbr-cat-title'});
    if (sel) {
      var info = catInfo(sel);
      head.appendChild(h('h2', {}, sel));
      if (info && (info.name || info.desc)) {
        head.appendChild(h('p', {class: 'cbr-cat-desc'}, (info.name ? info.name : '') + (info.name && info.desc ? ' - ' : '') + (info.desc || '')));
      }
      var line = h('p', {class: 'cbr-muted'}, num(last ? last.total : 0) + ' artifact' + (last && last.total === 1 ? '' : 's') +
        (words ? ' matching "' + words + '"' : '') + (info && info.repos ? ' in ' + info.repos.map(function (x) { return x[0]; }).join(', ') : '') + ' · ');
      if (info && info.uid) {
        line.appendChild(h('a', {href: crefUrl('category', sel, info.uid), title: 'The category itself: its definition, its commands'}, 'the category\'s page'));
        line.appendChild(document.createTextNode(' · '));
      }
      var gl = h('a', {href: pageUrl({view: 'graph', cats: sel, q: st.q, repos: st.repos}), title: 'These artifacts drawn with their connections'}, 'graph');
      line.appendChild(gl);
      line.appendChild(document.createTextNode(' · '));
      var x = h('button', {type: 'button', class: 'cbr-link'}, 'all categories');
      x.addEventListener('click', function () { pickCategory(''); });
      line.appendChild(x);
      if (CFG.edit) {                            // a viewer who may write: a new artifact of this category
        line.appendChild(document.createTextNode(' · '));
        var nb = h('button', {type: 'button', class: 'cbr-mini', title: 'A new artifact of this category: its name, its tags, its repository'}, '+ new ' + sel);
        nb.addEventListener('click', function () { newArtifactForm(head, sel, {repo: lastRepo(), tags: ''}); });
        line.appendChild(nb);
      }
      head.appendChild(line);
    } else {
      head.appendChild(h('h2', {}, 'Matching "' + words + '"'));
      head.appendChild(h('p', {class: 'cbr-muted'}, num(last ? last.total : 0) + ' artifacts across the categories on the left - pick one to narrow.'));
    }
    box.appendChild(head);
  }
  // A new artifact (2026-11-03): one small form - the name, the tags, the repository, a tick for today's date in
  // front of the name (-dt; on by default for a category that names its artifacts by their date, 2026-11-05) - made
  // by the category's own "add" on the server, then its page opens. The repositories offered are the ones this
  // viewer may write to (CFG.edit: everything, or the patterns of the host's grant).
  function globMatch(s, p) {
    return new RegExp('^' + p.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.') + '$').test(s);
  }
  function writableRepos() {
    var all = (options && options.repos ? options.repos : []).map(function (x) { return x[0]; }).filter(function (r) { return r !== '(registry)'; });
    if (CFG.edit === true) return all;
    var pats = Array.isArray(CFG.edit) ? CFG.edit : [];
    return all.filter(function (r) { return pats.some(function (p) { return globMatch(r.toLowerCase(), String(p).toLowerCase()); }); });
  }
  function lastRepo() { try { return localStorage.getItem('cbr-new-repo') || ''; } catch (e) { return ''; } }
  function newArtifactForm(anchor, cat, preset) {
    var old = root.querySelector('.cbr-newform');
    if (old) { old.remove(); return; }
    var f = h('form', {class: 'cbr-newform'});
    var name = h('input', {type: 'text', required: 'required', autocomplete: 'off', placeholder: 'the name'});
    var tags = h('input', {type: 'text', autocomplete: 'off', placeholder: 'tags, comma-separated'});
    tags.value = preset.tags || '';
    var dated = ((options && options.categories) || []).some(function (c) { return c.alias === cat && c.dated; });
    var dt = h('input', {type: 'checkbox'});
    dt.checked = dated;
    var repo = h('select', {});
    var repos = writableRepos();
    repos.forEach(function (r) {
      var o = h('option', {value: r}, r);
      if (r === preset.repo) o.selected = true;
      repo.appendChild(o);
    });
    var msg = h('span', {class: 'cbr-emsg'});
    var ok = h('button', {type: 'submit', class: 'cbr-btn'}, 'Create');
    var no = h('button', {type: 'button', class: 'cbr-copy'}, 'cancel');
    no.addEventListener('click', function () { f.remove(); });
    f.appendChild(h('div', {class: 'cbr-newform-title'}, 'New ' + cat));
    f.appendChild(h('label', {}, 'Name', name));
    f.appendChild(h('label', {}, 'Tags', tags));
    f.appendChild(h('label', {}, 'Repository', repo));
    f.appendChild(h('label', {class: 'cbr-newform-dt'}, dt, ' today\'s date in front of the name (-dt)'));
    f.appendChild(h('div', {class: 'cbr-newform-acts'}, ok, no, msg));
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      if (!repos.length) { msg.textContent = 'no repository you may write to is shown here'; return; }
      msg.textContent = '';
      ok.disabled = true;
      call('create', {cat: cat, repo: repo.value, alias: name.value.trim(), tags: tags.value, dt: dt.checked ? 1 : 0}, 'creating ' + name.value.trim()).then(function (r) {
        try { localStorage.setItem('cbr-new-repo', r.repo); } catch (x) {}
        window.location.href = crefUrl(r.cat, r.created, r.uid);
      }).catch(function (err) { ok.disabled = false; msg.textContent = err.message; });
    });
    anchor.appendChild(f);
    name.focus();
  }
  function renderBrowse() {
    renderToc();
    renderCatHead();
    var tb = $('cbr-table').querySelector('tbody');
    tb.innerHTML = '';
    var wrap = root.querySelector('.cbr-tablewrap');
    var showTable = !!(st.cats || st.q.trim());
    wrap.hidden = !showTable;
    $('cbr-facets').hidden = !showTable;
    if (!showTable) return;
    $('cbr-table').classList.toggle('one-cat', !!st.cats);
    COLS.forEach(function (c) { $('cbr-table').classList.toggle('no-' + c, !colOn(c)); });
    last.rows.forEach(function (r) {
      var a = h('td', {class: 'alias', html: hl(r.alias) + (r.name && r.name !== r.alias ? '<span class="nm">' + hl(r.name) + '</span>' : '') +
                       (r.migrated_to ? '<span class="cbr-badge">migrated</span>' : '')});
      var tags = h('td', {class: 'tags'});
      (r.tags || []).slice(0, 6).forEach(function (t) { tags.appendChild(chip(t)); });
      var tr = h('tr', {}, a, h('td', {class: 'cat'}, r.cat), h('td', {class: 'repo'}, r.repo || '(registry)'), tags,
                 h('td', {class: 'when'}, r.created), h('td', {class: 'when updated'}, r.updated), h('td', {class: 'acts'}, rowOpen(r.uid)));
      tr.addEventListener('click', function () { window.location.href = crefUrl(r.cat, r.alias, r.uid); });
      tb.appendChild(tr);
    });
    if (!last.rows.length) tb.appendChild(h('tr', {}, h('td', {colspan: '7', class: 'cbr-muted'}, 'Nothing matches.')));
    $('cbr-table').querySelectorAll('th[data-sort]').forEach(function (th) {
      var key = th.getAttribute('data-sort');
      var dated = key === 'alias' && last.sort === 'dated';     // the Artifact column's third order
      var on = key === last.sort || dated;
      th.classList.toggle('sorted', on);
      th.title = key === 'alias' ? 'Click: by name A to Z, Z to A, then the names without a date first and the dated ones newest first' : '';
      th.textContent = th.getAttribute('data-label') + (dated ? ' · undated, then newest' : (on ? (last.dir === 'desc' ? ' ▾' : ' ▴') : ''));
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
      if (f[0] === 'repo' && vals.length < 2) return;
      if (!vals.length) return;
      var sec = h('div', {class: 'cbr-facet'}, h('span', {class: 'cbr-facet-name'}, f[1] + ':'));
      var lim = facetOpen[f[0]] ? vals.length : 8;
      vals.slice(0, lim).forEach(function (x) {
        var b = h('button', {type: 'button', class: 'cbr-chip', title: f[1] + ' ' + x[0] + ': ' + num(x[1]) + ' - click to narrow'},
                  x[0] + ' ', h('span', {class: 'n'}, String(x[1])));
        b.addEventListener('click', function () { applyFacet(f[0], x[0]); });
        sec.appendChild(b);
      });
      if (vals.length > 8) {
        var more = h('button', {type: 'button', class: 'cbr-link more'}, facetOpen[f[0]] ? 'fewer' : '+ ' + (vals.length - 8) + ' more');
        more.addEventListener('click', function () { facetOpen[f[0]] = !facetOpen[f[0]]; renderFacets(); });
        sec.appendChild(more);
      }
      box.appendChild(sec);
    });
  }
  function applyFacet(kind, v) {
    if (kind === 'cat') {
      pickCategory(v);
    } else if (kind === 'repo') {
      st.repos = v;
      pickerLabel('repos');
      if (options) buildPicker('repos');
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
  var detailFlash = null;    // what a change made in the panel said, shown when the panel is drawn again (2026-11-10)
  function openDetail(uid, file) {
    if (!uid) return;
    st.uid = uid;
    st.file = file || '';
    var my = ++detailToken;
    call('artifact', {uid: uid}, 'reading the artifact').then(function (d) {
      if (my !== detailToken) return;
      st.cref = crefOf(d.row.cat_uid, d.row.uid);   // the address names it once its category is known
      syncUrl();
      subtitle({index: d.index});
      var box = $('cbr-detail');
      box.innerHTML = '';
      var close = h('button', {type: 'button', class: 'cbr-d-close', title: 'Close (Esc)'}, '×');
      close.addEventListener('click', closeDetail);
      var full = h('a', {class: 'cbr-btn cbr-d-full', href: crefUrl(d.row.cat, d.row.alias, d.row.uid), title: 'The page of this artifact'}, 'Open full view');
      box.appendChild(h('div', {class: 'cbr-d-head'}, h('h2', {}, d.row.alias), full, close));
      if (detailFlash && detailFlash.uid === uid) box.appendChild(h('div', {class: 'cbr-d-flash'}, detailFlash.text));
      detailFlash = null;
      if (d.row.name && d.row.name !== d.row.alias) box.appendChild(h('div', {class: 'cbr-d-name'}, d.row.name));
      box.appendChild(cmdLine(d.cref));
      var facts = h('table', {class: 'cbr-d-facts'});
      var catLink = h('a', {href: pageUrl({view: 'browse', cats: d.row.cat}), title: 'Every artifact of this category'}, d.row.cat);
      var repoLink = d.row.repo ? h('a', {href: pageUrl({view: 'browse', repos: d.row.repo}), title: 'Every artifact of this repository'}, d.row.repo)
                                : document.createTextNode('(registry)');
      var origin = d.origin || {};
      var originCell = origin.url ? h('a', {href: origin.url, target: '_blank', rel: 'noopener', title: origin.url},
                                      (origin.kind === 'github' ? 'GitHub: ' : '') + (origin.label || origin.url))
                                  : document.createTextNode(origin.label || 'none');
      [['Category', catLink], ['Repository', repoLink], ['Origin', originCell], ['UID', d.row.uid],
       ['Created', d.row.created], ['Updated', d.row.updated], ['Path', d.path || '']].forEach(function (x) {
        if (x[1]) facts.appendChild(h('tr', {}, h('td', {}, x[0]), h('td', {}, x[1])));
      });
      box.appendChild(facts);
      if (CFG.open && OPEN.some(function (w) { return CFG.open[w[0]]; })) box.appendChild(openBar(d.row.uid));
      if (d.row.migrated_to) {
        var m = h('p', {}, 'Migrated to ');
        if (d.migrated_to_uid) {
          var go = h('a', {href: '#'}, d.row.migrated_to);
          go.addEventListener('click', function (e) { e.preventDefault(); openDetail(d.migrated_to_uid); });
          m.appendChild(go);
        } else m.appendChild(document.createTextNode(d.row.migrated_to));
        box.appendChild(m);
      }
      // the tags (2026-11-10: edited here too - the chips, "edit tags" opens a field with all of them in order)
      var canList = !!d.edit;                       // the lists and the tags: a viewer who may write to the artifact
      if ((d.row.tags && d.row.tags.length) || canList) box.appendChild(tagsRow(d));
      box.appendChild(focusBar(crefOf(d.row.cat_uid, d.row.uid)));
      // the texts (2026-11-10): README.md, _info.md, the file the view names - as the artifact page renders them;
      // edited in place by a viewer who may save files here (the user: "edit Readme/_note in the sub-view too"), a
      // missing README.md or _info.md made the same way
      var canText = !!d.edit && !!d.files;          // the texts are saved through the file browser, under its rules
      var texts = d.texts || [];
      if (texts.length || canText) {
        box.appendChild(h('h3', {}, 'Text'));
        texts.forEach(function (t) {
          var tx = h('div', {class: 'cbr-d-text'});
          tx.innerHTML = t.html;
          var wrap = h('div', {class: 'cbr-d-tblock', 'data-rel': t.rel}, h('div', {class: 'cbr-d-tname'}, t.rel), tx);
          var bar = h('div', {class: 'cbr-d-tbar'});
          var more = h('button', {type: 'button', class: 'cbr-mini cbr-d-more'}, 'more');
          more.addEventListener('click', function () { var open = wrap.classList.toggle('open'); more.textContent = open ? 'less' : 'more'; });
          bar.appendChild(more);
          if (canText) {
            var eb = h('button', {type: 'button', class: 'cbr-mini cbr-d-tedit', title: 'Edit ' + t.rel + ' here (Ctrl+S saves)'}, 'edit');
            eb.addEventListener('click', function () { textEdit(d, t.rel, wrap, false); });
            bar.appendChild(eb);
          }
          wrap.appendChild(bar);
          box.appendChild(wrap);
          // "more" only when the text is cut (measured once the panel is shown)
          requestAnimationFrame(function () { if (tx.scrollHeight <= tx.clientHeight + 4) more.hidden = true; });
        });
        if (canText) {
          var have = texts.map(function (t) { return String(t.rel).toLowerCase(); });
          var row = h('div', {class: 'cbr-d-tnew'});
          TEXT_NEW.forEach(function (n) {
            if (n.names.some(function (x) { return have.indexOf(x.toLowerCase()) >= 0; })) return;
            var nb = h('button', {type: 'button', class: 'cbr-mini', title: n.hint}, '+ ' + n.names[0]);
            nb.addEventListener('click', function () {
              var ex = box.querySelector('.cbr-d-tblock.cbr-new[data-rel="' + n.names[0] + '"]');
              if (ex) { var ta = ex.querySelector('textarea'); if (ta) ta.focus(); return; }
              var blk = h('div', {class: 'cbr-d-tblock cbr-new', 'data-rel': n.names[0]}, h('div', {class: 'cbr-d-tname'}, n.names[0]));
              box.insertBefore(blk, row);
              textEdit(d, n.names[0], blk, true);
            });
            row.appendChild(nb);
          });
          if (row.childNodes.length) box.appendChild(row);
        }
      }
      // the connections apart (2026-11-10): with (both name each other), to (this _desc only), from (the other's only);
      // the AI uses; each with a picker and x where this viewer may write
      var links = d.connections || [];
      var withL = links.filter(function (c) { return c.mutual; }), toL = links.filter(function (c) { return !c.mutual; });
      var fromL = (d.incoming || []).filter(function (c) { return !c.mutual; });
      var nFrom = (d.incoming_total || (d.incoming || []).length) - ((d.incoming || []).length - fromL.length);
      editList(box, d, 'Connected with', withL, {key: 'connections', both: true, hint: 'connect with: type a name or a word, pick one, ";" for the next - both name each other'});
      editList(box, d, 'Connected to', toL, {key: 'connections', both: false, hint: 'connect to: type a name or a word, pick one - this artifact\'s _desc only'});
      linkList(box, 'Uses', d.uses, function (c) { return c.ref; });
      editList(box, d, 'AI uses (reads the memory and skills of)', d.ai_uses || [], {key: 'ai_uses', both: false, hint: 'an AI context: its short name, a name or a cRef'});
      if (d.index && d.index.ready) {
        linkList(box, 'Connected from', fromL, null, nFrom);
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
        if (st.file) listFiles(d.row.uid, fbox, fbtn, st.file);
      }
      box.appendChild(h('h3', {}, 'Commands'));
      (d.commands || []).forEach(function (c) { box.appendChild(cmdLine(c)); });
      box.appendChild(h('h3', {}, 'Meta (_cmeta)'));
      box.appendChild(codePre(JSON.stringify(d.meta, null, 2), '_cmeta.json'));
      var canEdit = d.edit && d.files;             // the editor saves through the file browser
      if (canEdit && d.meta_file) box.appendChild(editRow(d.row.uid, d.meta_file, fbox, fbtn, false));
      if (d.desc) {
        box.appendChild(h('h3', {}, 'Description (' + d.desc_file + ')'));
        box.appendChild(codePre(JSON.stringify(d.desc, null, 2), '_desc.json'));
        if (canEdit && d.desc_file) box.appendChild(editRow(d.row.uid, d.desc_file, fbox, fbtn, false));
      } else if (canEdit) {
        box.appendChild(editRow(d.row.uid, '_desc.yaml', fbox, fbtn, true));
      }
      box.hidden = false;
      box.scrollTop = 0;
    }).catch(function (e) { showError(e.message); });
  }
  function closeDetail() {
    detailToken++;
    $('cbr-detail').hidden = true;
    st.uid = st.cref = st.file = '';
    syncUrl();
  }
  // Open the folder on this machine (a browser on the server's own machine only): file manager, shell, Far
  var OPEN = [['folder', 'Open folder', 'Open this folder in the file manager'],
              ['shell', 'Shell', 'A terminal in this folder'],
              ['far', 'Far', 'Far Manager in this folder']];
  // The same buttons on every row of a list (2026-11-03): short, after the artifact; a row's click opens the
  // artifact, a button's does not. What happened shows in a notice that fades.
  function rowOpen(uid) {
    var box = h('span', {class: 'cbr-row-open'});
    OPEN.forEach(function (w) {
      if (!CFG.open || !CFG.open[w[0]]) return;
      var b = h('button', {type: 'button', class: 'cbr-mini', title: w[2]}, w[0] === 'folder' ? 'Folder' : w[1]);
      b.addEventListener('click', function (e) {
        e.stopPropagation();
        call('open', {uid: uid, what: w[0]}, null)
          .then(function () { toast((w[0] === 'folder' ? 'The folder' : w[1]) + ' opened on this machine'); })
          .catch(function (err) { toast(err.message, true); });
      });
      box.appendChild(b);
    });
    return box;
  }
  // The tags and updated columns of the Browse list: off by default, so that the list stays compact; the boxes of its
  // header turn them on, and the browser remembers them
  var COLS = ['tags', 'updated'];
  function colOn(col) { try { return localStorage.getItem('cbr-browse-' + col) === '1'; } catch (e) { return false; } }
  var toastTimer = null;
  function toast(text, bad) {
    var t = $('cbr-toast');
    if (!t) { t = h('div', {id: 'cbr-toast', class: 'cbr-toast', role: 'status', 'aria-live': 'polite'}); root.appendChild(t); }
    t.textContent = text;
    t.className = 'cbr-toast show' + (bad ? ' bad' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.className = 'cbr-toast' + (bad ? ' bad' : ''); }, bad ? 6000 : 2500);
  }
  function openBar(uid) {
    var bar = h('div', {class: 'cbr-d-open'});
    var msg = h('span', {class: 'msg', 'aria-live': 'polite'});
    OPEN.forEach(function (w) {
      if (!CFG.open[w[0]]) return;
      var b = h('button', {type: 'button', class: 'cbr-btn', title: w[2]}, w[1]);
      b.addEventListener('click', function () {
        msg.className = 'msg';
        msg.textContent = 'opening...';
        call('open', {uid: uid, what: w[0]}, null)
          .then(function () { msg.textContent = (w[0] === 'folder' ? 'the folder' : w[1]) + ' opened on this machine'; })
          .catch(function (e) { msg.className = 'msg bad'; msg.textContent = e.message; });
      });
      bar.appendChild(b);
    });
    bar.appendChild(msg);
    return bar;
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
  function focusBar(ref) {
    var sel = depthSelect(st.depth);
    var b = h('button', {type: 'button', class: 'cbr-btn cbr-primary'}, 'Focus the graph here');
    b.addEventListener('click', function () { focusOn(ref, sel.value); });
    return h('div', {class: 'cbr-d-graph'}, b, h('label', {}, 'depth ', sel));
  }
  // ref: <category UID>::<artifact UID> (the address carries it as focus=)
  function focusOn(ref, depth) {
    st.focus = ref;
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

  // A list of the detail that a viewer who may write changes in place (2026-11-10): x removes an entry (a connection
  // from both sides, where this viewer may write there), the picker adds (cmetaPicker of picker.js: searched as one
  // types, chips, ";" for the next; "with" written on both sides); the panel is read again after a change
  function editList(box, d, title, items, opts) {
    var can = !!d.edit && !!window.cmetaPicker;
    if (!items.length && !can) return;
    box.appendChild(h('h3', {}, title + (items.length ? ' (' + num(items.length) + ')' : '')));
    var ul = h('ul', {class: 'cbr-links'});
    items.forEach(function (c) {
      var li = h('li');
      if (c.found === false) li.appendChild(h('span', {class: 'missing', title: 'not shown by this server'}, c.alias || c.cref));
      else {
        var a = h('a', {href: '#', title: c.cref || c.alias}, c.alias);
        a.addEventListener('click', function (e) { e.preventDefault(); openDetail(c.uid); });
        li.appendChild(a);
        li.appendChild(h('span', {class: 'cbr-muted'}, '  ' + (c.cat || '')));
      }
      if (can && c.cref && !c.meta) {
        var x = h('button', {type: 'button', class: 'cbr-mini cbr-lx', title: opts.key === 'connections' ? 'Remove this connection (from the other artifact too, where it names this one)' : 'Remove it from the AI uses'}, '×');
        x.addEventListener('click', function () {
          if (!confirm('Remove ' + c.alias + ' from "' + title + '"?')) return;
          x.disabled = true;
          call('link', {uid: d.row.uid, key: opts.key, remove: c.cref}, 'removing')
            .then(function (r) { note(r); openDetail(d.row.uid); })
            .catch(function (e) { x.disabled = false; showError(e.message); });
        });
        li.appendChild(x);
      }
      ul.appendChild(li);
    });
    if (!items.length) ul.appendChild(h('li', {class: 'cbr-muted'}, 'none yet'));
    box.appendChild(ul);
    if (!can) return;
    var f = h('form', {class: 'cbr-ladd', autocomplete: 'off'}, h('input', {type: 'text', placeholder: opts.hint, 'aria-label': 'Add to ' + title, spellcheck: 'false'}),
              h('button', {type: 'submit', class: 'cbr-mini'}, 'Add'));
    var msg = h('span', {class: 'cbr-muted cbr-lmsg'});
    f.appendChild(msg);
    box.appendChild(f);
    window.cmetaPicker(f, {api: function (action, p) { return call(action, p); }, self: d.row.uid, key: opts.key, submit: function (all) {
      msg.textContent = '';
      return call('link', {uid: d.row.uid, key: opts.key, add: all.join(';'), both: opts.both ? '1' : ''}, 'connecting')
        .then(function (r) { if (!(r.changes || []).length) { msg.textContent = ((r.warnings || []).join('; ')) || 'nothing changed'; return true; } note(r); openDetail(d.row.uid); })
        .catch(function (e) { msg.textContent = e.message; return true; });
    }});
    function note(r) {
      var l = (r.changes || []).map(function (c) { return c.charAt(0) === '+' ? 'added ' + c.slice(2) : c.charAt(0) === '-' ? 'removed ' + c.slice(2) : c; }).concat(r.warnings || []);
      if (l.length) detailFlash = {uid: d.row.uid, text: l.join('; ')};
    }
  }
  // The texts a panel offers to make when they are missing (as the artifact page does): the names each may have, the
  // first is the one made
  var TEXT_NEW = [{names: ['README.md', 'readme.md'], hint: 'A README: what this artifact is - the page shows it first'},
                  {names: ['_info.md'], hint: 'A note of your own, shown after the README'}];
  // A text of the detail edited where it is read (2026-11-10): the block's rendering gives way to the editor (the
  // file browser's: the text with the fingerprint it was read with, Ctrl+S saves), a missing text starts empty; after
  // a save the panel is drawn again with the new text, cancel puts the rendering back (or takes a new block away)
  function textEdit(d, rel, block, isNew) {
    if (block.querySelector('.cbr-editor')) return;
    var kids = Array.prototype.slice.call(block.children);
    var view = h('div', {class: 'cbr-d-tedit'});
    function start(j) {
      kids.forEach(function (k) { k.hidden = true; });
      block.appendChild(view);
      editFile(d.row.uid, j, view, function (r) {
        detailFlash = {uid: d.row.uid, text: (r.created ? 'made ' : 'saved ') + rel + ((r.warnings || []).length ? '; ' + r.warnings.join('; ') : '')};
        openDetail(d.row.uid);
      }, function () {
        view.remove();
        if (isNew) block.remove(); else kids.forEach(function (k) { k.hidden = false; });
      });
      view.scrollIntoView({block: 'nearest'});
    }
    if (isNew) { start({rel: rel, text: '', stamp: ''}); return; }
    call('file', {uid: d.row.uid, rel: rel}, 'reading ' + rel).then(function (j) {
      if (j.kind === 'text' && j.editable && j.stamp) start(j);
      else toast(rel + ': ' + (j.truncated ? 'too large to edit here' : 'not editable here'), true);
    }).catch(function (e) { toast(e.message, true); });
  }
  // the tags of the detail (2026-11-10): the chips, and for a viewer who may write "edit tags" - a field with all of
  // them in order (commas or spaces between them: add, remove, reorder), Save through the tags action
  function tagsRow(d) {
    var tg = h('div', {class: 'cbr-d-tags'});
    (d.row.tags || []).forEach(function (t) { tg.appendChild(chip(t)); });
    if (!d.edit) return tg;
    var eb = h('button', {type: 'button', class: 'cbr-mini cbr-d-tags-edit', title: 'Add, remove or reorder the tags'}, (d.row.tags || []).length ? 'edit tags' : '+ tags');
    eb.addEventListener('click', function () {
      if (tg.querySelector('form')) return;
      var inp = h('input', {type: 'text', 'aria-label': 'The tags', spellcheck: 'false', placeholder: 'the tags, in order - commas or spaces between them'});
      inp.value = (d.row.tags || []).join(', ');
      var f = h('form', {class: 'cbr-ladd', autocomplete: 'off'}, inp, h('button', {type: 'submit', class: 'cbr-mini'}, 'Save'));
      var cn = h('button', {type: 'button', class: 'cbr-mini'}, 'cancel'), msg = h('span', {class: 'cbr-muted cbr-lmsg'});
      cn.addEventListener('click', function () { f.remove(); eb.hidden = false; });
      f.appendChild(cn); f.appendChild(msg);
      f.addEventListener('submit', function (e) {
        e.preventDefault();
        call('tags', {uid: d.row.uid, tags: inp.value}, 'saving the tags')
          .then(function (r) { if (!r.changed) { msg.textContent = 'nothing changed'; return; } detailFlash = {uid: d.row.uid, text: 'tags: ' + ((r.tags || []).join(', ') || 'none')}; openDetail(d.row.uid); })
          .catch(function (er) { msg.textContent = er.message; });
      });
      tg.appendChild(f); eb.hidden = true; inp.focus();
    });
    tg.appendChild(eb);
    return tg;
  }

  /* ------------------------------------------------------------------ the files of one artifact */
  var blobUrl = null;
  // An edit button under a viewer of the detail (the meta, the description): the editor opens on that file in
  // the files box (listed first when needed); a new _desc.yaml starts from the template
  function editRow(uid, rel, fbox, fbtn, isNew) {
    var b = h('button', {type: 'button', class: 'cbr-mini', title: (isNew ? 'Create ' : 'Edit ') + rel + ' here'},
              (isNew ? '+ ' : 'edit ') + rel);
    b.addEventListener('click', function () { openEditor(uid, rel, fbox, fbtn, isNew); });
    return h('p', {class: 'cbr-edit-row'}, b);
  }
  function openEditor(uid, rel, fbox, fbtn, isNew) {
    var go = function () {
      var view = fbox.querySelector('.cbr-fview');
      if (!view) return;
      if (isNew) editFile(uid, {rel: rel, text: '', stamp: ''}, view);
      else openFile(uid, rel, view, true);
      view.scrollIntoView({block: 'nearest'});
    };
    if (fbox.getAttribute('data-loaded')) { fbox.hidden = false; fbtn.textContent = 'Hide the files'; go(); }
    else listFiles(uid, fbox, fbtn, null, go);
  }
  // delete a file or an empty folder: the person is asked first; the list is read again after
  function delButton(uid, rel, what, box, btn) {
    var x = h('button', {type: 'button', class: 'cbr-mini cbr-del', title: 'Delete this ' + what}, '×');
    x.addEventListener('click', function (e) {
      e.stopPropagation();
      if (!window.confirm('Delete the ' + what + ' ' + rel + '? This cannot be undone here.')) return;
      call('delete', {uid: uid, rel: rel}, 'deleting ' + rel).then(function (r) { toast('deleted ' + r.deleted); reloadFiles(uid, box, btn); })
        .catch(function (err) { toast(err.message, true); });
    });
    return x;
  }
  function reloadFiles(uid, box, btn, want) {
    box.removeAttribute('data-loaded');
    listFiles(uid, box, btn, want);
  }
  function listFiles(uid, box, btn, want, after) {
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
      if (j.edit) {                              // a new text file (made when saved), a new folder
        var tb = h('p', {class: 'cbr-edit-row'});
        var nf = h('button', {type: 'button', class: 'cbr-mini', title: 'A new text file in this artifact: the editor opens, the file is made when you save'}, '+ file');
        nf.addEventListener('click', function () {
          var n = window.prompt('The name of the new file - a path inside the artifact, a text name (notes.md, files/plan.txt):', '');
          if (n && n.trim()) editFile(uid, {rel: n.trim(), text: '', stamp: ''}, view);
        });
        var nd = h('button', {type: 'button', class: 'cbr-mini', title: 'A new folder in this artifact'}, '+ folder');
        nd.addEventListener('click', function () {
          var n = window.prompt('The name of the new folder - a path inside the artifact:', '');
          if (n && n.trim()) call('mkdir', {uid: uid, rel: n.trim()}, 'making ' + n).then(function (r) { toast('made ' + r.made); reloadFiles(uid, box, btn); })
            .catch(function (e) { toast(e.message, true); });
        });
        tb.appendChild(nf);
        tb.appendChild(nd);
        box.appendChild(tb);
      }
      j.files.forEach(function (f) {
        var li = h('li', {title: f.mtime}, h('span', {class: 'nm'}, f.rel), h('span', {class: 'n'}, fmtSize(f.size)));
        li.addEventListener('click', function () {
          ul.querySelectorAll('li.on').forEach(function (x) { x.classList.remove('on'); });
          li.classList.add('on');
          st.file = f.rel;
          syncUrl();
          openFile(uid, f.rel, view);
        });
        if (j.edit && !/^_(cmeta|desc)\./i.test(f.rel)) li.appendChild(delButton(uid, f.rel, 'file', box, btn));
        if (want && f.rel === want) li.classList.add('on');
        ul.appendChild(li);
      });
      // the empty folders (no file, no folder inside): shown so that they can be deleted
      (j.dirs || []).forEach(function (d) {
        var under = function (x) { return x.indexOf(d + '/') === 0; };
        if (j.files.some(function (f) { return under(f.rel); }) || j.dirs.some(under)) return;
        var li = h('li', {class: 'dir'}, h('span', {class: 'nm'}, d + '/'), h('span', {class: 'n'}, 'empty'));
        if (j.edit) li.appendChild(delButton(uid, d, 'folder', box, btn));
        ul.appendChild(li);
      });
      box.appendChild(ul);
      (j.can_add || []).forEach(function (name) {   // a file the editor may create here (none of that name yet)
        var add = h('button', {type: 'button', class: 'cbr-mini', title: 'Create ' + name + ' in this artifact'}, '+ ' + name);
        add.addEventListener('click', function () { editFile(uid, {rel: name, text: '', stamp: ''}, view); });
        box.appendChild(add);
      });
      box.appendChild(view);
      if (want) openFile(uid, want, view);     // a link or the URL named the file: open it (also one past the list)
      if (after) after();
    }).catch(function (e) { box.hidden = false; box.textContent = e.message; });
  }
  function openFile(uid, rel, view, edit) {
    call('file', {uid: uid, rel: rel}, 'reading ' + rel).then(function (j) {
      view.innerHTML = '';
      if (blobUrl) { URL.revokeObjectURL(blobUrl); blobUrl = null; }
      var close = h('button', {type: 'button', class: 'cbr-copy'}, 'close');
      close.addEventListener('click', function () { view.innerHTML = ''; st.file = ''; syncUrl(); });
      var head = h('div', {class: 'cbr-fhead'}, h('b', {}, j.rel), ' · ' + fmtSize(j.size) +
        (j.truncated ? ' · the first 512 KB' : '') + ' ', close);
      if (j.kind === 'text' && j.editable) {     // the server says this viewer may save it here
        var edit = h('button', {type: 'button', class: 'cbr-copy', title: 'Edit this file here (Ctrl+S saves)'}, 'edit');
        edit.addEventListener('click', function () { editFile(uid, j, view); });
        head.insertBefore(edit, close);
      }
      view.appendChild(head);
      if (j.kind === 'text') {
        view.appendChild(codePre(j.text, j.rel));
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
      if (edit && j.kind === 'text' && j.editable) editFile(uid, j, view);   // asked to edit it at once
    }).catch(function (e) { view.textContent = e.message; });
  }
  // The editor (2026-11-03): a plain text box for a text file this viewer may save - a browser on the server's
  // own machine, or a reader the host lets write here. The server checks YAML and JSON, keeps the identity of a
  // _cmeta (and reindexes it), and refuses a file changed meanwhile (the fingerprint it gave with the text).
  var DESC_TEMPLATE = '# What this artifact declares: links to other artifacts (connections), what it runs (uses),\n' +
                      '# whose memory its AI sessions read (ai_uses), and any facts of its own.\nconnections: []\n';
  // after: what to do once saved (the texts of the detail, 2026-11-10: the panel drawn again); cancelled: on cancel
  function editFile(uid, j, view, after, cancelled) {
    view.innerHTML = '';
    var ta = h('textarea', {class: 'cbr-editor', spellcheck: 'false', wrap: 'off'});
    ta.value = j.text || (j.rel === '_desc.yaml' && !j.stamp ? DESC_TEMPLATE : '');
    ta.rows = Math.max(8, Math.min(40, (ta.value.match(/\n/g) || []).length + 2));
    var msg = h('span', {class: 'cbr-emsg'});
    var save = h('button', {type: 'button', class: 'cbr-btn'}, 'Save');
    var cancel = h('button', {type: 'button', class: 'cbr-copy'}, 'cancel');
    function doSave() {
      msg.textContent = '';
      save.disabled = true;
      call('save', {uid: uid, rel: j.rel, text: ta.value, stamp: j.stamp || ''}, 'saving ' + j.rel).then(function (r) {
        toast('saved ' + r.saved + (r.reindexed ? ' - the artifact is reindexed' : ''));
        (r.warnings || []).forEach(function (w) { toast(w, true); });
        if (after) after(r);
        else if (/^_(cmeta|desc)\./i.test(j.rel)) openDetail(uid);      // the meta and the description on the page follow
        else openFile(uid, j.rel, view);
      }).catch(function (e) { save.disabled = false; msg.textContent = e.message; });
    }
    save.addEventListener('click', doSave);
    cancel.addEventListener('click', function () { if (cancelled) cancelled(); else if (j.stamp) openFile(uid, j.rel, view); else view.innerHTML = ''; });
    ta.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); doSave(); }
      else if (e.key === 'Tab') {                // two spaces, as YAML wants
        e.preventDefault();
        var s = ta.selectionStart, t = ta.selectionEnd;
        ta.value = ta.value.slice(0, s) + '  ' + ta.value.slice(t);
        ta.selectionStart = ta.selectionEnd = s + 2;
      }
    });
    view.appendChild(h('div', {class: 'cbr-fhead'}, h('b', {}, (j.stamp ? 'editing ' : 'new file ') + j.rel), save, cancel, msg));
    view.appendChild(ta);
    ta.focus();
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
        if (n.kind === 'artifact') focusOn(crefOf(n.cat_uid, n.id), st.depth);
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
      var C = I.cache || {};
      bits.push('connection index: ' + num(I.total) + ' artifacts, ' + num(I.links) + ' connections, ' +
                num(I.uses) + ' uses' + (I.ai_uses ? ', ' + num(I.ai_uses) + ' AI uses' : '') + ', ' +
                num(I.descs) + ' descriptions, built in ' + msText(I.ms) + ' at ' + esc((I.built || '').slice(11, 16)) +
                (!C.artifact ? '' : I.reread >= I.descs ? ' (every _desc read, then kept in ' + esc(C.artifact) + ')'
                                  : ' (' + num(I.reread) + ' re-read, the rest from ' + esc(C.artifact) + ')') +
                (C.error ? ' · ' + esc(C.error) : ''));
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
    // the Search tab starts clean - the search bar and what to type, never the Browse tab's listing - and shows a
    // result only for the words typed; the Browse tab keeps its last listing
    else if (v === 'search' && !st.q.trim()) { last = null; renderSearchHint(); }
    else if (last && lastView === v) render();
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
        if (s === 'alias') {
          // the Artifact column cycles through three orders: by name A to Z, Z to A, then "undated first, the dated
          // ones newest first" (the order of a category that mixes routines and dated work, fgg.automation)
          var cur = last ? last.sort : '';
          if (cur === 'alias' && last.dir !== 'desc') { st.sort = 'alias'; st.dir = 'desc'; }
          else if (cur === 'alias') { st.sort = 'dated'; st.dir = 'asc'; }
          else { st.sort = 'alias'; st.dir = 'asc'; }
          run();
          return;
        }
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
    root.querySelectorAll('.cbr-col-toggle input[data-col]').forEach(function (box) {
      var col = box.getAttribute('data-col');
      box.checked = colOn(col);
      box.addEventListener('click', function (e) { e.stopPropagation(); });
      box.addEventListener('change', function () {
        try { localStorage.setItem('cbr-browse-' + col, box.checked ? '1' : '0'); } catch (e) { /* ignore */ }
        $('cbr-table').classList.toggle('no-' + col, !box.checked);
      });
    });
    $('cbr-clear').addEventListener('click', function () {
      st.q = st.repos = st.cats = st.after = st.before = st.sort = st.dir = st.focus = st.depth = '';
      st.repos = DEFAULT_PICK.repos; st.cats = DEFAULT_PICK.cats;      // the pickers as the server opens them
      $('cbr-q').value = ''; $('cbr-after').value = ''; $('cbr-before').value = '';
      pickerLabel('repos'); pickerLabel('cats');
      if (options) { buildPicker('repos'); buildPicker('cats'); }
      run();
    });
    // the category index: its filter box and the fold of every group
    $('cbr-toc-filter').addEventListener('input', function () { tocFilter = $('cbr-toc-filter').value.trim(); renderToc(); });
    $('cbr-toc-fold').addEventListener('click', function () {
      var groups = tocGroups((last && last.toc) || (options && options.cats) || []).filter(function (g) { return g.key; });
      var anyOpen = groups.some(function (g) { return !tocFold[g.key]; });
      groups.forEach(function (g) { tocFold[g.key] = anyOpen; });
      $('cbr-toc-fold').textContent = anyOpen ? 'unfold' : 'fold';
      renderToc();
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
    var wantUid = st.uid, wantFile = st.file;
    call('options', {}, 'loading the index').then(function (o) {
      options = o;
      subtitle(o);
      buildPicker('repos');
      buildPicker('cats');
      setView(st.view);
      if (wantUid) openDetail(wantUid, wantFile);
      if (CFG.notice) showError(CFG.notice);   // a cref= that names nothing this server shows
    }).catch(function (e) { showError(e.message); });
  }
  // The connections are read in the background; any answer that carries the state of that index updates this
  // line (no polling: on the engine cserver every call can land in another worker process, with its own index)
  function subtitle(o) {
    if (o && o.total != null) options = o;
    if (o && o.index) indexState = o.index;
    if (!options) return;
    $('cbr-sub').textContent = 'Browse, search and graph ' + num(options.total) + ' artifacts in ' +
      options.cats.length + ' categories of ' + options.repos.length + ' repositories' +
      (indexState && indexState.ready ? ', joined by ' + num(indexState.links) + ' connections.' : '.');
  }
  init();
})();
