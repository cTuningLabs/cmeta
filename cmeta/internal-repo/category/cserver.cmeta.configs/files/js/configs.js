/* Licensed under the Apache License, Version 2.0. See the COPYRIGHT and LICENSE files in the project root.
 *
 * cserver.cmeta.configs - the config artifacts and their keys as the plugged artifacts know them, both ways:
 *  - the map on the left: the artifacts that use configs (by category), the configs, and a line from each artifact to
 *    each config it uses (solid: reads it in its code, dashed: declares its keys, dotted: shows them in its docs);
 *    pointing at a name lights its lines and their ends with what goes between them ("5 read", "every key") and fades
 *    the rest; a click keeps it and shows only that on the right (an artifact and what it uses, a config and who uses
 *    it, or both: one artifact's keys of one config); a second click, the card's x or Esc lets go;
 *  - the cards on the right: one per config, the table of its keys (what each does, its value here, who reads it), a
 *    click on a key for everything known of it and the commands that change it; the keys set here that nothing reads
 *    under each card; or, by repository, what each repository brings.
 * The search, the filters, the chosen artifact and config and the view live in the address, so that a reload or a
 * shared link shows the same; the theme and the pane shown on a narrow screen are kept by the browser.
 *
 * No third-party libraries: the page works offline, on the engine cserver and on the cPlatform alike.
 */
