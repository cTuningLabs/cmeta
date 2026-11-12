/*
   The bar above every page of the cMeta server (2026-11-12; templates/header.html, page_header of the cserver
   config): the menu of all pages - the home page's own list (/projects ?native_action=projects), read once when the
   menu first opens, filtered as you type, Enter opens the first (or the chosen) one; with Customized on (the switch
   the home page has too, kept in this browser: cserver.projects.customized) the sections of the home page's
   customized view in their order (?native_action=view), then the pages none of them names - the neuron to the home
   page, where the page is (a part of its name opens the menu on its sibling pages), the theme every page shares
   (cmeta.theme: a click sets it and tells the page in this tab as other tabs are told) and Settings.
*/
(function () {
  var KEY = 'cmeta.theme', CUSTOM_KEY = 'cserver.projects.customized';
  var bar = document.getElementById('cmh');
  if (!bar) return;
  var drawer = document.getElementById('cmh-drawer'), back = document.getElementById('cmh-back');
  var menu = document.getElementById('cmh-menu'), filter = document.getElementById('cmh-filter');
  var list = document.getElementById('cmh-list'), customBox = document.getElementById('cmh-custom');
  var here = bar.getAttribute('data-page') || '', home = bar.getAttribute('data-home') || '/';
  var pages = null, view = null, loading = {}, chosen = 0, shown = [];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function stored(key) {
    try { return window.localStorage.getItem(key) || ''; } catch (e) { return ''; }
  }

  /* full width whatever margin the page's body keeps; the page's own top margin stays below the bar */
  function bleed() {
    var cs = window.getComputedStyle(document.body);
    bar.style.marginLeft = '-' + cs.marginLeft;
    bar.style.marginRight = '-' + cs.marginRight;
    bar.style.marginTop = '-' + cs.marginTop;
    bar.style.marginBottom = cs.marginTop;
  }

  /* ------------------------------------------------------------ the theme */
  function apply(dark) {
    bar.classList.toggle('cmh-dark', !!dark);
    drawer.classList.toggle('cmh-dark', !!dark);
  }
  // a page that sets the shared theme (its own switch) tells the bar through the setItem hook of base.html
  window.cmetaHeaderTheme = function (value) { apply(value === 'dark'); };
  window.addEventListener('storage', function (e) {
    if (e.key === KEY && e.newValue) apply(e.newValue === 'dark');
    if (e.key === CUSTOM_KEY && customBox) { customBox.checked = e.newValue === '1'; if (!drawer.hidden) load(); }
  });
  document.getElementById('cmh-theme').addEventListener('click', function () {
    var old = stored(KEY), next = bar.classList.contains('cmh-dark') ? 'light' : 'dark';
    try { window.localStorage.setItem(KEY, next); } catch (e) { /* private mode */ }
    apply(next === 'dark');
    // the page follows the shared theme of other tabs through the storage event: the same word in this tab
    try {
      window.dispatchEvent(new StorageEvent('storage', { key: KEY, oldValue: old || null, newValue: next,
                                                         url: window.location.href, storageArea: window.localStorage }));
    } catch (e) { /* an old browser: the page follows at its next load */ }
  });

  /* ------------------------------------------------------------ the menu */
  // an entry: {title, page ('' for a link of a customized view), href, about, repo, group, missing}
  function titleOf(p) {
    var name = String(p.name || '');
    return (name.split(' - ')[0] || '').trim() || p.page;
  }
  function aboutOf(p) {
    var name = String(p.name || ''), i = name.indexOf(' - ');
    return p.desc || (i > 0 ? name.slice(i + 3) : '');
  }
  function custom() { return !!(customBox && customBox.checked); }
  function entries() {
    if (custom()) {
      if (!view) return null;
      var out = [];
      (view.sections || []).forEach(function (section) {
        (view.buttons || []).forEach(function (b) {
          if (b.section !== section) return;
          out.push({ title: b.title || b.page || b.url, page: b.page || '', href: b.href, about: b.about || b.note || '',
                     repo: b.repo || '', group: section || 'Pages', missing: !!b.missing });
        });
      });
      (view.loose || []).forEach(function (p) {
        out.push({ title: p.title || p.page, page: p.page, href: p.href, about: p.about || '', repo: p.repo || '',
                   group: 'Other pages' });
      });
      return out;
    }
    if (!pages) return null;
    return pages.map(function (p) {
      return { title: titleOf(p), page: p.page, href: p.href, about: aboutOf(p), repo: p.repo || '', group: '' };
    });
  }
  function matches(e, words) {
    var t = (e.title + ' /' + e.page + ' ' + e.about + ' ' + e.repo + ' ' + e.group).toLowerCase();
    // a word that ends with a dot is the start of a page's name (a part of the place: "my." - my.dashboard ...)
    return words.every(function (w) {
      return /\.$/.test(w) ? String(e.page).toLowerCase().indexOf(w.replace(/^\//, '')) === 0 : t.indexOf(w) >= 0;
    });
  }
  function draw() {
    var all = entries();
    if (!all) return;
    var words = filter.value.toLowerCase().split(/\s+/).filter(Boolean);
    shown = all.filter(function (e) { return matches(e, words); });
    chosen = Math.min(Math.max(chosen, 0), Math.max(shown.length - 1, 0));
    var out = [], group = null;
    if (!words.length) {
      out.push('<a class="cmh-item' + (bar.getAttribute('data-is-home') === '1' ? ' cmh-here' : '') + '" href="' + esc(home) +
               '"><b>Home</b><small>/</small><span>every page of this server, as cards</span></a>');
    }
    shown.forEach(function (e, i) {
      if (e.group && e.group !== group) {
        group = e.group;
        out.push('<div class="cmh-group">' + esc(group) + '</div>');
      }
      out.push('<a class="cmh-item' + (e.page && e.page === here ? ' cmh-here' : '') + (i === chosen && words.length ? ' cmh-sel' : '') +
               (e.missing ? ' cmh-missing' : '') + '" href="' + esc(e.href) + '" title="' +
               esc((e.page ? '/' + e.page : e.href) + (e.repo ? '  (' + e.repo + ')' : '') + (e.missing ? ' - not on this machine' : '')) +
               '"><b>' + esc(e.title) + '</b>' + (e.page ? '<small>/' + esc(e.page) + '</small>' : '') +
               (e.about ? '<span>' + esc(e.about) + '</span>' : '') + '</a>');
    });
    if (!shown.length) out.push('<div class="cmh-note">No page matches "' + esc(filter.value) + '".</div>');
    out.push('<div class="cmh-count">' + shown.length + ' of ' + all.length + (custom() ? ' - as the home page groups them' : ' pages') + '</div>');
    list.innerHTML = out.join('');
  }
  function fail(e) {
    list.innerHTML = '<div class="cmh-note">The list of pages could not be read (' + esc(e && e.message || e) +
      ') - the home page has them: <a href="' + esc(home) + '">Home</a></div>';
  }
  function fetchJson(url, then, what) {
    if (loading[what]) return;
    loading[what] = true;
    fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (!d || d.error) throw new Error((d && d.error) || 'no answer'); then(d); draw(); })
      .catch(fail)
      .then(function () { loading[what] = false; });
  }
  function load() {
    if (custom()) {
      if (view) { draw(); return; }
      list.innerHTML = '<div class="cmh-note">Reading the home page\'s sections ...</div>';
      fetchJson(bar.getAttribute('data-view'), function (d) { view = d; }, 'view');
      return;
    }
    if (pages) { draw(); return; }
    fetchJson(bar.getAttribute('data-projects'), function (d) {
      if (!d.pages) throw new Error('no list of pages');
      pages = d.pages.slice().sort(function (a, b) { return titleOf(a).localeCompare(titleOf(b)); });
    }, 'pages');
  }
  function open(prefix) {
    drawer.hidden = false;
    back.hidden = false;
    menu.setAttribute('aria-expanded', 'true');
    if (typeof prefix === 'string') filter.value = prefix;
    chosen = 0;
    load();
    // the filter takes the keys at once: a word typed (or Enter) right after the click goes there, never to ☰
    filter.focus();
    filter.select();
  }
  function close() {
    drawer.hidden = true;
    back.hidden = true;
    menu.setAttribute('aria-expanded', 'false');
  }
  menu.addEventListener('click', function () { if (drawer.hidden) open(); else close(); });
  back.addEventListener('click', close);
  document.getElementById('cmh-close').addEventListener('click', function () { close(); menu.focus(); });
  Array.prototype.forEach.call(bar.querySelectorAll('.cmh-crumb'), function (c) {
    c.addEventListener('click', function () { open(c.getAttribute('data-prefix') || ''); });
  });
  if (customBox) {
    customBox.checked = stored(CUSTOM_KEY) === '1';
    customBox.addEventListener('change', function () {
      try { window.localStorage.setItem(CUSTOM_KEY, customBox.checked ? '1' : '0'); } catch (e) { /* private mode */ }
      chosen = 0;
      load();
      filter.focus();
    });
  }
  filter.addEventListener('input', function () { chosen = 0; draw(); });
  filter.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      chosen = (chosen + (e.key === 'ArrowDown' ? 1 : -1) + shown.length) % Math.max(shown.length, 1);
      draw();
      var sel = list.querySelector('.cmh-sel');
      if (sel && sel.scrollIntoView) sel.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') {
      var go = shown[chosen] || shown[0];
      if (go) { e.preventDefault(); window.location.href = go.href; }
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !drawer.hidden) { close(); menu.focus(); }
  });

  apply(stored(KEY) === 'dark');
  bleed();
  window.cmetaHeader = { open: open, close: close };       // for the browser checks
})();
