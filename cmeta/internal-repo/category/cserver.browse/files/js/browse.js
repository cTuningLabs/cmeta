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

  // The categorical palette (validated slot order, light and dark steps); a 9th category and beyond is "other"
  var PALETTE_LIGHT = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'];
  var PALETTE_DARK = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'];
  var OTHER = '#8d93a0';
  var THEME_KEY = 'cserver.browse.theme';
  var VIEWS = ['search', 'browse', 'graph'];

  var st = {q: '', repos: '', cats: '', after: '', before: '', view: 'search', sort: '', dir: '', uid: ''};
  Object.keys(st).forEach(function (k) { if (CFG.state && CFG.state[k]) st[k] = CFG.state[k]; });
  if (VIEWS.indexOf(st.view) < 0) st.view = 'search';
  st.offset = 0;
  st.limit = 50;

  var options = null;      // {repos: [[name, n]], cats: [[name, n]], total, catalog}
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
  function call(action, params, what) {
    busy(true, what || 'loading');
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
      .finally(function () { busy(false); });
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
      ['q', 'repos', 'cats', 'after', 'before', 'sort', 'dir', 'uid'].forEach(function (k) {
        if (st[k]) u.searchParams.set(k, st[k]); else u.searchParams.delete(k);
      });
      if (st.view !== 'search') u.searchParams.set('view', st.view); else u.searchParams.delete('view');
      history.replaceState(null, '', u.toString());
    } catch (e) { /* old browser: the state stays in the page */ }
    $('cbr-json').href = apiUrl('search') + '&' + qs(params());
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
      if (st.view === 'graph' && graph) graph.recolour();
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
  function openDetail(uid) {
    if (!uid) return;
    st.uid = uid;
    syncUrl();
    call('artifact', {uid: uid}, 'reading the artifact').then(function (d) {
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
      if (d.connections && d.connections.length) {
        box.appendChild(h('h3', {}, 'Connects to (' + d.connections.length + ')'));
        var ul = h('ul', {class: 'cbr-links'});
        d.connections.forEach(function (c) {
          if (c.found) {
            var a = h('a', {href: '#', title: c.cref}, c.alias);
            a.addEventListener('click', function (e) { e.preventDefault(); openDetail(c.uid); });
            ul.appendChild(h('li', {}, a, h('span', {class: 'cbr-muted'}, '  ' + c.cat)));
          } else {
            ul.appendChild(h('li', {class: 'missing', title: 'not in the index of this server'}, c.cref));
          }
        });
        box.appendChild(ul);
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
    $('cbr-detail').hidden = true;
    st.uid = '';
    syncUrl();
  }

  /* ------------------------------------------------------------------ Graph view */
  var graph = null;
  var stopGraph = null;      // stops the animation of the graph on screen before another one is drawn
  function loadGraph() {
    var max = parseInt($('cbr-gmax').value, 10) || 150;
    var nb = $('cbr-gnb').checked;
    return call('graph', Object.assign(params(), {max_nodes: max, neighbors: nb ? '1' : ''}), 'building the graph')
      .then(function (g) {
        $('cbr-status').textContent = g.total + ' artifacts match · ' + g.shown + ' shown' +
          (g.truncated ? ' (raise "nodes" to see more)' : '') + ' · ' + g.links.length + ' connections · ' + g.ms + ' ms';
        $('cbr-gstat').textContent = '';
        graph = drawGraph(g);
      })
      .catch(function (e) { showError(e.message); });
  }

  function drawGraph(g) {
    var NS = 'http://www.w3.org/2000/svg';
    var svg = $('cbr-svg');
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var W = svg.clientWidth || 900, H = svg.clientHeight || 600;
    function el(tag, cls) { var e = document.createElementNS(NS, tag); if (cls) e.setAttribute('class', cls); return e; }

    var top = g.cats.slice(0, 8).map(function (x) { return x[0]; });
    function colour(cat) {
      var pal = root.classList.contains('dark') ? PALETTE_DARK : PALETTE_LIGHT;
      var i = top.indexOf(cat);
      return i >= 0 ? pal[i] : OTHER;
    }
    var legend = $('cbr-legend');
    function drawLegend() {
      legend.innerHTML = '';
      g.cats.slice(0, 8).forEach(function (x) {
        var i = h('i'); i.style.background = colour(x[0]);
        legend.appendChild(h('div', {title: x[0]}, i, x[0], h('span', {class: 'n'}, String(x[1]))));
      });
      if (g.cats.length > 8) {
        var rest = g.cats.slice(8).reduce(function (s, x) { return s + x[1]; }, 0);
        var i2 = h('i'); i2.style.background = OTHER;
        legend.appendChild(h('div', {}, i2, (g.cats.length - 8) + ' other categories', h('span', {class: 'n'}, String(rest))));
      }
      legend.hidden = !g.cats.length;
    }
    drawLegend();

    var nodes = g.nodes.map(function (r, i) {
      var a = 2 * Math.PI * i / Math.max(1, g.nodes.length);
      var rad = Math.min(W, H) * 0.35 * Math.sqrt((i + 1) / Math.max(1, g.nodes.length));
      return {r: r, x: W / 2 + rad * Math.cos(a), y: H / 2 + rad * Math.sin(a), vx: 0, vy: 0, deg: 0, fixed: false};
    });
    var byId = {};
    nodes.forEach(function (n) { byId[n.r.uid] = n; });
    var links = [];
    g.links.forEach(function (l) {
      var s = byId[l.source], t = byId[l.target];
      if (s && t) { links.push({s: s, t: t}); s.deg++; t.deg++; }
    });

    var view = el('g');
    var gl = el('g'), gn = el('g'), gt = el('g');
    view.appendChild(gl); view.appendChild(gn); view.appendChild(gt);
    svg.appendChild(view);
    links.forEach(function (l) { l.el = el('line', 'lk'); gl.appendChild(l.el); });
    // Every label on a small graph; on a large one only the 25 best connected nodes (the rest on hover)
    var showAllLabels = nodes.length <= 70;
    var labelled = {};
    nodes.slice().sort(function (a, b) { return b.deg - a.deg; }).slice(0, 25)
      .forEach(function (p) { if (p.deg > 0) labelled[p.r.uid] = 1; });
    nodes.forEach(function (n) {
      n.rad = 4 + Math.min(9, Math.sqrt(n.deg) * 2);
      n.el = el('circle', 'nd' + (n.r.neighbor ? ' nb' : ''));
      n.el.setAttribute('r', n.rad);
      n.el.setAttribute('fill', colour(n.r.cat));
      var t = el('title'); t.textContent = n.r.alias + '  (' + n.r.cat + ', ' + (n.r.repo || 'registry') + ')';
      n.el.appendChild(t);
      gn.appendChild(n.el);
      if (showAllLabels || labelled[n.r.uid]) {
        n.lb = el('text', 'lb');
        n.lb.textContent = n.r.alias.length > 34 ? n.r.alias.slice(0, 32) + '…' : n.r.alias;
        gt.appendChild(n.lb);
      }
    });
    if (!nodes.length) {
      var t0 = el('text', 'lb'); t0.setAttribute('x', W / 2 - 80); t0.setAttribute('y', H / 2);
      t0.textContent = 'Nothing matches the query.'; gt.appendChild(t0);
    }

    // A small force simulation: repulsion between all nodes, springs along the connections, a pull to the centre.
    // Most of it runs before the first paint, so the picture is already still when it appears and is fitted
    // once; the rest settles in a few frames without moving the view.
    if (stopGraph) stopGraph();
    var alpha = 1, raf = 0, n = nodes.length;
    var k = Math.sqrt(W * H / Math.max(1, n)) * 0.55;
    function tick() {
      var i, j, a, b, dx, dy, d2, f;
      for (i = 0; i < n; i++) {
        a = nodes[i];
        for (j = i + 1; j < n; j++) {
          b = nodes[j];
          dx = a.x - b.x; dy = a.y - b.y;
          d2 = dx * dx + dy * dy || 0.01;
          if (d2 > 90000) continue;
          f = k * k / d2 * 0.04 * alpha;
          a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
        }
      }
      links.forEach(function (l) {
        var lx = l.t.x - l.s.x, ly = l.t.y - l.s.y;
        var d = Math.sqrt(lx * lx + ly * ly) || 0.01;
        var s = (d - k * 0.9) / d * 0.06 * alpha;
        l.s.vx += lx * s; l.s.vy += ly * s; l.t.vx -= lx * s; l.t.vy -= ly * s;
      });
      nodes.forEach(function (p) {
        p.vx += (W / 2 - p.x) * 0.004 * alpha;
        p.vy += (H / 2 - p.y) * 0.004 * alpha;
        if (!p.fixed) { p.x += Math.max(-30, Math.min(30, p.vx)); p.y += Math.max(-30, Math.min(30, p.vy)); }
        p.vx *= 0.55; p.vy *= 0.55;
      });
      alpha *= 0.982;
    }
    function paint() {
      links.forEach(function (l) {
        l.el.setAttribute('x1', l.s.x); l.el.setAttribute('y1', l.s.y);
        l.el.setAttribute('x2', l.t.x); l.el.setAttribute('y2', l.t.y);
      });
      nodes.forEach(function (p) {
        p.el.setAttribute('cx', p.x); p.el.setAttribute('cy', p.y);
        if (p.lb) { p.lb.setAttribute('x', p.x + p.rad + 3); p.lb.setAttribute('y', p.y + 4); }
      });
    }
    function loop() {
      var steps = n > 350 ? 1 : (n > 150 ? 2 : 3);
      for (var s = 0; s < steps; s++) tick();
      paint();
      raf = alpha > 0.015 ? requestAnimationFrame(loop) : 0;
    }

    // Zoom, pan, drag, hover, click
    var tx = 0, ty = 0, sc = 1;
    function apply() { view.setAttribute('transform', 'translate(' + tx + ',' + ty + ') scale(' + sc + ')'); }
    function fit() {
      if (!nodes.length) return;
      var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      nodes.forEach(function (p) { x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x); y1 = Math.max(y1, p.y); });
      var w = Math.max(40, x1 - x0), hh = Math.max(40, y1 - y0);
      sc = Math.min(2.5, 0.9 * Math.min(W / w, H / hh));
      tx = W / 2 - sc * (x0 + w / 2); ty = H / 2 - sc * (y0 + hh / 2);
      apply();
    }

    // Settle most of the layout now (within ~0.6 s), fit it once, then let the last of it settle on screen
    var started = Date.now();
    while (alpha > 0.06 && Date.now() - started < 600) tick();
    paint();
    fit();
    raf = requestAnimationFrame(loop);
    stopGraph = function () { cancelAnimationFrame(raf); raf = 0; cancelAnimationFrame(wheelRaf); wheelRaf = 0; };

    // Zoom by how far the wheel actually turned, applied at most once per frame. A smooth wheel or a touchpad
    // sends a burst of small events for one notch, and a few more after the hand stops: a fixed step per event
    // made one small turn zoom many times over and drift on. Now the zoom is proportional to the turn, so it
    // stops when the wheel stops, and it stays between 1/20 and 20 times.
    var wheelDy = 0, wheelX = 0, wheelY = 0, wheelRaf = 0;
    function zoomStep() {
      wheelRaf = 0;
      var f = Math.exp(-Math.max(-300, Math.min(300, wheelDy)) * 0.0015);
      wheelDy = 0;
      var nsc = Math.max(0.05, Math.min(20, sc * f));
      f = nsc / sc;
      tx = wheelX - (wheelX - tx) * f; ty = wheelY - (wheelY - ty) * f; sc = nsc;
      apply();
    }
    svg.onwheel = function (e) {
      e.preventDefault();
      var dy = e.deltaY * (e.deltaMode === 1 ? 16 : (e.deltaMode === 2 ? H : 1));
      if (Math.abs(dy) < 0.5) return;
      var r = svg.getBoundingClientRect();
      wheelX = e.clientX - r.left; wheelY = e.clientY - r.top;
      wheelDy += dy;
      if (!wheelRaf) wheelRaf = requestAnimationFrame(zoomStep);
    };
    svg.ondblclick = function (e) { if (e.target === svg) fit(); };
    var drag = null;
    function toWorld(e) {
      var r = svg.getBoundingClientRect();
      return {x: (e.clientX - r.left - tx) / sc, y: (e.clientY - r.top - ty) / sc};
    }
    svg.onpointerdown = function (e) {
      var hit = null;
      nodes.forEach(function (p) { if (p.el === e.target) hit = p; });
      drag = {node: hit, x: e.clientX, y: e.clientY, tx: tx, ty: ty, moved: false};
      if (hit) { hit.fixed = true; }
      else svg.classList.add('panning');
      svg.setPointerCapture(e.pointerId);
    };
    svg.onpointermove = function (e) {
      if (!drag) return;
      if (Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) > 3) drag.moved = true;
      if (drag.node) {
        var w = toWorld(e);
        drag.node.x = w.x; drag.node.y = w.y;
        if (alpha < 0.05) { alpha = 0.05; cancelAnimationFrame(raf); loop(); } else paint();
      } else {
        tx = drag.tx + e.clientX - drag.x; ty = drag.ty + e.clientY - drag.y;
        apply();
      }
    };
    svg.onpointerup = function () {
      if (drag && drag.node) {
        drag.node.fixed = false;
        if (!drag.moved) openDetail(drag.node.r.uid);
      }
      drag = null;
      svg.classList.remove('panning');
    };
    nodes.forEach(function (p) {
      p.el.addEventListener('mouseenter', function () {
        p.el.classList.add('hot');
        links.forEach(function (l) { if (l.s === p || l.t === p) l.el.classList.add('hot'); });
        if (!p.lb) {
          p.tmp = el('text', 'lb'); p.tmp.textContent = p.r.alias;
          p.tmp.setAttribute('x', p.x + p.rad + 3); p.tmp.setAttribute('y', p.y + 4); gt.appendChild(p.tmp);
        }
      });
      p.el.addEventListener('mouseleave', function () {
        p.el.classList.remove('hot');
        links.forEach(function (l) { l.el.classList.remove('hot'); });
        if (p.tmp) { gt.removeChild(p.tmp); p.tmp = null; }
      });
    });
    apply();
    return {
      recolour: function () {
        nodes.forEach(function (p) { p.el.setAttribute('fill', colour(p.r.cat)); });
        drawLegend();
      }
    };
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
    $('cbr-form').addEventListener('submit', function (e) {
      e.preventDefault();
      closePickers();
      st.q = $('cbr-q').value.trim();
      st.sort = '';
      st.dir = '';
      run();
    });
    ['after', 'before'].forEach(function (k) {
      $('cbr-' + k).addEventListener('change', function () { st[k] = $('cbr-' + k).value; run(); });
    });
    $('cbr-clear').addEventListener('click', function () {
      st.q = st.repos = st.cats = st.after = st.before = st.sort = st.dir = '';
      $('cbr-q').value = ''; $('cbr-after').value = ''; $('cbr-before').value = '';
      pickerLabel('repos'); pickerLabel('cats');
      if (options) { buildPicker('repos'); buildPicker('cats'); }
      run();
    });
    $('cbr-help-btn').addEventListener('click', function () { $('cbr-help').hidden = !$('cbr-help').hidden; });
    $('cbr-reload').addEventListener('click', function () {
      call('reload', {}, 'reloading the index').then(function (o) { options = o; buildPicker('repos'); buildPicker('cats'); run(); })
        .catch(function (e) { showError(e.message); });
    });
    $('cbr-gmax').addEventListener('change', function () { if (st.view === 'graph') loadGraph(); });
    $('cbr-gnb').addEventListener('change', function () { if (st.view === 'graph') loadGraph(); });
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
      $('cbr-sub').textContent = 'Search, browse and graph ' + o.total + ' artifacts in ' + o.repos.length +
        ' repositories and ' + o.cats.length + ' categories.';
      buildPicker('repos');
      buildPicker('cats');
      setView(st.view);
      if (wantUid) openDetail(wantUid);
    }).catch(function (e) { showError(e.message); });
  }
  init();
})();