(function () {
  'use strict';
  var CFG = window.CONFIG || {};
  var root = document.getElementById('ccf');
  if (!root) return;
  function $(id) { return document.getElementById(id); }

  var THEME_KEY = 'cserver.cmeta.configs.theme';
  var PANE_KEY = 'cserver.cmeta.configs.pane';      // which list a narrow screen shows: arts | cfgs
  var URL_KEYS = ['q', 'show', 'repo', 'view', 'open', 'art', 'cfg'];
  var SHOWS = ['', 'set', 'unset', 'unread', 'undocumented'];
  var SRC = {declared: 'D', code: 'C', docs: 'R'};
  var SRC_TITLE = {declared: 'declared in the configs block of a _desc.yaml', code: 'read by the code of an artifact',
                   docs: 'shown in a README, the docs or a comment (a cx config set line, a table of keys)'};
  var FROM = {declared: 'declared in', table: 'a table of keys in', cmd: 'a cx config set line in',
              'const': 'a comment of the code of', line: 'a comment of the code of', above: 'a comment of the code of',
              settings: 'the settings of this page', code: 'the code of'};
  // the order of the groups of the map (the categories that hold code first; the others by name, repositories last)
  var GROUPS = ['category', 'app', 'task', 'tool', 'program', 'container', 'script', 'automation', 'website', 'host',
                'machine'];

  var st = {q: '', show: '', repo: '', view: '', open: '', art: '', cfg: ''};
  URL_KEYS.forEach(function (k) { if (CFG.state && CFG.state[k] != null) st[k] = String(CFG.state[k]); });
  if (SHOWS.indexOf(st.show) < 0) st.show = '';

  var data = null;              // the last answer of the server
  var ART = {};                 // its artifacts by aid (category UID::artifact UID)
  var USES = {};                // each artifact and the configs it uses: {aid: {config: {reads, declares, docs, keys, how}}}
  var BY_NAME = {};             // the configs by name
  var rows = [];                // every key (and every key set here that nothing reads) as a row of the search
  var EDGES = [];               // the lines of the map drawn now: {id, aid, cfg, kind}
  var hover = null;             // what the pointer is on in the map: {aid, cfg} (one of them, or both for a line)
  var opened = {};              // the rows whose details are open: config + '\n' + key
  var busyCount = 0, toastTimer = null, frame = 0;
  var revealed = '|';           // the choice the map last brought into view (art|cfg)
  var wholeReaders = {};        // the cards whose list of users was unfolded ("and N more")
  var READERS_SHOWN = 12;
  var pane = 'cfgs';
  try { pane = localStorage.getItem(PANE_KEY) === 'arts' ? 'arts' : 'cfgs'; } catch (e) { pane = 'cfgs'; }

  /* ------------------------------------------------------------------ helpers */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  // a text of a description: its `code` and [links](https://...) shown as such, the rest escaped
  function rich(s) {
    return esc(s).replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  }
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
  function num(n) { return Number(n || 0).toLocaleString('en-US'); }
  function msText(ms) { return ms >= 1000 ? (ms / 1000).toFixed(1) + ' s' : Math.round(ms) + ' ms'; }
  function byText(f) { return function (x, y) { var a = f(x), b = f(y); return a < b ? -1 : (a > b ? 1 : 0); }; }
  function apiUrl(action) {
    var u = CFG.api_url || '?';
    var sep = /[?&]$/.test(u) ? '' : (u.indexOf('?') >= 0 ? '&' : '?');
    return u + sep + 'native_action=' + action;
  }
  function call(action, params) {
    return fetch(apiUrl(action), {method: 'POST', headers: {'Content-Type': 'application/json'},
                                  body: JSON.stringify(params || {})})
      .then(function (res) {
        return res.text().then(function (text) {
          var d;
          try { d = JSON.parse(text); } catch (e) { throw new Error('HTTP ' + res.status + ': ' + text.slice(0, 300)); }
          if (d && d.error) throw new Error(d.error);
          return d;
        });
      });
  }
  function busy(on, what) {
    busyCount = Math.max(0, busyCount + (on ? 1 : -1));
    var b = $('ccf-busy');
    if (on && what) b.querySelector('.what').textContent = what;
    b.hidden = busyCount === 0;
  }
  function showError(msg) { var e = $('ccf-error'); e.textContent = msg || ''; e.hidden = !msg; }
  function toast(text) {
    var t = $('ccf-toast');
    if (!t) { t = h('div', {id: 'ccf-toast', class: 'ccf-toast', role: 'status'}); root.appendChild(t); }
    t.textContent = text;
    t.className = 'ccf-toast show';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.className = 'ccf-toast'; }, 1800);
  }
  function copyText(text, btn) {
    function done() {
      toast('Copied: ' + (text.length > 70 ? text.slice(0, 67) + '...' : text));
      if (btn) { btn.classList.add('done'); setTimeout(function () { btn.classList.remove('done'); }, 1200); }
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () { fallback(); });
    } else fallback();
    function fallback() {
      var ta = h('textarea', {style: 'position:fixed;left:-9999px;top:0'});
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); done(); } catch (e) { toast('Copy it by hand: ' + text); }
      document.body.removeChild(ta);
    }
  }
  function nameOf(a) { return a.cat + '::' + a.alias; }
  // the page of an artifact (and of one of its files) on this host: its /cref/ reader
  function crefHref(a, file) {
    if (!CFG.cref_url || !a) return '';
    var u = CFG.cref_url + encodeURIComponent(a.cat) + '::' + encodeURIComponent(a.alias) + ',' + a.uid;
    if (file) u += '/' + String(file).split('/').map(encodeURIComponent).join('/');
    return u;
  }
  // an artifact in a card: a click shows only what it uses (as in the map); the arrow opens its page
  function artChip(aid, extra) {
    var a = ART[aid];
    if (!a) return null;
    var chip = h('span', {class: 'ccf-art' + (st.art === aid ? ' sel' : ''), title: nameOf(a) + ' · ' + a.repo +
                          (a.name ? '\n' + a.name : '') + '\na click: only what it uses'});
    var b = h('button', {type: 'button', class: 'ccf-art-pick'}, nameOf(a));
    b.addEventListener('click', function (ev) { ev.stopPropagation(); selectArt(aid); });
    chip.appendChild(b);
    if (a.repo) chip.appendChild(h('span', {class: 'rp'}, ' · ' + a.repo));
    if (extra) chip.appendChild(h('span', {class: 'how'}, ' ' + extra));
    var href = crefHref(a);
    if (href) chip.appendChild(h('a', {href: href, class: 'ccf-open', title: 'the page of ' + nameOf(a)}, '↗'));
    return chip;
  }
  function isPattern(key) { return /[<*]/.test(key); }
  // what an artifact does with a config, in a few words: "5 read · every key", "3 declared", "2 in docs"
  function pairText(aid, cfg) {
    var u = (USES[aid] || {})[cfg];
    if (!u) return '';
    var parts = [];
    if (u.reads) parts.push(u.reads + ' read');
    if (u.how.indexOf('every key') >= 0) parts.push('every key');
    if (u.declares) parts.push(u.declares + ' declared');
    if (u.docs) parts.push(u.docs + ' in docs');
    if (u.how.indexOf('write') >= 0) parts.push('writes');
    if (!parts.length && u.how.indexOf('run time') >= 0) parts.push('keys named at run time');
    return parts.join(' · ') || 'reads it';
  }
  // the same in the map, as small counts in the colours of the legend (blue: read, purple: declared, grey: in docs;
  // "all": every key, "w": writes, "*": keys named at run time) - the words in its title
  function pairBadge(el, aid, cfg) {
    var u = (USES[aid] || {})[cfg];
    el.textContent = '';
    el.removeAttribute('title');
    if (!u) return;
    function b(cls, text) { el.appendChild(h('b', {class: cls}, text)); }
    if (u.reads) b('r', String(u.reads));
    if (u.how.indexOf('every key') >= 0) b('r', 'all');
    if (u.declares) b('d', String(u.declares));
    if (u.docs) b('m', String(u.docs));
    if (u.how.indexOf('write') >= 0) b('r', 'w');
    if (!el.childNodes.length) b('r', u.how.indexOf('run time') >= 0 ? '*' : '•');
    el.title = pairText(aid, cfg);
  }
  function edgeKind(u) {
    if (u.reads || u.how.some(function (x) { return x === 'reads' || x === 'every key' || x === 'run time' || x === 'write'; }))
      return 'reads';
    return u.declares || u.how.indexOf('declared') >= 0 ? 'declares' : 'docs';
  }

  /* ------------------------------------------------------------------ the search */
  function terms(q) {
    var out = [];
    var re = /(-?)(?:(\w+):)?("([^"]*)"|\S+)/g, m;
    while ((m = re.exec(q || '')) !== null) {
      var neg = m[1] === '-', field = (m[2] || '').toLowerCase();
      var value = (m[4] != null ? m[4] : m[3]).toLowerCase();
      field = {cfg: 'config', artifact: 'art'}[field] || field;
      if (field && ['config', 'key', 'art', 'repo', 'cat', 'is'].indexOf(field) < 0) { value = field + ':' + value; field = ''; }
      if (value) out.push({neg: neg, field: field, value: value});
    }
    return out;
  }
  function globRe(p) {
    return new RegExp('^' + p.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.') + '$');
  }
  function matches(r, ts) {
    for (var i = 0; i < ts.length; i++) {
      var t = ts[i], hit;
      if (t.field === 'config') hit = /[*?]/.test(t.value) ? globRe(t.value).test(r.config) : r.config.indexOf(t.value) >= 0;
      else if (t.field === 'key') hit = r.key.indexOf(t.value) >= 0;
      else if (t.field === 'art') hit = r.arts.some(function (x) { return x.indexOf(t.value) >= 0; });
      else if (t.field === 'repo') hit = r.repos.some(function (x) { return x.indexOf(t.value) >= 0; });
      else if (t.field === 'cat') hit = r.cats.some(function (x) { return x.indexOf(t.value) >= 0; });
      else if (t.field === 'is') hit = !!r.is[t.value];
      else hit = r.hay.indexOf(t.value) >= 0;
      if (hit === t.neg) return false;
    }
    return true;
  }
  // a row: what a word may be found in, what is: says of it, and the artifacts it is about (aids) - those that read,
  // declare or show the key, and those that read every key of its whole config
  function row(c, k, extra) {
    var aids = {};
    var related = !k ? (c.readers || []) : (k.readers ? k.readers.concat(k.declared || [], k.docs || []) : []);
    related.forEach(function (x) { aids[x.aid] = 1; });
    (c.readers || []).forEach(function (x) { if ((x.every || []).indexOf('') >= 0) aids[x.aid] = 1; });
    var who = Object.keys(aids).map(function (aid) { return ART[aid]; }).filter(Boolean);
    var r = {c: c, k: k, config: c.name.toLowerCase(), key: k ? k.key.toLowerCase() : '', aids: aids,
             repos: who.map(function (a) { return (a.repo || '').toLowerCase(); }),
             cats: who.map(function (a) { return (a.cat || '').toLowerCase(); }),
             arts: who.map(function (a) { return nameOf(a).toLowerCase(); }),
             names: who.map(function (a) { return nameOf(a) + ' ' + a.repo; }).join(' ')};
    Object.keys(extra || {}).forEach(function (x) { r[x] = extra[x]; });
    return r;
  }
  function buildRows() {
    rows = [];
    data.configs.forEach(function (c) {
      c.keys.forEach(function (k) {
        var is = {};
        k.sources.forEach(function (s) { is[s] = 1; });
        is[k.set ? 'set' : 'unset'] = 1;
        if (k.secret) is.secret = 1;
        if (!k.desc) is.undocumented = 1;
        if (isPattern(k.key)) is.dynamic = 1;
        var r = row(c, k, {is: is});
        r.hay = [c.name, k.key, k.desc, k.type, (k.defaults || []).join(' '), k.secret ? '' : (k.value || ''),
                 (k.descs || []).map(function (d) { return d.text; }).join(' '), r.names].join(' ').toLowerCase();
        rows.push(r);
      });
      (c.unread || []).forEach(function (u) {
        // set here, read by none: about no artifact but one that reads every key of the config
        var r = row(c, u, {unread: true, is: {set: 1, unread: 1}});
        r.hay = [c.name, u.key, u.secret ? '' : (u.value || '')].join(' ').toLowerCase();
        rows.push(r);
      });
      if (!c.keys.length && !(c.unread || []).length) {
        // a config with no key known: the card alone, found by its name, what it is and who uses it
        var r = row(c, null, {is: c.artifacts.length ? {set: 1} : {unset: 1}});
        r.hay = [c.name, c.desc, r.names].join(' ').toLowerCase();
        rows.push(r);
      }
    });
  }
  // the rows the query, the repository and (withShow) the pill keep - what the map shows -, and (withSel) the
  // artifact and the config chosen in the map - what the cards show
  function filtered(withShow, withSel) {
    var ts = terms(st.q);
    if (withShow && st.show) ts.push({neg: false, field: 'is', value: st.show});
    var repo = st.repo.toLowerCase();
    return rows.filter(function (r) {
      if (repo && r.repos.indexOf(repo) < 0) return false;
      if (withSel && st.art && !r.aids[st.art]) return false;
      if (withSel && st.cfg && r.c.name !== st.cfg) return false;
      return matches(r, ts);
    });
  }

  /* ------------------------------------------------------------------ the commands of a key */
  function quoteArg(arg) {
    return /[\s"&|<>^%!;()]/.test(arg) ? '"' + arg.replace(/"/g, '\\"') + '"' : arg;
  }
  function setLine(name, key, value, listy) {
    return 'cx config set ' + quoteArg(name) + ' ' + quoteArg('--meta.' + key + (listy ? ',' : '') + '=' + value);
  }
  function commands(c, k) {
    var out = [];
    var listy = !!(k.list || k.type === 'list');
    if (k.unread) {
      out.push(['remove it', 'cx config unset ' + quoteArg(c.name) + ' ' + quoteArg('--meta.' + k.key)]);
      return out;
    }
    var value;
    if (k.set && !k.secret && k.value != null) value = k.value;
    else {
      var ex = (k.examples || []).filter(function (x) { return !x.sub; })[0];
      value = ex ? ex.value : '<' + (k.type && k.type !== 'text' ? k.type.replace('/', '|') : 'value') + '>';
    }
    out.push([k.set ? 'change it' : 'set it', setLine(c.name, k.key, value, listy)]);
    (k.examples || []).filter(function (x) { return x.sub; }).slice(0, 2).forEach(function (x) {
      out.push(['an entry under it', setLine(c.name, k.key + '.' + x.sub, x.value, false)]);
    });
    if (k.set && k.value != null || k.set && k.secret)
      out.push(['remove it (its default applies again)', 'cx config unset ' + quoteArg(c.name) + ' ' + quoteArg('--meta.' + k.key)]);
    (k.children || []).slice(0, 3).forEach(function (x) {
      out.push(['remove ' + x.key, 'cx config unset ' + quoteArg(c.name) + ' ' + quoteArg('--meta.' + x.key)]);
    });
    out.push(['what is set', 'cx config show ' + quoteArg(c.name)]);
    return out;
  }
  function cmdBlock(list) {
    var box = h('div', {class: 'ccf-cmds'});
    list.forEach(function (it) {
      var b = h('button', {type: 'button', class: 'ccf-copy', title: it[0]}, 'copy');
      b.addEventListener('click', function (ev) { ev.stopPropagation(); copyText(it[1], b); });
      box.appendChild(h('div', {class: 'ccf-cmd'}, h('code', {title: it[0]}, it[1]), b));
    });
    return box;
  }

  /* ------------------------------------------------------------------ choosing in the map */
  function scrollToCards() {
    var list = $('ccf-list');
    var top = list.getBoundingClientRect().top + window.scrollY - 70;
    if (window.scrollY > top) window.scrollTo({top: Math.max(0, top), behavior: 'smooth'});
  }
  function selectArt(aid) {
    st.art = st.art === aid ? '' : aid;
    st.view = '';
    hover = null;
    writeUrl();
    render();
    scrollToCards();
  }
  function selectCfg(name) {
    st.cfg = st.cfg === name ? '' : name;
    st.view = '';
    hover = null;
    writeUrl();
    render();
    scrollToCards();
  }
  function selectBoth(aid, name) {
    var same = st.art === aid && st.cfg === name;
    st.art = same ? '' : aid;
    st.cfg = same ? '' : name;
    st.view = '';
    hover = null;
    writeUrl();
    render();
    scrollToCards();
  }
  function release() {
    if (!st.art && !st.cfg) return false;
    st.art = st.cfg = '';
    hover = null;
    writeUrl();
    render();
    return true;
  }

  /* ------------------------------------------------------------------ the map */
  function groupRank(cat) {
    var i = GROUPS.indexOf(cat);
    if (i >= 0) return i;
    if (/automation$/.test(cat)) return GROUPS.indexOf('automation');
    return cat === 'repo' ? 99 : 50;
  }
  function renderMap(kept) {
    var narrowed = !!(st.q || st.show || st.repo);
    var artN = {}, cfgN = {};
    kept.forEach(function (r) {
      cfgN[r.c.name] = (cfgN[r.c.name] || 0) + (r.k ? 1 : 0);
      Object.keys(r.aids).forEach(function (aid) { artN[aid] = (artN[aid] || 0) + 1; });
    });
    // who uses a config the rows are in, as a whole or under names of its own choosing (no key of it known)
    Object.keys(cfgN).forEach(function (name) {
      ((BY_NAME[name] || {}).readers || []).forEach(function (x) { if (!(x.aid in artN)) artN[x.aid] = 0; });
    });
    if (!narrowed) {
      Object.keys(USES).forEach(function (aid) { if (!(aid in artN)) artN[aid] = 0; });
      data.configs.forEach(function (c) { if (!(c.name in cfgN)) cfgN[c.name] = 0; });
    }
    if (st.art && ART[st.art] && !(st.art in artN)) artN[st.art] = 0;   // what is chosen stays in view
    if (st.cfg && BY_NAME[st.cfg] && !(st.cfg in cfgN)) cfgN[st.cfg] = 0;

    // the artifacts by category; each with the number of configs it uses
    var ap = $('ccf-arts'), cp = $('ccf-cfgs');
    var keepA = ap.scrollTop, keepC = cp.scrollTop;
    ap.textContent = '';
    var groups = {};
    Object.keys(artN).forEach(function (aid) {
      var a = ART[aid];
      if (a) (groups[a.cat] = groups[a.cat] || []).push(aid);
    });
    Object.keys(groups).sort(function (x, y) { return groupRank(x) - groupRank(y) || (x < y ? -1 : 1); })
      .forEach(function (cat) {
        ap.appendChild(h('h4', {}, cat, h('span', {class: 'n'}, ' ' + groups[cat].length)));
        groups[cat].sort(byText(function (aid) { return ART[aid].alias.toLowerCase(); })).forEach(function (aid) {
          var a = ART[aid], n = Object.keys(USES[aid] || {}).length;
          ap.appendChild(h('div', {class: 'ccf-node' + (st.art === aid ? ' sel' : ''), 'data-aid': aid, role: 'button',
                                   tabindex: '0', title: nameOf(a) + ' · ' + a.repo + (a.name ? '\n' + a.name : '') +
                                   '\nuses ' + n + ' config' + (n === 1 ? '' : 's') + ' - a click: only what it uses'},
                           h('span', {class: 'nm'}, a.alias), h('span', {class: 'tag'}), h('span', {class: 'n'}, String(n))));
        });
      });

    // the configs, the ones named at run time after them; each with the number of its keys the rows show
    cp.textContent = '';
    var named = data.configs.filter(function (c) { return !c.dynamic && c.name in cfgN; });
    var dyn = data.configs.filter(function (c) { return c.dynamic && c.name in cfgN; });
    function add(c) {
      cp.appendChild(h('div', {class: 'ccf-node' + (c.artifacts.length ? ' here' : '') + (st.cfg === c.name ? ' sel' : ''),
                               'data-cfg': c.name, role: 'button', tabindex: '0',
                               title: (c.desc || c.name) + (c.artifacts.length ? '\n(a config artifact of this machine)' : '') +
                                      '\na click: only this config and who uses it'},
                       h('span', {class: 'nm'}, c.name), h('span', {class: 'tag'}), h('span', {class: 'n'}, String(cfgN[c.name]))));
    }
    if (named.length) cp.appendChild(h('h4', {}, 'config'));
    named.forEach(add);
    if (dyn.length) cp.appendChild(h('h4', {}, 'named at run time'));
    dyn.forEach(add);
    if (!named.length && !dyn.length) cp.appendChild(h('div', {class: 'ccf-none ccf-pad'}, 'none'));
    if (!Object.keys(groups).length) ap.appendChild(h('div', {class: 'ccf-none ccf-pad'}, 'none'));
    ap.scrollTop = keepA;
    cp.scrollTop = keepC;
    // a new choice (from a card, from the address) is brought into view in its list, once: the lists keep the
    // reader's own scrolling otherwise
    var chosen = st.art + '|' + st.cfg;
    if (chosen !== revealed) {
      revealed = chosen;
      reveal(ap, ap.querySelector('.ccf-node.sel'));
      reveal(cp, cp.querySelector('.ccf-node.sel'));
    }

    $('ccf-n-arts').textContent = num(Object.keys(artN).filter(function (aid) { return ART[aid]; }).length);
    $('ccf-n-cfgs').textContent = num(named.length + dyn.length);

    // a line from each artifact shown to each config shown that it uses
    EDGES = [];
    Object.keys(artN).forEach(function (aid) {
      Object.keys(USES[aid] || {}).forEach(function (name) {
        if (name in cfgN) EDGES.push({id: aid + '|' + name, aid: aid, cfg: name, kind: edgeKind(USES[aid][name])});
      });
    });
    $('ccf-nav').setAttribute('data-pane', pane);
    schedule();
  }
  function reveal(p, node) {
    if (!node) return;
    var top = node.offsetTop - p.offsetTop, bottom = top + node.offsetHeight;
    if (top < p.scrollTop + 20 || bottom > p.scrollTop + p.clientHeight - 20)
      p.scrollTop = Math.max(0, top - p.clientHeight / 3);
  }
  function schedule() {
    if (frame) return;
    frame = requestAnimationFrame(function () { frame = 0; drawEdges(); });
  }
  // the lines between the two lists, for the rows in view (a row scrolled away: its line ends at the list's edge,
  // fainter)
  function drawEdges() {
    var svg = $('ccf-edges'), map = $('ccf-map');
    if (!svg || !data) return;
    if (getComputedStyle(svg).display === 'none') { applyFocus(); return; }
    var mr = map.getBoundingClientRect();
    var ap = $('ccf-arts'), cp = $('ccf-cfgs');
    var ar = ap.getBoundingClientRect(), cr = cp.getBoundingClientRect();
    var x1 = ar.right - mr.left + 2, x2 = cr.left - mr.left - 3, dx = (x2 - x1) * 0.6;
    function ys(p, attr) {
      var r = p.getBoundingClientRect(), top = r.top - mr.top + 3, bot = r.bottom - mr.top - 3, out = {};
      p.querySelectorAll('[' + attr + ']').forEach(function (n) {
        var b = n.getBoundingClientRect(), y = b.top + b.height / 2 - mr.top;
        out[n.getAttribute(attr)] = {y: Math.max(top, Math.min(bot, y)), out: y < top || y > bot};
      });
      return out;
    }
    var A = ys(ap, 'data-aid'), C = ys(cp, 'data-cfg');
    var parts = ['<defs>', ['reads', 'declares', 'docs'].map(function (k) {
      return '<marker id="ccf-ah-' + k + '" class="ah ' + k + '" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" ' +
             'markerHeight="7" markerUnits="userSpaceOnUse" orient="auto"><path d="M0,0 L8,4 L0,8 L2.5,4 Z"/></marker>';
    }).join(''), '</defs>'];
    EDGES.forEach(function (e) {
      var a = A[e.aid], c = C[e.cfg];
      if (!a || !c) return;
      var d = 'M' + x1.toFixed(1) + ',' + a.y.toFixed(1) + ' C' + (x1 + dx).toFixed(1) + ',' + a.y.toFixed(1) + ' ' +
              (x2 - dx).toFixed(1) + ',' + c.y.toFixed(1) + ' ' + x2.toFixed(1) + ',' + c.y.toFixed(1);
      parts.push('<g data-edge="' + esc(e.id) + '"><path class="hit" d="' + d + '"/><path class="e ' + e.kind +
                 (a.out || c.out ? ' out' : '') + '" d="' + d + '"/></g>');
    });
    svg.innerHTML = parts.join('');
    applyFocus();
  }
  // the focus: what the pointer is on, else what is chosen - its lines and their ends lit, with what goes between
  // them; the rest faded
  function applyFocus() {
    var map = $('ccf-map');
    if (!map || !data) return;
    var f = hover || ((st.art || st.cfg) ? {aid: st.art, cfg: st.cfg} : null);
    var litA = {}, litC = {}, litE = {};
    if (f) {
      EDGES.forEach(function (e) {
        var on = f.aid && f.cfg ? (e.aid === f.aid && e.cfg === f.cfg) : (f.aid ? e.aid === f.aid : e.cfg === f.cfg);
        if (on) { litE[e.id] = 1; litA[e.aid] = 1; litC[e.cfg] = 1; }
      });
      if (f.aid) litA[f.aid] = 1;
      if (f.cfg) litC[f.cfg] = 1;
    }
    map.classList.toggle('focus', !!f);
    map.querySelectorAll('[data-aid]').forEach(function (n) {
      var aid = n.getAttribute('data-aid'), lit = !!litA[aid];
      n.classList.toggle('lit', lit);
      pairBadge(n.querySelector('.tag'), aid, lit && f && f.cfg ? f.cfg : '');
    });
    map.querySelectorAll('[data-cfg]').forEach(function (n) {
      var name = n.getAttribute('data-cfg'), lit = !!litC[name];
      n.classList.toggle('lit', lit);
      pairBadge(n.querySelector('.tag'), lit && f && f.aid ? f.aid : '', name);
    });
    map.querySelectorAll('[data-edge]').forEach(function (g) {
      var on = !!litE[g.getAttribute('data-edge')];
      g.classList.toggle('lit', on);
      if (on) g.parentNode.appendChild(g);        // a lit line over the faded ones
    });
  }
  function focusOf(el) {
    var n = el && el.closest ? el.closest('[data-aid],[data-cfg],[data-edge]') : null;
    if (!n) return null;
    if (n.hasAttribute('data-aid')) return {aid: n.getAttribute('data-aid'), cfg: ''};
    if (n.hasAttribute('data-cfg')) return {aid: '', cfg: n.getAttribute('data-cfg')};
    var id = n.getAttribute('data-edge'), i = id.indexOf('|');
    return {aid: id.slice(0, i), cfg: id.slice(i + 1), edge: true};
  }
  function sameFocus(a, b) { return (!a && !b) || (a && b && a.aid === b.aid && a.cfg === b.cfg); }
  function edgeTag(f, ev) {
    var tag = $('ccf-edge-tag');
    if (!f || !f.edge || !ART[f.aid]) { tag.hidden = true; return; }
    var mr = $('ccf-map').getBoundingClientRect();
    tag.textContent = nameOf(ART[f.aid]) + ' → ' + f.cfg + ': ' + pairText(f.aid, f.cfg);
    tag.hidden = false;
    var x = Math.min(ev.clientX - mr.left + 12, mr.width - tag.offsetWidth - 4);
    tag.style.left = Math.max(4, x) + 'px';
    tag.style.top = (ev.clientY - mr.top + 14) + 'px';
  }
  function wireMap() {
    var map = $('ccf-map');
    map.addEventListener('mouseover', function (ev) {
      var f = focusOf(ev.target);
      if (!sameFocus(f, hover)) { hover = f; applyFocus(); }
    });
    map.addEventListener('mousemove', function (ev) { edgeTag(hover, ev); });
    map.addEventListener('mouseleave', function () { hover = null; applyFocus(); $('ccf-edge-tag').hidden = true; });
    map.addEventListener('click', function (ev) {
      var f = focusOf(ev.target);
      if (!f) return;
      $('ccf-edge-tag').hidden = true;
      if (f.edge) selectBoth(f.aid, f.cfg);
      else if (f.aid) selectArt(f.aid);
      else selectCfg(f.cfg);
    });
    map.addEventListener('keydown', function (ev) {
      if ((ev.key === 'Enter' || ev.key === ' ') && ev.target.matches('[data-aid],[data-cfg]')) {
        ev.preventDefault();
        ev.target.click();
      }
    });
    $('ccf-arts').addEventListener('scroll', schedule, {passive: true});
    $('ccf-cfgs').addEventListener('scroll', schedule, {passive: true});
    window.addEventListener('resize', schedule);
    document.querySelectorAll('.ccf-tab').forEach(function (b) {
      b.addEventListener('click', function () {
        pane = b.getAttribute('data-pane');
        try { localStorage.setItem(PANE_KEY, pane); } catch (e) { /* private mode */ }
        $('ccf-nav').setAttribute('data-pane', pane);
        schedule();
      });
    });
  }

  /* ------------------------------------------------------------------ the cards */
  function valueCell(k) {
    if (k.unread) return k.secret ? h('span', {class: 'ccf-val hidden'}, 'set (hidden)') : h('span', {class: 'ccf-val'}, String(k.value));
    if (!data.values) return h('span', {class: 'ccf-none'}, '');
    if (k.set && k.secret) return h('span', {class: 'ccf-val hidden', title: 'never shown: a secret'}, 'set (hidden)');
    if (k.set && k.value != null) return h('span', {class: 'ccf-val'}, String(k.value));
    if (k.children && k.children.length)
      return h('span', {class: 'ccf-val', title: k.children.map(function (x) { return x.key; }).join('\n')},
               k.children.length + ' set under it');
    return h('span', {class: 'ccf-none'}, 'not set');
  }
  function readersCell(k) {
    var cell = h('td', {class: 'r ccf-readers-cell'});
    var list = k.readers.length ? k.readers : (k.declared.length ? k.declared : k.docs);
    var label = k.readers.length ? '' : (k.declared.length ? 'declared: ' : (k.docs.length ? 'shown in: ' : ''));
    if (label) cell.appendChild(document.createTextNode(label));
    list.slice(0, 3).forEach(function (x, i) {
      var a = ART[x.aid];
      if (!a) return;
      if (i) cell.appendChild(document.createTextNode(', '));
      var b = h('button', {type: 'button', class: 'ccf-pick' + (st.art === x.aid ? ' sel' : ''),
                           title: nameOf(a) + ' · ' + a.repo + '\na click: only what it uses'}, a.alias);
      b.addEventListener('click', function (ev) { ev.stopPropagation(); selectArt(x.aid); });
      cell.appendChild(b);
    });
    if (list.length > 3) cell.appendChild(document.createTextNode(' +' + (list.length - 3)));
    return cell;
  }
  function keyRow(c, k, unread) {
    var id = c.name + '\n' + k.key;
    var tr = h('tr', {class: 'ccf-row' + (isPattern(k.key) ? ' dynamic' : '') + (opened[id] ? ' open' : '')});
    var kc = h('td', {class: 'k'}, h('code', {}, k.key));
    (k.sources || []).forEach(function (s) {
      kc.appendChild(h('span', {class: 'ccf-src ' + s, title: SRC_TITLE[s]}, SRC[s]));
    });
    if (k.secret) kc.appendChild(h('span', {class: 'ccf-chip ccf-lock', title: 'a secret: its value is never shown'}, 'secret'));
    var dc = h('td', {class: 'd'});
    if (unread) dc.appendChild(h('span', {class: 'ccf-none'}, 'no plugged artifact reads it' + (k.every ? ' by name (one reads every key of this config)' : '')));
    else if (k.desc) dc.appendChild(h('div', {html: rich(k.desc)}));
    else dc.appendChild(h('span', {class: 'ccf-none'}, 'nothing says what it does'));
    var sub = [];
    if (k.type) sub.push(k.type);
    if (k.defaults && k.defaults.length) sub.push('default: ' + k.defaults.join(' | '));
    if (sub.length) dc.appendChild(h('div', {class: 'ccf-sub2'}, sub.join(' · ')));
    tr.appendChild(kc);
    tr.appendChild(dc);
    tr.appendChild(h('td', {class: 'v'}, valueCell(unread ? Object.assign({unread: true}, k) : k)));
    tr.appendChild(unread ? h('td', {class: 'r ccf-readers-cell'}, '') : readersCell(k));
    tr.addEventListener('click', function (ev) {
      if (ev.target.closest('a,button')) return;
      opened[id] = !opened[id];
      st.open = opened[id] ? c.name + '::' + k.key : '';
      writeUrl();
      render();
    });
    return tr;
  }
  function refList(aid, refs) {
    var a = ART[aid];
    var li = h('li', {});
    var chip = artChip(aid);
    if (chip) li.appendChild(chip);
    (refs || []).slice(0, 6).forEach(function (r) {
      var href = crefHref(a, r[0]);
      li.appendChild(document.createTextNode(' '));
      li.appendChild(href ? h('a', {href: href, class: 'ccf-from', title: 'open the file'}, r[0] + ':' + r[1])
                          : h('span', {class: 'ccf-from'}, r[0] + ':' + r[1]));
    });
    return li;
  }
  function detailRow(c, k, unread) {
    var td = h('td', {colspan: '4'});
    var grid = h('div', {class: 'ccf-dgrid'});
    var left = h('div', {}), right = h('div', {});
    if (!unread && k.descs && k.descs.length) {
      left.appendChild(h('h4', {}, 'What it does'));
      var ul = h('ul', {});
      k.descs.forEach(function (d) {
        var li = h('li', {html: rich(d.text) + ' '});
        var a = ART[d.aid];
        var where = (FROM[d.from] || 'from') + ' ' + (a ? nameOf(a) : '') + (d.file ? ' (' + d.file + (d.line ? ':' + d.line : '') + ')' : '');
        var href = a ? crefHref(a, d.file) : '';
        li.appendChild(href ? h('a', {class: 'ccf-from', href: href}, '— ' + where) : h('span', {class: 'ccf-from'}, '— ' + where));
        ul.appendChild(li);
      });
      left.appendChild(ul);
    }
    if (!unread) {
      [['Read by', k.readers], ['Declared by', k.declared], ['Shown in', k.docs]].forEach(function (part) {
        if (!part[1] || !part[1].length) return;
        left.appendChild(h('h4', {}, part[0]));
        var ul2 = h('ul', {});
        part[1].forEach(function (x) { ul2.appendChild(refList(x.aid, x.refs)); });
        left.appendChild(ul2);
      });
      if (k.examples && k.examples.length) {
        left.appendChild(h('h4', {}, 'Examples'));
        var ul3 = h('ul', {});
        k.examples.forEach(function (x) {
          var a = ART[x.aid];
          var li = h('li', {}, h('span', {class: 'ccf-kv'}, (x.sub ? k.key + '.' + x.sub : k.key) + ' = ' + x.value));
          if (a) li.appendChild(h('span', {class: 'ccf-from'}, ' — ' + a.alias + (x.file ? ' (' + x.file + ':' + x.line + ')' : '')));
          ul3.appendChild(li);
        });
        left.appendChild(ul3);
      }
    }
    if (k.children && k.children.length && data.values) {
      right.appendChild(h('h4', {}, 'Set under it here'));
      var ul4 = h('ul', {});
      k.children.forEach(function (x) {
        ul4.appendChild(h('li', {}, h('span', {class: 'ccf-kv'}, x.key + ' = ' + (x.secret ? '(hidden)' : x.value))));
      });
      right.appendChild(ul4);
    }
    right.appendChild(h('h4', {}, 'Change it'));
    right.appendChild(cmdBlock(commands(c, unread ? Object.assign({unread: true}, k) : k)));
    if (isPattern(k.key))
      right.appendChild(h('div', {class: 'ccf-from'}, 'The parts in <...> are named by the code at run time: put the name you need there.'));
    if (k.secret)
      right.appendChild(h('div', {class: 'ccf-from'}, 'A secret: set it on the machine itself - a value typed on the command line stays in the shell\'s history.'));
    grid.appendChild(left);
    grid.appendChild(right);
    td.appendChild(grid);
    return h('tr', {class: 'ccf-detail'}, td);
  }
  function configCard(c, list) {
    var sec = h('section', {class: 'ccf-cfg' + (st.cfg === c.name ? ' sel' : ''), id: 'cfg-' + c.name});
    var head = h('div', {class: 'ccf-cfg-head'});
    var title = h('button', {type: 'button', class: 'ccf-cfg-pick', title: st.cfg === c.name ? 'all the configs again' :
                             'only this config and who uses it'}, h('span', {class: 'kw'}, 'config::'), c.name);
    title.addEventListener('click', function () { selectCfg(c.name); });
    head.appendChild(h('h2', {}, title));
    if (c.artifacts.length) {
      var a0 = c.artifacts[0];
      head.appendChild(h('span', {class: 'ccf-chip ok', title: 'a config artifact of this machine'},
                         'here · ' + c.artifacts.map(function (a) { return a.repo; }).join(', ') +
                         (data.values ? ' · ' + a0.keys + ' key' + (a0.keys === 1 ? '' : 's') +
                          (a0.kept_in !== 'data.json' ? ' in its ' + a0.kept_in : '') : '')));
    } else if (!c.dynamic && data.values) head.appendChild(h('span', {class: 'ccf-chip'}, 'not set here'));
    if (c.unread && c.unread.length)
      head.appendChild(h('span', {class: 'ccf-chip warn', title: 'set here, read by no plugged artifact'}, c.unread.length + ' read by none'));
    var acts = h('span', {class: 'acts'});
    if (!c.dynamic) {
      var b = h('button', {type: 'button', class: 'ccf-copy', title: 'copy'}, 'cx config show ' + c.name);
      b.addEventListener('click', function () { copyText('cx config show ' + quoteArg(c.name), b); });
      acts.appendChild(b);
    }
    if (c.data_file && CFG.cref_url) {
      var df = c.data_file;
      acts.appendChild(h('a', {href: crefHref({cat: 'config', alias: df.alias, uid: df.uid}, df.file),
                               title: 'where its values are (editable there, on this machine)'}, df.file || 'its page'));
    }
    head.appendChild(acts);
    sec.appendChild(head);
    if (c.desc) sec.appendChild(h('p', {class: 'ccf-desc', html: rich(c.desc)}));
    else if (c.dynamic) sec.appendChild(h('p', {class: 'ccf-desc'}, 'A config the code names at run time (' + c.name + '): which one depends on the call.'));

    // who uses it: the chosen artifact first; a long list folded after READERS_SHOWN (and to the chosen one alone)
    var readers = (c.readers || []).filter(function (r) { return ART[r.aid]; });
    if (st.art) readers.sort(function (x, y) { return (y.aid === st.art) - (x.aid === st.art); });
    if (readers.length) {
      var rd = h('div', {class: 'ccf-readers'}, 'Used by ');
      var whole = wholeReaders[c.name] || readers.length <= READERS_SHOWN + 2;
      var chosenFirst = st.art && readers[0].aid === st.art;
      var count = whole ? readers.length : (chosenFirst ? 1 : READERS_SHOWN);
      readers.slice(0, count).forEach(function (r) {
        var how = [];
        if (r.every && r.every.indexOf('') >= 0) how.push('every key');          // the whole config, not one dict in it
        if (r.how.indexOf('run time') >= 0) how.push('keys it names at run time');
        if (r.how.indexOf('write') >= 0) how.push('writes');
        if (r.how.length === 1 && r.how[0] === 'declared') how.push('declares');
        var e = artChip(r.aid, how.join(', '));
        if (e) rd.appendChild(e);
      });
      if (!whole) {
        var more = h('button', {type: 'button', class: 'ccf-link ccf-more'}, 'and ' + (readers.length - count) + ' more');
        more.addEventListener('click', function () { wholeReaders[c.name] = true; render(); });
        rd.appendChild(more);
      }
      sec.appendChild(rd);
    }
    // and those that only show its keys in their docs (the dotted lines of the map)
    var users = {};
    readers.forEach(function (r) { users[r.aid] = 1; });
    var shownIn = Object.keys(USES).filter(function (aid) { return ART[aid] && !users[aid] && USES[aid][c.name]; })
      .sort(byText(function (aid) { return nameOf(ART[aid]).toLowerCase(); }));
    if (shownIn.length) {
      var sd = h('div', {class: 'ccf-readers'}, 'Also shown in the docs of ');
      shownIn.forEach(function (aid) { var e = artChip(aid, pairText(aid, c.name)); if (e) sd.appendChild(e); });
      sec.appendChild(sd);
    }
    if (c.artifacts.length && data.values && c.artifacts[0].files && c.artifacts[0].files.length)
      sec.appendChild(h('div', {class: 'ccf-readers'}, 'Its folder also holds: ' + c.artifacts[0].files.join(', ')));
    if (st.art && USES[st.art] && USES[st.art][c.name] && !USES[st.art][c.name].keys.length)
      sec.appendChild(h('div', {class: 'ccf-readers'}, nameOf(ART[st.art]) + ': ' + pairText(st.art, c.name) +
                        ' - no key of it found in its code'));

    var keys = list.filter(function (r) { return r.k && !r.unread; });
    var unread = list.filter(function (r) { return r.unread; });
    if (keys.length) {
      var table = h('table', {class: 'ccf-keys'});
      table.appendChild(h('thead', {}, h('tr', {}, h('th', {class: 'k'}, 'Key'), h('th', {class: 'd'}, 'What it does'),
                                           h('th', {class: 'v'}, data.values ? 'Here' : 'Value'), h('th', {class: 'r'}, 'Read by'))));
      var tb = h('tbody', {});
      keys.forEach(function (r) {
        tb.appendChild(keyRow(c, r.k, false));
        if (opened[c.name + '\n' + r.k.key]) tb.appendChild(detailRow(c, r.k, false));
      });
      table.appendChild(tb);
      sec.appendChild(table);
    }
    if (unread.length) {
      var box = h('div', {class: 'ccf-unread'}, h('h3', {}, 'Set here, read by no plugged artifact (' + unread.length + ')' +
        (unread[0].k.every ? ' - an artifact reads every key of this config: it may pass them on' : '')));
      var t2 = h('table', {});
      unread.forEach(function (r) {
        var u = r.k;
        var line = 'cx config unset ' + quoteArg(c.name) + ' ' + quoteArg('--meta.' + u.key);
        var b2 = h('button', {type: 'button', class: 'ccf-copy', title: line}, 'copy unset');
        b2.addEventListener('click', function () { copyText(line, b2); });
        t2.appendChild(h('tr', {}, h('td', {class: 'k'}, h('code', {}, u.key)),
                         h('td', {class: 'c'}, u.secret ? h('span', {class: 'ccf-val hidden'}, '(hidden)') : h('span', {class: 'ccf-val'}, String(u.value))),
                         h('td', {}, b2)));
      });
      box.appendChild(t2);
      sec.appendChild(box);
    }
    return sec;
  }
  // what is chosen in the map, on top of the cards: the artifact with the configs it uses, or the config with the
  // artifacts that use it, or both; each with its x
  function selectionCard() {
    var box = h('section', {class: 'ccf-selcard'});
    function close(what, fn) {
      var b = h('button', {type: 'button', class: 'ccf-x', title: 'let go of ' + what + ' (Esc: of both)'}, '×');
      b.addEventListener('click', fn);
      return b;
    }
    if (st.art && ART[st.art]) {
      var a = ART[st.art], uses = USES[st.art] || {};
      var head = h('div', {class: 'ccf-sel-head'}, h('span', {class: 'ccf-sel-kind'}, 'artifact'),
                   h('b', {class: 'ccf-sel-name'}, nameOf(a)), h('span', {class: 'ccf-chip'}, a.repo));
      var href = crefHref(a);
      if (href) head.appendChild(h('a', {href: href, class: 'ccf-open', title: 'its page'}, 'its page ↗'));
      head.appendChild(close(nameOf(a), function () { selectArt(st.art); }));
      box.appendChild(head);
      if (a.name) box.appendChild(h('p', {class: 'ccf-desc'}, a.name));
      var names = Object.keys(uses).sort(byText(function (n) { return (n.charAt(0) === '<' ? '~' : '') + n.toLowerCase(); }));
      var line = h('div', {class: 'ccf-sel-uses'}, 'Uses ' + names.length + ' config' + (names.length === 1 ? '' : 's') + ': ');
      names.forEach(function (n) {
        var u = uses[n];
        var b = h('button', {type: 'button', class: 'ccf-cfgchip' + (st.cfg === n ? ' sel' : ''),
                             title: (u.keys.length ? u.keys.join('\n') + '\n' : '') + (st.cfg === n ? 'all its configs again' : 'only this one')},
                  n + ' ', h('span', {class: 'n'}, pairText(st.art, n)));
        b.addEventListener('click', function () { selectCfg(n); });
        line.appendChild(b);
      });
      box.appendChild(line);
    }
    if (st.cfg && BY_NAME[st.cfg]) {
      var c = BY_NAME[st.cfg];
      if (!st.art) {
        box.appendChild(h('div', {class: 'ccf-sel-head'}, h('span', {class: 'ccf-sel-kind'}, 'config'),
                          h('b', {class: 'ccf-sel-name'}, c.name), close(c.name, function () { selectCfg(st.cfg); })));
        var users = (c.readers || []).map(function (r) { return r.aid; }).filter(function (aid) { return ART[aid]; });
        var line2 = h('div', {class: 'ccf-sel-uses'}, 'Used by ' + users.length + ' artifact' + (users.length === 1 ? '' : 's') + ': ');
        users.sort(byText(function (aid) { return nameOf(ART[aid]).toLowerCase(); })).forEach(function (aid) {
          var chip = artChip(aid, pairText(aid, c.name));
          if (chip) line2.appendChild(chip);
        });
        box.appendChild(line2);
      } else {
        box.appendChild(h('div', {class: 'ccf-sel-head small'}, h('span', {class: 'ccf-sel-kind'}, 'in config'),
                          h('b', {class: 'ccf-sel-name'}, c.name), h('span', {class: 'ccf-from'}, pairText(st.art, c.name)),
                          close(c.name, function () { selectCfg(st.cfg); })));
      }
    }
    return box;
  }
  function renderConfigs(kept) {
    var main = $('ccf-list');
    main.textContent = '';
    if (st.art || st.cfg) main.appendChild(selectionCard());
    var by = {};
    kept.forEach(function (r) { (by[r.c.name] = by[r.c.name] || []).push(r); });
    // a config the chosen artifact uses without a key of it known (as a whole, under names of its own): its card
    // too, unless a search or a pill narrows the cards
    if (st.art && !st.q && !st.show) Object.keys(USES[st.art] || {}).forEach(function (n) {
      if (BY_NAME[n] && !by[n] && !USES[st.art][n].keys.length && (!st.cfg || st.cfg === n)) by[n] = [];
    });
    if (st.cfg && BY_NAME[st.cfg] && !by[st.cfg] && !st.art) by[st.cfg] = [];
    var shown = data.configs.filter(function (c) { return by[c.name]; });
    if (!shown.length) { main.appendChild(h('div', {class: 'ccf-empty'}, 'No key holds all of that.')); return; }
    shown.forEach(function (c) { main.appendChild(configCard(c, by[c.name])); });
  }
  function renderRepos(kept) {
    var main = $('ccf-list');
    main.textContent = '';
    var repos = {};
    function note(aid, config, key) {
      var a = ART[aid];
      if (!a) return;
      var rp = repos[a.repo] = repos[a.repo] || {};
      var art = rp[aid] = rp[aid] || {};
      var keys = art[config] = art[config] || {};
      if (key) keys[key] = 1;
    }
    var configs = {};
    kept.forEach(function (r) {
      configs[r.c.name] = r.c;
      if (!r.k || r.unread) return;
      r.k.readers.concat(r.k.declared, r.k.docs).forEach(function (x) { note(x.aid, r.c.name, r.k.key); });
    });
    // and who uses a config of those whole, or under names of its own choosing (no key of it known)
    Object.keys(configs).forEach(function (name) {
      (configs[name].readers || []).forEach(function (x) { note(x.aid, name, ''); });
    });
    var names = Object.keys(repos).sort(byText(function (x) { return x.toLowerCase(); }));
    if (!names.length) { main.appendChild(h('div', {class: 'ccf-empty'}, 'No artifact reads a key that holds all of that.')); return; }
    names.forEach(function (rname) {
      var arts = repos[rname];
      var aids = Object.keys(arts).sort(byText(function (aid) { return nameOf(ART[aid]); }));
      var sec = h('section', {class: 'ccf-repo'}, h('h2', {}, rname || '(no repository) ',
                  h('span', {class: 'n'}, ' · ' + aids.length + ' artifact' + (aids.length === 1 ? '' : 's'))));
      aids.forEach(function (aid) {
        var cfgs = h('div', {class: 'cfgs'});
        Object.keys(arts[aid]).sort().forEach(function (name) {
          var n = Object.keys(arts[aid][name]).length;
          var chip = h('button', {type: 'button', class: 'ccf-cfgchip', title: Object.keys(arts[aid][name]).sort().join('\n') +
                                  '\na click: what ' + nameOf(ART[aid]) + ' uses of it'},
                       name + ' ', h('span', {class: 'n'}, String(n)));
          chip.addEventListener('click', function () { selectBoth(aid, name); });
          cfgs.appendChild(chip);
        });
        sec.appendChild(h('div', {class: 'ccf-repo-art'}, h('div', {}, artChip(aid) || ''), cfgs));
      });
      main.appendChild(sec);
    });
  }
  function renderStatus(kept) {
    var s = data.stats || {};
    var el = $('ccf-status');
    el.innerHTML = '<b>' + num(s.configs) + '</b> config artifacts · <b>' + num(s.keys) + '</b> keys' +
      (data.values ? ' · <b>' + num(s.set) + '</b> set here · <b>' + num(s.unread) + '</b> set here that nothing reads' : '') +
      ' · used by <b>' + num(s.readers) + '</b> artifacts of <b>' + num(s.repos) + '</b> repositories' +
      (kept.length !== rows.length ? ' · <b>' + num(kept.filter(function (r) { return r.k; }).length) + '</b> shown' : '') +
      ' <span title="' + esc('files looked at: ' + s.files + ', read: ' + s.read + ', parsed: ' + s.parsed + '; built ' + data.built) +
      '">— ' + num(s.files) + ' files of ' + num(s.artifacts) + ' artifacts, ' + msText(s.ms || 0) +
      (s.read ? ' (' + num(s.read) + ' read)' : ' (none changed)') + '</span>';
  }
  function renderNotices() {
    var box = $('ccf-notices');
    box.textContent = '';
    if (!data.values)
      box.appendChild(h('div', {}, 'The values set on this server are shown to its own machine only (or past its password; ' +
                                    'configs_values in the cserver config says otherwise): here, the keys and who uses them.'));
    (data.problems || []).concat(CFG.problems || []).forEach(function (p) { box.appendChild(h('div', {class: 'warn'}, p)); });
    if (data.errors && data.errors.length)
      box.appendChild(h('div', {class: 'warn', title: data.errors.join('\n')},
                        data.errors.length + ' file(s) could not be read as Python or YAML: their docs lines still count (hover for the list)'));
  }
  function renderPills() {
    var base = filtered(false, true);
    document.querySelectorAll('.ccf-view').forEach(function (b) {
      var s = b.getAttribute('data-show');
      // what is set here is for a viewer who may see this machine's values
      b.hidden = !data.values && ['set', 'unset', 'unread'].indexOf(s) >= 0;
      b.classList.toggle('on', s === st.show);
      var n = s ? base.filter(function (r) { return r.k && r.is[s]; }).length : base.filter(function (r) { return r.k; }).length;
      b.querySelector('.n').textContent = num(n);
    });
    document.querySelectorAll('.ccf-mode').forEach(function (b) {
      b.classList.toggle('on', b.getAttribute('data-view') === st.view);
    });
  }
  function render() {
    if (!data) return;
    var kept = filtered(true, true);
    renderPills();
    renderStatus(kept);
    renderMap(filtered(true, false));
    if (st.view === 'repos') renderRepos(kept);
    else renderConfigs(kept);
    $('ccf-expand').textContent = Object.keys(opened).some(function (k) { return opened[k]; }) ? 'close all' : 'open all';
  }

  /* ------------------------------------------------------------------ the address, the controls */
  function writeUrl() {
    var u = new URL(window.location.href);
    URL_KEYS.forEach(function (k) { if (st[k]) u.searchParams.set(k, st[k]); else u.searchParams.delete(k); });
    window.history.replaceState(null, '', u.toString());
    $('ccf-json').href = apiUrl('configs');
  }
  function fillRepos() {
    var sel = $('ccf-repo');
    sel.textContent = '';
    sel.appendChild(h('option', {value: ''}, 'all'));
    (data.repos || []).forEach(function (r) {
      var o = h('option', {value: r[0]}, r[0] + ' (' + r[1] + ')');
      if (r[0] === st.repo) o.selected = true;
      sel.appendChild(o);
    });
  }
  // an artifact named in the address: its aid (category UID::artifact UID, as the page writes it), or
  // <category>::<alias> (as one types it)
  function resolveArt(v) {
    if (!v || ART[v]) return v;
    var low = v.toLowerCase();
    var hit = Object.keys(ART).filter(function (aid) { return nameOf(ART[aid]).toLowerCase() === low; });
    return hit.length === 1 ? hit[0] : '';
  }
  function load(refresh) {
    showError('');
    busy(true, refresh ? 'looking at the artifacts again' : 'reading the artifacts (the first time: every file, some seconds)');
    return call('configs', refresh ? {refresh: 1} : {}).then(function (d) {
      data = d;
      ART = d.artifacts || {};
      USES = d.uses || {};
      BY_NAME = {};
      d.configs.forEach(function (c) { BY_NAME[c.name] = c; });
      if (!d.values && ['set', 'unset', 'unread'].indexOf(st.show) >= 0) st.show = '';
      st.art = resolveArt(st.art);
      if (st.cfg && !BY_NAME[st.cfg]) st.cfg = '';
      writeUrl();
      buildRows();
      fillRepos();
      renderNotices();
      if (st.open && !Object.keys(opened).length) {
        var i = st.open.indexOf('::');
        if (i > 0) opened[st.open.slice(0, i) + '\n' + st.open.slice(i + 2)] = true;
      }
      render();
      if (st.open) {
        var t = document.querySelector('.ccf-row.open');
        if (t) t.scrollIntoView({block: 'center'});
      }
    }).catch(function (e) {
      showError('The configs could not be read: ' + e.message);
    }).then(function () { busy(false); });
  }

  $('ccf-form').addEventListener('submit', function (ev) {
    ev.preventDefault();
    st.q = $('ccf-q').value.trim();
    writeUrl();
    render();
  });
  var typing = null;
  $('ccf-q').addEventListener('input', function () {
    clearTimeout(typing);
    typing = setTimeout(function () { st.q = $('ccf-q').value.trim(); writeUrl(); render(); }, 200);
  });
  document.querySelectorAll('.ccf-view').forEach(function (b) {
    b.addEventListener('click', function () { st.show = b.getAttribute('data-show'); writeUrl(); render(); });
  });
  document.querySelectorAll('.ccf-mode').forEach(function (b) {
    b.addEventListener('click', function () { st.view = b.getAttribute('data-view'); writeUrl(); render(); });
  });
  $('ccf-repo').addEventListener('change', function () { st.repo = $('ccf-repo').value; writeUrl(); render(); });
  $('ccf-help-btn').addEventListener('click', function () { $('ccf-help').hidden = !$('ccf-help').hidden; });
  $('ccf-howto-btn').addEventListener('click', function () { $('ccf-howto').hidden = !$('ccf-howto').hidden; });
  $('ccf-refresh').addEventListener('click', function () { load(true); });
  $('ccf-expand').addEventListener('click', function () {
    var any = Object.keys(opened).some(function (k) { return opened[k]; });
    opened = {};
    if (!any) filtered(true, true).slice(0, 400).forEach(function (r) { if (r.k && !r.unread) opened[r.c.name + '\n' + r.k.key] = true; });
    st.open = '';
    writeUrl();
    render();
  });
  document.addEventListener('keydown', function (ev) {
    var typingHere = /^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement || {}).tagName || '');
    if (ev.key === '/' && !typingHere) {
      ev.preventDefault();
      $('ccf-q').focus();
    } else if (ev.key === 'Escape' && !typingHere) {
      if (release()) ev.preventDefault();
    }
  });
  wireMap();

  /* ------------------------------------------------------------------ the theme */
  function setDark(on) { root.classList.toggle('dark', !!on); }
  if (CFG.hosted) {
    // inside the cPlatform's shell: its theme, live; no switch of our own
    root.classList.add('hosted');
    $('ccf-theme').hidden = true;
    var html = document.documentElement;
    var follow = function () {
      var t = html.getAttribute('data-ctp-theme');
      setDark(t ? t === 'dark' : CFG.dark_mode === true);
    };
    follow();
    new MutationObserver(follow).observe(html, {attributes: true, attributeFilter: ['data-ctp-theme']});
  } else {
    var saved = null;
    try { saved = localStorage.getItem(THEME_KEY); } catch (e) { saved = null; }
    setDark(saved ? saved === 'dark' : CFG.dark_mode === true);
    $('ccf-theme').addEventListener('click', function () {
      var on = !root.classList.contains('dark');
      setDark(on);
      try { localStorage.setItem(THEME_KEY, on ? 'dark' : 'light'); } catch (e) { /* private mode */ }
    });
  }

  if (CFG.settings_url) {
    var line = $('ccf-settings-line');
    line.innerHTML = 'What it reads: <a href="' + esc(CFG.settings_url) + '"><code>files/configs.yaml</code></a> of ' +
      '<code>cserver.cmeta.configs</code>, and a <code>configs</code> block in the <code>_desc.yaml</code> of any artifact';
  }
  $('ccf-q').value = st.q;
  writeUrl();
  load(false);
})();
