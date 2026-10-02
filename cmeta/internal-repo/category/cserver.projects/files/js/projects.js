/* Licensed under the Apache License, Version 2.0. See the COPYRIGHT and LICENSE files in the project root for details.
   cserver.projects - fetches ?native_action=projects and renders the cards. No dependency: the hosts serve
   cmeta_server.js with accessCT(), but a plain fetch keeps the page working when that script is absent. */

(function () {
  'use strict';

  var CFG = (typeof CONFIG !== 'undefined') ? CONFIG : {};
  var PIN_KEY = 'cserver.projects.pins';
  var THEME_KEY = 'cserver.projects.theme';
  var DATA = { pages: [], others: [], repos: [] };

  function $(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s === undefined || s === null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  /* The JSON endpoint of this page; ?repo=<text> of the page URL travels with it. */
  function apiUrl() {
    var url = (CFG.api_url || '?') + 'native_action=projects';
    return CFG.repo ? url + '&repo=' + encodeURIComponent(CFG.repo) : url;
  }

  /* ---------------------------------------------------------------- pins */
  function pins() {
    try { return JSON.parse(localStorage.getItem(PIN_KEY) || '[]'); } catch (e) { return []; }
  }
  function setPins(list) {
    try { localStorage.setItem(PIN_KEY, JSON.stringify(list)); } catch (e) { /* private mode */ }
  }
  function togglePin(alias) {
    var list = pins(), i = list.indexOf(alias);
    if (i < 0) { list.push(alias); } else { list.splice(i, 1); }
    setPins(list);
    render($('cpj-search').value);
  }

  /* --------------------------------------------------------------- theme */
  function applyTheme(dark) {
    var root = $('cpj');
    root.classList.toggle('dark', !!dark);
    /* The host's <body> keeps its margin; paint it in the page's own background so no light strip is left
       at the top in dark mode (and give the host its colour back in light mode). */
    document.body.style.backgroundColor = dark ? getComputedStyle(root).getPropertyValue('--cpj-bg').trim() : '';
  }
  function initTheme() {
    var stored = null;
    try { stored = localStorage.getItem(THEME_KEY); } catch (e) { /* ignore */ }
    applyTheme(stored ? stored === 'dark' : !!CFG.dark_mode);
  }
  function toggleTheme() {
    var dark = !$('cpj').classList.contains('dark');
    applyTheme(dark);
    try { localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light'); } catch (e) { /* ignore */ }
  }

  /* ---------------------------------------------------------------- data */
  function load() {
    var url = apiUrl();
    var groups = $('cpj-groups');
    groups.innerHTML = '<p class="cpj-muted">Scanning the index ...</p>';
    var p;
    if (typeof accessCT === 'function') {
      p = accessCT(url, {});
    } else {
      p = fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}'
      }).then(function (r) { return r.json(); });
    }
    return p.then(function (out) {
      if (!out || out.error) { fail((out && out.error) || 'empty answer'); return; }
      DATA = { pages: out.pages || [], others: out.others || [], repos: out.repos || [] };
      $('cpj-error').hidden = true;
      render($('cpj-search').value);
    }).catch(function (e) { fail(String(e)); });
  }

  function fail(msg) {
    var box = $('cpj-error');
    box.textContent = 'Could not load the page list: ' + msg;
    box.hidden = false;
    $('cpj-groups').innerHTML = '';
  }

  /* -------------------------------------------------------------- render */
  function matches(p, q) {
    if (!q) { return true; }
    var hay = [p.page, p.alias, p.name, p.desc, p.repo, (p.tags || []).join(' ')].join(' ').toLowerCase();
    return q.toLowerCase().split(/\s+/).every(function (w) { return !w || hay.indexOf(w) >= 0; });
  }

  /* A category's name is a free-text line: "My page - what it shows ...", "The course pages ...: /my.course",
     or absent. Split it into a short heading and the rest; when no short heading can be found, the page alias is
     the heading and the whole line becomes the description. */
  function split(p) {
    var name = (p.name || '').trim();
    if (!name) { return { title: p.page, desc: p.desc || '' }; }
    var cut = -1, sep = 0;
    [' - ', ': ', ' – '].forEach(function (s) {
      var i = name.indexOf(s);
      if (i > 0 && (cut < 0 || i < cut)) { cut = i; sep = s.length; }
    });
    var head = cut > 0 ? name.slice(0, cut) : name;
    var rest = cut > 0 ? name.slice(cut + sep) : '';
    if (head.length > 48) { return { title: p.page, desc: p.desc || name }; }
    return { title: head, desc: p.desc || rest };
  }

  function card(p, pinned) {
    var s = split(p), title = s.title, desc = s.desc;
    var meta = ['<span class="cpj-repo">' + esc(p.repo || 'local') + '</span>'];
    if (p.updated) { meta.push('<span>' + esc(p.updated) + '</span>'); }
    return '' +
      '<div class="cpj-card" data-alias="' + esc(p.alias) + '">' +
        '<div class="cpj-acts">' +
          '<button class="cpj-act cpj-pin' + (pinned ? ' cpj-on' : '') + '" type="button" title="Pin to the top">' +
            (pinned ? '★' : '☆') + '</button>' +
          '<button class="cpj-act cpj-copy" type="button" title="Copy the URL">⧉</button>' +
        '</div>' +
        '<a class="cpj-link" href="' + esc(p.href) + '"><h3>' + esc(title) + '</h3></a>' +
        '<div class="cpj-alias">/' + esc(p.page) + '</div>' +
        (desc ? '<p class="cpj-desc">' + esc(desc) + '</p>' : '') +
        '<div class="cpj-meta">' + meta.join('') + '</div>' +
      '</div>';
  }

  function group(title, items, n) {
    return '<section class="cpj-group"><h2>' + esc(title) +
      '<span class="cpj-n">' + n + '</span></h2><div class="cpj-cards">' + items.join('') + '</div></section>';
  }

  function render(q) {
    q = (q || '').trim();
    var pinned = pins();
    var none = DATA.pages.length === 0;
    var shown = DATA.pages.filter(function (p) { return matches(p, q); });
    var html = [];

    var pin = shown.filter(function (p) { return pinned.indexOf(p.alias) >= 0; });
    if (pin.length) {
      html.push(group('Pinned', pin.map(function (p) { return card(p, true); }), pin.length));
    }

    var rest = shown.filter(function (p) { return pinned.indexOf(p.alias) < 0; });
    DATA.repos.forEach(function (repo) {
      var items = rest.filter(function (p) { return (p.repo || '') === repo; });
      if (items.length) {
        html.push(group(repo || 'local', items.map(function (p) { return card(p, false); }), items.length));
      }
    });

    /* No page at all (a fresh install): say what a page is instead of an empty grid. */
    $('cpj-empty').hidden = !none;
    $('cpj-groups').innerHTML = html.length ? html.join('') :
      (none ? '' : '<p class="cpj-muted">No page matches <code>' + esc(q) + '</code>.</p>');

    $('cpj-count').textContent = none ? '' : (q
      ? '(' + shown.length + ' of ' + DATA.pages.length + ' shown)'
      : '(' + DATA.pages.length + (DATA.pages.length === 1 ? ' page)' : ' pages)'));

    var others = DATA.others || [];
    $('cpj-others').hidden = others.length === 0;
    $('cpj-others-count').textContent = others.length;
    $('cpj-others-list').innerHTML = others.map(function (p) {
      return '<li><code>' + esc(p.alias) + '</code> - ' + esc(p.repo) +
        (p.name ? ' - ' + esc(p.name.split(' - ')[0]) : '') + '</li>';
    }).join('');

    var first = $('cpj-groups').querySelector('.cpj-card');
    if (first && q) { first.classList.add('cpj-hit'); }
  }

  /* --------------------------------------------------------------- wire */
  function copyUrl(alias, btn) {
    var p = DATA.pages.concat(DATA.others).filter(function (x) { return x.alias === alias; })[0];
    if (!p) { return; }
    var abs = new URL(p.href, window.location.href).href;
    var done = function () {
      var old = btn.textContent;
      btn.textContent = '✓';
      setTimeout(function () { btn.textContent = old; }, 900);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(abs).then(done, function () { window.prompt('Copy the URL:', abs); });
    } else {
      window.prompt('Copy the URL:', abs);
    }
  }

  function init() {
    initTheme();

    $('cpj-json').href = apiUrl();

    $('cpj-search').addEventListener('input', function () { render(this.value); });
    $('cpj-search').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        var a = $('cpj-groups').querySelector('.cpj-card .cpj-link');
        if (a) { window.location.href = a.getAttribute('href'); }
      } else if (e.key === 'Escape') {
        this.value = '';
        render('');
      }
    });

    $('cpj-theme').addEventListener('click', toggleTheme);
    $('cpj-reload').addEventListener('click', load);

    $('cpj-groups').addEventListener('click', function (e) {
      var pinBtn = e.target.closest('.cpj-pin');
      var copyBtn = e.target.closest('.cpj-copy');
      var card = e.target.closest('.cpj-card');
      if (!card) { return; }
      var alias = card.getAttribute('data-alias');
      if (pinBtn) { e.preventDefault(); togglePin(alias); return; }
      if (copyBtn) { e.preventDefault(); copyUrl(alias, copyBtn); return; }
      if (!e.target.closest('a')) {
        var a = card.querySelector('.cpj-link');
        if (a) { window.location.href = a.getAttribute('href'); }
      }
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === '/' && document.activeElement !== $('cpj-search')) {
        e.preventDefault();
        $('cpj-search').focus();
      }
    });

    load();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
