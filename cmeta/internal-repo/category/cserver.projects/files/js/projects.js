/* Licensed under the Apache License, Version 2.0. See the COPYRIGHT and LICENSE files in the project root for details.
   cserver.projects - the home page of cserver, two ways: the cards (?native_action=projects: every page of this
   machine, grouped by repository, with pins) and, with the Customized switch (kept in this browser; off by default),
   one's own view (?native_action=view): sections of buttons with names of one's own, an important one filled,
   arranged in place - Edit: a button dragged to another place or section (a long press first on a phone), a section
   dragged by its handle or renamed with its pencil, a click on a button to change it (its title, its page or address,
   its section, Important, its note) or delete it, "+" at the end of a section and "+ Section" for new ones; the pages
   of this machine the view does not name, listed under it, dragged into a section or clicked to be added. Each change
   goes to the server at once and its message offers Undo; Alt+Left / Alt+Right move a focused button, Alt+Up /
   Alt+Down a section (on its handle). The search box filters either way (Enter opens the first one); A- / A+ set the
   size, kept too.

   One file for two pages: this home page (#cpj, started at the end of this file) and any page that draws one's view
   with CmetaProjects.board (a dashboard puts this file into itself; its changes go through it to this page's view_*
   actions). No dependency. */

(function () {
  'use strict';
  if (window.CmetaProjects) { return; }

  /* ------------------------------------------------------------------ helpers */
  function h(tag, attrs) {
    var e = document.createElement(tag), a = attrs || {};
    Object.keys(a).forEach(function (k) { if (k === 'class') { e.className = a[k]; } else { e.setAttribute(k, a[k]); } });
    for (var i = 2; i < arguments.length; i++) {
      var kid = arguments[i];
      if (kid === null || kid === undefined || kid === false) { continue; }
      e.appendChild(typeof kid === 'string' ? document.createTextNode(kid) : kid);
    }
    return e;
  }
  function esc(s) {
    return String(s === undefined || s === null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function words(q) { return String(q || '').toLowerCase().split(/\s+/).filter(Boolean); }
  /* a button (or a page of the machine) the words of a search keep: each word in its title, page, address,
     section, note, what its page says of itself or its repository */
  function hits(b, ws) {
    if (!ws || !ws.length) { return true; }
    var hay = [b.title, b.page, b.url, b.section, b.note, b.about, b.repo].join(' ').toLowerCase();
    return ws.every(function (w) { return hay.indexOf(w) >= 0; });
  }
  function cssEsc(s) { return window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/["\\]/g, '\\$&'); }
  var seq = 0;                              /* ids of a board's own elements (two boards on a page never clash) */

  /* ------------------------------------------------------------------ a board: one's view */
  /* opts: edit (this browser may change it), call(action, params) -> Promise (save, arrange, discard, restore - the
     view_* actions of the home page), changed() -> Promise (the view read again and set: after a change), ui {toast(text,
     bad), toastAction(text, label, fn)}, host (where its dialog and the dragged copy go: the page's root, for its
     colours), cref_url (the reader of an artifact: the form names the button's artifact), top() (the bottom of a bar
     that stays at the top of the window: a drag scrolls below it), empty() (the text of an empty view), footnote
     (a line under the view: where it is kept) */
  function board(opts) {
    opts = opts || {};
    var ui = opts.ui || {};
    var id = ++seq;
    var el = h('div', { 'class': 'cpj-board', 'data-board': String(id) });
    var marker = null;
    var view = { buttons: [], sections: [], loose: [], pages: [] }, ws = [], editing = false;
    var drag = null, lastDrag = 0, form = null, renaming = null;

    function host() { return opts.host || document.body; }
    function toast(text, bad) { if (ui.toast) { ui.toast(text, bad); } }
    function toastUndo(text, fn) { if (ui.toastAction) { ui.toastAction(text, 'Undo', fn); } else { toast(text); } }
    function call(action, params) { return opts.call(action, params); }
    function changed() { return Promise.resolve(opts.changed ? opts.changed() : null); }
    function failed(e) { toast(e.message, true); return changed(); }

    /* ---------------------------------------------------------------- drawing */
    function render() {
      closeRename();
      cancelDrag();
      el.innerHTML = '';
      el.classList.toggle('cpj-editing', editing);
      var order = [], by = {}, n = 0;
      (view.buttons || []).forEach(function (b) {
        if (!hits(b, ws)) { return; }
        if (!by.hasOwnProperty(b.section)) { by[b.section] = []; order.push(b.section); }
        by[b.section].push(b);
        n++;
      });
      if (editing && !ws.length) {
        /* every section in Edit, in its place - an empty one too (2026-11-11: "+ Section" makes one by its name alone) */
        var all = (view.sections || []).slice();
        order.forEach(function (s) { if (all.indexOf(s) < 0) { all.push(s); } });
        all.forEach(function (s) { if (!by.hasOwnProperty(s)) { by[s] = []; } });
        order = all;
      }
      if (!(view.buttons || []).length && !(editing && order.length)) {
        el.appendChild(h('div', { 'class': 'cpj-empty-view' }, opts.empty ? opts.empty() : 'No view yet.'));
      }
      order.forEach(function (s) { el.appendChild(sectionEl(s, by[s])); });
      if (editing) {
        var ns = h('button', { type: 'button', 'class': 'cpj-btn cpj-newsec', title: 'A new section: its name (then drag buttons into it, or "+" in it)' }, '+ Section');
        var foot = h('div', { 'class': 'cpj-sfoot' }, ns);
        ns.addEventListener('click', function () { startNewSection(foot, ns); });
        el.appendChild(foot);
      }
      var loose = (view.loose || []).filter(function (l) { return hits(l, ws); });
      if (loose.length && (view.buttons || []).length) { el.appendChild(looseEl(loose)); }
      if (!n && !loose.length && (view.buttons || []).length) { el.appendChild(h('p', { 'class': 'cpj-muted' }, 'Nothing matches the search.')); }
      if (opts.footnote && (view.buttons || []).length) {
        el.appendChild(h('p', { 'class': 'cpj-viewnote' },
          'Your view: ' + view.buttons.length + ' buttons in ' + view.sections.length + ' sections, kept in ' + (view.home || 'local') +
          ' (artifacts of cserver.projects, one per button) - a repository that syncs between your machines shows each of them the same view.'));
      }
      marker = h('div', { 'class': 'cpj-marker', hidden: '' });
      el.appendChild(marker);
      var first = el.querySelector('.cpj-pill[href]');
      if (first && ws.length) { first.classList.add('cpj-hit'); }
      return { shown: n, total: (view.buttons || []).length, sections: (view.sections || []).length };
    }

    function sectionEl(s, list) {
      var sec = h('div', { 'class': 'cpj-sec', 'data-section': s });
      var title = h('div', { 'class': 'cpj-stitle' });
      var name = h('span', { 'class': 'cpj-sname' }, s || '(no section)');
      if (editing) {
        var handle = h('span', { 'class': 'cpj-handle', role: 'button', tabindex: '0', 'aria-label': 'Move the section ' + s,
                                 title: 'Drag the section to another place (or Alt+Up / Alt+Down)' }, '\u283f');
        handle.addEventListener('pointerdown', function (e) { press(e, 'section', null, s, sec); });
        handle.addEventListener('keydown', function (e) {
          if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) { e.preventDefault(); moveSectionBy(s, e.key === 'ArrowUp' ? -1 : 1); }
        });
        title.appendChild(handle);
      }
      title.appendChild(name);
      if (editing) {
        var ren = h('button', { type: 'button', 'class': 'cpj-mini cpj-ren', title: 'Rename the section (its buttons follow)',
                                'aria-label': 'Rename the section ' + s }, '\u270e');
        ren.addEventListener('click', function () { startRename(s, title, name); });
        title.appendChild(ren);
        /* an empty section made by "+ Section": x removes it (its record); a section with buttons goes with them */
        var marks = (view.markers || []).filter(function (m) { return m.section === s; });
        if (!list.length && marks.length) {
          var rm = h('button', { type: 'button', 'class': 'cpj-mini cpj-srm', title: 'Remove this empty section',
                                 'aria-label': 'Remove the empty section ' + s }, '\u00d7');
          rm.addEventListener('click', function () { removeSection(s, marks); });
          title.appendChild(rm);
        }
      }
      var pills = h('div', { 'class': 'cpj-pills' });
      list.forEach(function (b) {
        pills.appendChild(pillEl(b));
        if (b.newline) { pills.appendChild(h('span', { 'class': 'cpj-break', 'aria-hidden': 'true' })); }   /* the next one on a new line */
      });
      if (editing) {
        var add = h('button', { type: 'button', 'class': 'cpj-pill cpj-addpill', title: 'A new button in ' + s, 'aria-label': 'A new button in ' + s }, '+');
        add.addEventListener('click', function () { openForm(null, s); });
        pills.appendChild(add);
      }
      sec.appendChild(title);
      sec.appendChild(pills);
      return sec;
    }

    function pillEl(b) {
      var a = h('a', { 'class': 'cpj-pill' + (b.star ? ' cpj-star' : '') + (b.missing ? ' cpj-missing' : '') + (b.href ? '' : ' cpj-bad'),
                       'data-uid': b.uid, draggable: 'false' }, b.title);
      var where = b.page ? '/' + b.page : b.url;
      a.title = [b.note, b.about, where, b.missing ? 'not a page of this machine' : ''].filter(Boolean).join('\n') || b.title;
      if (editing) {
        a.setAttribute('role', 'button');
        a.tabIndex = 0;
        a.title = b.title + ' - a click changes it, a drag moves it (Alt+Left / Alt+Right)\n' + where;
        a.addEventListener('pointerdown', function (e) { press(e, 'button', b, b.section, a); });
        a.addEventListener('click', function (e) {
          e.preventDefault();
          if (Date.now() - lastDrag < 400) { return; }          /* the click that ends a drag */
          openForm(b, b.section);
        });
        a.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openForm(b, b.section); }
          else if (e.altKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) { e.preventDefault(); moveBy(b, e.key === 'ArrowLeft' ? -1 : 1); }
        });
        a.addEventListener('contextmenu', function (e) { e.preventDefault(); });    /* a long press is a drag here */
      } else if (b.href) {
        a.href = b.href;
      }
      return a;
    }

    /* The pages of this machine the view does not name: links as any, and in Edit to be dragged into a section or
       clicked to be added */
    function looseEl(list) {
      var sec = h('div', { 'class': 'cpj-sec cpj-loosesec' });
      sec.appendChild(h('div', { 'class': 'cpj-stitle' }, h('span', { 'class': 'cpj-sname' }, 'Not in your view (' + list.length + ')')));
      var pills = h('div', { 'class': 'cpj-pills' });
      list.forEach(function (l) {
        var a = h('a', { 'class': 'cpj-pill cpj-loose', 'data-page': l.page, draggable: 'false',
                         title: [l.about, '/' + l.page, 'in ' + (l.repo || 'local'), editing ? 'drag it into a section, or click to add it' : ''].filter(Boolean).join('\n') },
                  l.title);
        if (editing) {
          a.setAttribute('role', 'button');
          a.tabIndex = 0;
          a.addEventListener('pointerdown', function (e) { press(e, 'loose', l, '', a); });
          a.addEventListener('click', function (e) {
            e.preventDefault();
            if (Date.now() - lastDrag < 400) { return; }
            openForm(null, (view.sections || [])[0] || '', l);
          });
          a.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openForm(null, (view.sections || [])[0] || '', l); } });
          a.addEventListener('contextmenu', function (e) { e.preventDefault(); });
        } else {
          a.href = l.href;
        }
        pills.appendChild(a);
      });
      sec.appendChild(pills);
      return sec;
    }

    function flash(uid) {
      var p = el.querySelector('.cpj-pill[data-uid="' + uid + '"]');
      if (!p) { return; }
      p.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      p.classList.remove('cpj-flash');
      void p.offsetWidth;
      p.classList.add('cpj-flash');
    }
    function focusOf(sel) { var x = el.querySelector(sel); if (x) { x.focus(); } }

    /* ------------------------------------------------------------- the moves */
    function arrangeButton(b, section, before, refocus) {
      if (before === b.uid) { return Promise.resolve(); }
      return call('arrange', { uid: b.uid, section: section, before: before })
        .then(function (res) {
          if (!res.changed || !res.changed.length) { return changed(); }
          return changed().then(function () {
            if (refocus) { focusOf('.cpj-pill[data-uid="' + b.uid + '"]'); }
            toastUndo('Moved: ' + b.title + (section !== b.section ? ' - to ' + section : ''), function () { putBack(res.undo); });
          });
        })
        .catch(failed);
    }
    function moveBy(b, dir) {
      var mine = (view.buttons || []).filter(function (x) { return x.section === b.section; });
      var i = -1;
      mine.forEach(function (x, k) { if (x.uid === b.uid) { i = k; } });
      var j = i + dir;
      if (i < 0 || j < 0 || j >= mine.length) { return; }
      arrangeButton(b, b.section, dir < 0 ? mine[j].uid : (mine[j + 1] ? mine[j + 1].uid : ''), true);
    }
    function arrangeSection(s, before, refocus) {
      if (before === s) { return Promise.resolve(); }
      return call('arrange', { move_section: s, before_section: before })
        .then(function (res) {
          if (!res.changed || !res.changed.length) { return changed(); }
          return changed().then(function () {
            if (refocus) { focusOf('.cpj-sec[data-section="' + cssEsc(s) + '"] .cpj-handle'); }
            toastUndo('Moved the section ' + s, function () { putBack(res.undo); });
          });
        })
        .catch(failed);
    }
    function moveSectionBy(s, dir) {
      var all = view.sections || [], i = all.indexOf(s), j = i + dir;
      if (i < 0 || j < 0 || j >= all.length) { return; }
      arrangeSection(s, dir < 0 ? all[j] : (all[j + 1] || ''), true);
    }
    /* Undo of a move or a rename: the orders and sections the buttons had */
    function putBack(undo) {
      return call('arrange', { orders: undo }).then(changed).then(function () { toast('Put back as it was'); }).catch(failed);
    }
    /* A page the view does not name, added where it was dropped */
    function addLoose(l, section, before) {
      return call('save', { page: l.page, title: l.title, section: section, before: before })
        .then(function (res) {
          var k = res.button;
          return changed().then(function () {
            flash(k.uid);
            toastUndo('Added: ' + k.title + ' - ' + k.section, function () { discardIt(k, true); });
          });
        })
        .catch(failed);
    }

    /* ------------------------------------------------------- a new, empty section: its name alone */
    function startNewSection(foot, btn) {
      closeRename();
      if (foot.querySelector('.cpj-sin')) { foot.querySelector('.cpj-sin').focus(); return; }
      var input = h('input', { type: 'text', 'class': 'cpj-sin cpj-newsin', maxlength: '100', placeholder: 'the name of the new section',
                               'aria-label': 'The name of the new section' });
      btn.hidden = true;
      foot.insertBefore(input, btn);
      var done = false;
      function close(refocus) {
        if (done) { return; }
        done = true;
        input.remove();
        btn.hidden = false;
        if (refocus) { btn.focus(); }
      }
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); submit(); }
        else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(true); }
      });
      input.addEventListener('blur', function () { setTimeout(function () { if (!input.disabled && !input.value.trim()) { close(); } }, 150); });
      function submit() {
        var name = input.value.trim();
        if (!name) { close(true); return; }
        var low = name.toLowerCase();
        var have = (view.sections || []).filter(function (x) { return x.toLowerCase() === low; })[0];
        if (have) { toast('There is a section ' + have + ' already', true); input.select(); return; }
        input.disabled = true;
        call('section', { section: name })
          .then(function (res) {
            done = true;
            return changed().then(function () {
              var sEl = el.querySelector('.cpj-sec[data-section="' + cssEsc(res.section) + '"]');
              if (sEl) { sEl.scrollIntoView({ block: 'nearest' }); sEl.classList.add('cpj-flash'); }
              toastUndo('Added the section ' + res.section, function () {
                call('discard', { uid: res.uid }).then(changed).then(function () { toast('Removed again: ' + res.section); }).catch(failed);
              });
            });
          })
          .catch(function (e) { toast(e.message, true); input.disabled = false; input.focus(); });
      }
      input.focus();
    }
    /* an empty section removed: its record(s) deleted, put back by Undo */
    function removeSection(s, marks) {
      var removed = [];
      marks.reduce(function (p, m) {
        return p.then(function () { return call('discard', { uid: m.uid }).then(function (res) { removed.push(res.removed); }); });
      }, Promise.resolve())
        .then(function () {
          return changed().then(function () {
            toastUndo('Removed the empty section ' + s, function () {
              removed.reduce(function (p, r) { return p.then(function () { return call('restore', { removed: r }); }); }, Promise.resolve())
                .then(changed).then(function () { toast('Back: ' + s); }).catch(failed);
            });
          });
        })
        .catch(failed);
    }

    /* ------------------------------------------------------- a section renamed */
    function startRename(s, title, nameEl) {
      closeRename();
      var input = h('input', { type: 'text', 'class': 'cpj-sin', maxlength: '100', 'aria-label': 'The new name of the section ' + s });
      input.value = s;
      nameEl.hidden = true;
      title.insertBefore(input, nameEl.nextSibling);
      renaming = { s: s, input: input, nameEl: nameEl, title: title };
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); submitRename(); }
        else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeRename(true); }
      });
      input.addEventListener('blur', function () { setTimeout(function () { if (renaming && renaming.input === input && !input.disabled) { closeRename(); } }, 150); });
      input.focus();
      input.select();
    }
    function closeRename(refocus) {
      if (!renaming) { return; }
      var x = renaming;
      renaming = null;
      x.input.remove();
      x.nameEl.hidden = false;
      if (refocus) { var b = x.title.querySelector('.cpj-ren'); if (b) { b.focus(); } }
    }
    function submitRename() {
      var x = renaming, to = x.input.value.trim();
      if (!to || to === x.s) { closeRename(true); return; }
      x.input.disabled = true;
      call('arrange', { section: x.s, rename: to })
        .then(function (res) {
          renaming = null;
          return changed().then(function () { toastUndo('Renamed the section ' + x.s + ' - ' + to, function () { putBack(res.undo); }); });
        })
        .catch(function (e) { toast(e.message, true); x.input.disabled = false; x.input.focus(); });
    }

    /* ---------------------------------------------- drag and drop (a mouse, a pen, a finger) */
    /* A mouse drags once it moves a few pixels; a finger after a long press (before that, it scrolls the page). The
       dragged copy follows the pointer, a line shows where it would go, the window scrolls near its edges; dropped,
       the button (or section) moves at once and the server is told (Undo in its message); Esc cancels. */
    function press(e, kind, item, s, src) {
      if (!editing || drag || (e.pointerType === 'mouse' && e.button !== 0)) { return; }
      drag = { kind: kind, item: item, s: s, src: src, id: e.pointerId, x0: e.clientX, y0: e.clientY, x: e.clientX, y: e.clientY,
               active: false, touch: e.pointerType !== 'mouse', timer: 0, target: null, ghost: null, scroller: 0 };
      if (drag.touch) {
        var d = drag;
        d.timer = setTimeout(function () { if (drag === d && !d.active) { begin(); } }, 300);
      }
    }
    function begin() {
      var d = drag, sec = d.kind === 'section', r = d.src.getBoundingClientRect();
      d.active = true;
      clearTimeout(d.timer);
      d.dx = d.x0 - r.left;
      d.home = d.kind === 'button' ? uidAfter(d.src) : (sec ? sectionAfter(d.src) : null);
      var face = sec ? d.src.querySelector('.cpj-stitle') : d.src;
      var ghost = face.cloneNode(true);
      ghost.className = (sec ? 'cpj-stitle' : d.src.className) + ' cpj-ghost';
      ghost.style.width = Math.ceil(face.getBoundingClientRect().width) + 'px';
      ghost.style.fontSize = getComputedStyle(face).fontSize;
      host().appendChild(ghost);
      d.ghost = ghost;
      d.src.classList.add('cpj-dragging');
      el.classList.add('cpj-dnd');
      if (d.touch && navigator.vibrate && navigator.userActivation && navigator.userActivation.hasBeenActive) {
        try { navigator.vibrate(12); } catch (x) { /* not allowed here */ }
      }
      d.scroller = setInterval(autoScroll, 30);
      track();
    }
    function onMove(e) {
      if (!drag || e.pointerId !== drag.id) { return; }
      drag.x = e.clientX;
      drag.y = e.clientY;
      if (!drag.active) {
        var dx = drag.x - drag.x0, dy = drag.y - drag.y0, d2 = dx * dx + dy * dy;
        if (drag.touch) { if (d2 > 100) { finishDrag(); } return; }   /* a finger that moves first scrolls the page */
        if (d2 < 25) { return; }
        begin();
      }
      e.preventDefault();
      track();
    }
    function onUp(e) {
      if (!drag || e.pointerId !== drag.id) { return; }
      var d = drag;
      finishDrag();
      if (!d.active) { return; }                                  /* a click: the click handler does it */
      lastDrag = Date.now();
      var t = d.target;
      if (!t) { return; }
      if (d.kind === 'section') {
        t.sEl.parentNode.insertBefore(d.src, t.after ? t.sEl.nextSibling : t.sEl);
        arrangeSection(d.s, t.before, false);
        return;
      }
      /* at once on the page; the server's answer draws it again */
      if (t.at) { t.at.parentNode.insertBefore(d.src, t.after ? t.at.nextSibling : t.at); }
      else { var box = t.sEl.querySelector('.cpj-pills'); box.insertBefore(d.src, box.querySelector('.cpj-addpill')); }
      if (d.kind === 'button') { arrangeButton(d.item, t.s, t.before, false); } else { addLoose(d.item, t.s, t.before); }
    }
    function finishDrag() {
      var d = drag;
      if (!d) { return; }
      drag = null;
      clearTimeout(d.timer);
      clearInterval(d.scroller);
      if (d.ghost) { d.ghost.remove(); }
      d.src.classList.remove('cpj-dragging');
      el.classList.remove('cpj-dnd');
      if (marker) { marker.hidden = true; }
    }
    function cancelDrag() { if (drag) { if (drag.active) { lastDrag = Date.now(); } finishDrag(); } }

    function track() {
      var d = drag;
      /* the copy beside the pointer, never over the line that shows where it goes: under a mouse, above a finger */
      d.ghost.style.left = (d.x - Math.min(d.dx, 24)) + 'px';
      d.ghost.style.top = (d.touch ? d.y - d.ghost.offsetHeight - 22 : d.y + 18) + 'px';
      var under = document.elementFromPoint(d.x, d.y);
      d.target = under && el.contains(under) ? (d.kind === 'section' ? sectionTarget(under, d.y) : pillTarget(under, d.x, d.y)) : null;
      showMarker(d.target);
    }
    /* the next button after a pill (the dragged one skipped): its UID, '' at the end of its section */
    function uidAfter(pill) {
      for (var n = pill.nextElementSibling; n; n = n.nextElementSibling) {
        if (drag && n === drag.src) { continue; }
        if (n.classList.contains('cpj-break')) { continue; }        /* a line break is no button */
        return n.getAttribute('data-uid') || '';
      }
      return '';
    }
    function sectionAfter(sEl) {
      for (var n = sEl.nextElementSibling; n; n = n.nextElementSibling) {
        if (drag && n === drag.src) { continue; }
        if (n.classList.contains('cpj-sec') && !n.classList.contains('cpj-loosesec')) { return n.getAttribute('data-section'); }
      }
      return '';
    }
    /* where a dragged button would go: before a button (its left half) or after it (its right half); in the gaps of a
       line, before the first button right of the pointer; past the end of a line, after its last one; elsewhere in a
       section, at its end -> {s, before, at, after, sEl} or null (its own place, or not a section of the view) */
    function pillTarget(under, x, y) {
      var sEl = under.closest('.cpj-sec');
      if (!sEl || sEl.classList.contains('cpj-loosesec')) { return null; }
      var s = sEl.getAttribute('data-section');
      var pill = under.closest('.cpj-pill[data-uid]'), after = false;
      if (pill === drag.src) { return null; }
      if (!pill) {
        var pills = [].slice.call(sEl.querySelectorAll('.cpj-pill[data-uid]')).filter(function (p) { return p !== drag.src; });
        var line = pills.filter(function (p) { var r = p.getBoundingClientRect(); return y >= r.top - 4 && y <= r.bottom + 4; });
        var right = line.filter(function (p) { var r = p.getBoundingClientRect(); return r.left + r.width / 2 > x; });
        if (right.length) { pill = right[0]; }
        else if (line.length) { pill = line[line.length - 1]; after = true; }
        else if (pills.length) { pill = pills[pills.length - 1]; after = true; }
      } else {
        var rr = pill.getBoundingClientRect();
        after = x > rr.left + rr.width / 2;
      }
      var before = pill ? (after ? uidAfter(pill) : pill.getAttribute('data-uid')) : '';
      if (drag.kind === 'button' && s === drag.item.section && before === drag.home) { return null; }
      return { s: s, before: before, at: pill, after: after, sEl: sEl };
    }
    /* where a dragged section would go: before the section under the pointer (its upper half) or after it */
    function sectionTarget(under, y) {
      var sEl = under.closest('.cpj-sec');
      if (!sEl || sEl.classList.contains('cpj-loosesec')) { return null; }
      var r = sEl.getBoundingClientRect(), after = y > r.top + r.height / 2;
      var before = after ? sectionAfter(sEl) : sEl.getAttribute('data-section');
      if (sEl === drag.src || before === drag.home) { return null; }
      return { before: before, sEl: sEl, after: after };
    }
    function showMarker(t) {
      if (!t || !(t.at || t.sEl)) { marker.hidden = true; return; }
      var base = el.getBoundingClientRect();
      marker.hidden = false;
      if (drag.kind !== 'section') {
        var r = (t.at || t.sEl.querySelector('.cpj-pills')).getBoundingClientRect();
        marker.className = 'cpj-marker v';
        marker.style.left = ((t.at ? (t.after ? r.right + 2 : r.left - 4) : r.left) - base.left) + 'px';
        marker.style.top = (r.top - base.top) + 'px';
        marker.style.height = (t.at ? r.height : 22) + 'px';
        marker.style.width = '';
      } else {
        var sr = t.sEl.getBoundingClientRect();
        marker.className = 'cpj-marker hz';
        marker.style.left = '0px';
        marker.style.top = ((t.after ? sr.bottom : sr.top) - base.top - 2) + 'px';
        marker.style.width = base.width + 'px';
        marker.style.height = '';
      }
    }
    function autoScroll() {
      if (!drag || !drag.active) { return; }
      var top = opts.top ? opts.top() : 0, edge = 56, v = 0, y = drag.y;
      if (y < top + edge) { v = -Math.ceil((top + edge - y) / 3); }
      else if (y > window.innerHeight - edge) { v = Math.ceil((y - (window.innerHeight - edge)) / 3); }
      if (v) { window.scrollBy(0, v); track(); }
    }

    document.addEventListener('pointermove', onMove, { passive: false });
    document.addEventListener('pointerup', onUp);
    document.addEventListener('pointercancel', function (e) { if (drag && e.pointerId === drag.id) { cancelDrag(); } });
    /* a finger that drags never scrolls the page meanwhile */
    document.addEventListener('touchmove', function (e) { if (drag && drag.active && e.cancelable) { e.preventDefault(); } }, { passive: false });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && drag) { cancelDrag(); e.preventDefault(); } });

    /* ------------------------------------------------------- the form of a button */
    function buildForm() {
      var f = h('form', { 'class': 'cpj-form', autocomplete: 'off', novalidate: '' });
      var head = h('h3', { id: 'cpj-form-h-' + id }, 'New button');
      var close = h('button', { type: 'button', 'class': 'cpj-x', title: 'Close (Esc)', 'aria-label': 'Close' }, '\u00d7');
      f.appendChild(h('div', { 'class': 'cpj-form-head' }, head, close));
      function row(label, field, tip) {
        f.appendChild(h('label', { 'class': 'cpj-field', title: tip || '' }, h('span', { 'class': 'cpj-flabel' }, label), field));
      }
      var title = h('input', { type: 'text', name: 'title', maxlength: '100', placeholder: 'the text of its button' });
      var pages = h('datalist', { id: 'cpj-pages-' + id });
      var target = h('input', { type: 'text', name: 'target', list: 'cpj-pages-' + id, spellcheck: 'false', maxlength: '4000',
                                placeholder: '/browse, monitor?watch=x - or http://another-machine:8004/browse' });
      var secs = h('datalist', { id: 'cpj-secs-' + id });
      var section = h('input', { type: 'text', name: 'section', list: 'cpj-secs-' + id, maxlength: '100', placeholder: 'its section' });
      var star = h('input', { type: 'checkbox', name: 'star' });
      var newline = h('input', { type: 'checkbox', name: 'newline' });
      var note = h('textarea', { name: 'note', rows: '2', maxlength: '1000', placeholder: 'optional: a line shown when it is pointed at' });
      row('Title', title, 'Empty: the heading of its page\'s card, or the name of its site');
      row('Page', target, 'A page of this server (its name, a path or ?query may follow), or the address of any page - another machine\'s too');
      f.appendChild(pages);
      row('Section', section, 'A section of the view, or a new one');
      f.appendChild(secs);
      f.appendChild(h('label', { 'class': 'cpj-field cpj-check' }, h('span', { 'class': 'cpj-flabel' }, ''), star,
                      h('span', {}, 'Important - a filled button')));
      row('Note', note);
      f.appendChild(h('label', { 'class': 'cpj-field cpj-check', title: 'Several lines of buttons in one section: this button ends its line' },
                      h('span', { 'class': 'cpj-flabel' }, ''), newline, h('span', {}, 'New line after it - the next button starts a line of its own')));
      var art = h('div', { 'class': 'cpj-art' });
      var err = h('div', { 'class': 'cpj-err', role: 'alert', hidden: '' });
      var del = h('button', { type: 'button', 'class': 'cpj-btn cpj-del', title: 'Delete this button (Undo in the message)' }, 'Delete');
      var cancel = h('button', { type: 'button', 'class': 'cpj-btn' }, 'Cancel');
      var ok = h('button', { type: 'submit', 'class': 'cpj-go' }, 'Save');
      f.appendChild(art);
      f.appendChild(err);
      f.appendChild(h('div', { 'class': 'cpj-acts2' }, del, h('span', { 'class': 'cpj-spacer' }), cancel, ok));
      var modal = h('div', { 'class': 'cpj-modal', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'cpj-form-h-' + id, hidden: '' }, f);
      host().appendChild(modal);
      form = { modal: modal, f: f, head: head, title: title, target: target, pages: pages, section: section, secs: secs, star: star,
               newline: newline, note: note, art: art, err: err, del: del, ok: ok, button: null };
      f.addEventListener('input', function () { err.hidden = true; });
      f.addEventListener('submit', submitForm);
      cancel.addEventListener('click', closeForm);
      close.addEventListener('click', closeForm);
      del.addEventListener('click', function () { if (form.button) { discardIt(form.button); } });
      modal.addEventListener('mousedown', function (e) { if (e.target === modal) { closeForm(); } });
      modal.addEventListener('keydown', function (e) { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeForm(); } });
    }
    function formError(msg) { form.err.textContent = msg; form.err.hidden = false; }
    function closeForm() { if (form) { form.modal.hidden = true; } }

    /* b: the button to change (null: a new one in the section s - '' asks for a new section); l: a page of this machine
       the view does not name, to add */
    function openForm(b, s, l) {
      if (!opts.edit) { return; }
      if (!form) { buildForm(); }
      cancelDrag();
      closeRename();
      form.button = b;
      form.f.reset();
      form.head.textContent = b ? 'Change the button' : (l ? 'Add ' + l.title + ' to the view' : (s ? 'New button in ' + s : 'New button in a new section'));
      form.title.value = b ? b.title : (l ? l.title : '');
      form.target.value = b ? (b.page ? '/' + b.page : b.url) : (l ? '/' + l.page : '');
      form.section.value = b ? b.section : (s || '');
      form.star.checked = !!(b && b.star);
      form.newline.checked = !!(b && b.newline);
      form.note.value = b ? (b.note || '') : '';
      form.pages.innerHTML = '';
      var seen = {};
      (view.pages || []).concat(view.loose || []).forEach(function (p) {
        if (!seen[p.page]) { seen[p.page] = 1; form.pages.appendChild(h('option', { value: '/' + p.page }, p.title || '')); }
      });
      form.secs.innerHTML = '';
      (view.sections || []).forEach(function (x) { form.secs.appendChild(h('option', { value: x })); });
      form.del.hidden = !b;
      form.art.innerHTML = '';
      if (b) {
        var ref = 'cserver.projects::' + b.alias + ',' + b.uid;
        form.art.appendChild(document.createTextNode('Its artifact: '));
        form.art.appendChild(opts.cref_url ? h('a', { href: opts.cref_url + encodeURI(ref).replace(/#/g, '%23'), title: ref }, 'cserver.projects::' + b.alias)
                                           : h('code', {}, 'cserver.projects::' + b.alias));
        form.art.appendChild(document.createTextNode(' in ' + b.repo));
      }
      form.art.hidden = !b;
      form.err.hidden = true;
      form.ok.disabled = false;
      form.modal.hidden = false;
      (b ? form.title : (s || l) ? (l ? form.section : form.target) : form.section).focus();
    }

    function submitForm(ev) {
      ev.preventDefault();
      var x = form, b = x.button;
      var target = x.target.value.trim();
      var p = { title: x.title.value.trim(), section: x.section.value.trim(), note: x.note.value, star: x.star.checked ? 'yes' : 'no',
                newline: x.newline.checked ? 'yes' : 'no' };
      if (!target) { formError('A page of this server (its name) or an address is needed.'); x.target.focus(); return; }
      if (/^(?:[a-z][\w+.\-]*:|\/\/)/i.test(target)) { p.url = target; } else { p.page = target.replace(/^\/+/, ''); }
      if (!p.section) { formError('A section is needed: one of the sections, or a new name.'); x.section.focus(); return; }
      if (b) { p.uid = b.uid; }
      x.ok.disabled = true;
      call('save', p)
        .then(function (res) {
          closeForm();
          var k = res.button;
          return changed().then(function () {
            flash(k.uid);
            if (res.created) { toastUndo('Added: ' + k.title + ' - ' + k.section, function () { discardIt(k, true); }); }
            else if (res.changed) { toastUndo('Saved: ' + k.title, function () { saveBack(k, res.old); }); }
            else { toast('Nothing changed: ' + k.title); }
          });
        })
        .catch(function (e) { formError(e.message); })
        .then(function () { x.ok.disabled = false; });
    }
    /* Undo of a change: what the button was, its place too */
    function saveBack(k, o) {
      var p = { uid: k.uid, title: o.title, section: o.section, note: o.note || '', star: o.star ? 'yes' : 'no',
                newline: o.newline ? 'yes' : 'no', order: o.order === null ? '' : o.order };
      if (o.page) { p.page = o.page; } else { p.url = o.url; }
      return call('save', p).then(changed).then(function () { flash(k.uid); toast('Put back: ' + o.title); }).catch(failed);
    }
    /* delete (quiet: the Undo of an addition - no Undo of its own) */
    function discardIt(b, quiet) {
      return call('discard', { uid: b.uid })
        .then(function (res) {
          closeForm();
          return changed().then(function () {
            if (quiet) { toast('Removed again: ' + b.title); return; }
            toastUndo('Deleted: ' + b.title, function () {
              call('restore', { removed: res.removed }).then(changed)
                .then(function () { flash(b.uid); toast('Back: ' + b.title); }).catch(failed);
            });
          });
        })
        .catch(function (e) { if (form && !form.modal.hidden) { formError(e.message); } else { toast(e.message, true); } });
    }

    return {
      el: el,
      /* the view as the server gave it ({buttons, sections, loose, pages, home ...}) and the words of the search ->
         {shown, total, sections} */
      set: function (v, words_) { view = v || { buttons: [], sections: [], loose: [], pages: [] }; ws = words_ || []; return render(); },
      editing: function () { return editing; },
      setEditing: function (on) { editing = !!on && !!opts.edit; return render(); },
      add: function (s) { openForm(null, s || ''); },
      flash: flash
    };
  }

  /* ------------------------------------------------------------------ the home page (#cpj) */
  function page() {
    var CFG = (typeof CONFIG !== 'undefined') ? CONFIG : {};
    var KEY = 'cserver.projects.';
    var PIN_KEY = KEY + 'pins', THEME_KEY = KEY + 'theme', SCALE_KEY = KEY + 'scale', CUSTOM_KEY = KEY + 'customized';
    var SHARED_THEME = 'cmeta.theme';      /* the theme of every page of this server (2026-11-10) */
    var DATA = { pages: [], others: [], repos: [] };
    var VIEW = null;                       /* the customized view as the server gave it */
    var root = document.getElementById('cpj');
    var custom = stored(CUSTOM_KEY) === '1';
    var b = null, toastTimer = null;

    function $(i) { return document.getElementById(i); }
    function stored(name) { try { return localStorage.getItem(name); } catch (e) { return null; } }
    function store(name, value) { try { localStorage.setItem(name, value); } catch (e) { /* private mode */ } }

    /* The JSON endpoint of this page; ?repo=<text> of the page URL travels with the cards' list. */
    function apiUrl(action) {
      var url = (CFG.api_url || '?') + 'native_action=' + (action || 'projects');
      return (!action || action === 'projects') && CFG.repo ? url + '&repo=' + encodeURIComponent(CFG.repo) : url;
    }
    /* A request of this page -> its JSON; an answer with an error throws it (the view's changes). */
    function call(action, params) {
      return fetch(apiUrl(action), { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                     body: JSON.stringify(params || {}) })
        .then(function (r) {
          return r.text().then(function (text) {
            var d;
            try { d = JSON.parse(text); } catch (e) { throw new Error('HTTP ' + r.status + ': ' + text.slice(0, 300)); }
            if (d && d.error) { throw new Error(d.error); }
            return d;
          });
        });
    }

    /* the messages, with Undo (their own class names: .cpj-act and .cpj-on belong to the cards' buttons) */
    function toastEl() {
      var t = $('cpj-toast');
      if (!t) { t = h('div', { id: 'cpj-toast', 'class': 'cpj-toast', role: 'status', 'aria-live': 'polite' }); root.appendChild(t); }
      return t;
    }
    function toast(text, bad) {
      var t = toastEl();
      t.textContent = text;
      t.className = 'cpj-toast cpj-shown' + (bad ? ' cpj-badt' : '');
      clearTimeout(toastTimer);
      toastTimer = setTimeout(function () { t.className = 'cpj-toast'; }, bad ? 6000 : 2400);
    }
    function toastAction(text, label, fn) {
      var t = toastEl();
      t.textContent = text + ' ';
      var x = h('button', { type: 'button', 'class': 'cpj-toast-act' }, label);
      x.addEventListener('click', function () { t.className = 'cpj-toast'; clearTimeout(toastTimer); fn(); });
      t.appendChild(x);
      t.className = 'cpj-toast cpj-shown cpj-withundo';
      clearTimeout(toastTimer);
      toastTimer = setTimeout(function () { t.className = 'cpj-toast'; }, 9000);
    }

    /* ---------------------------------------------------------------- pins */
    function pins() { try { return JSON.parse(stored(PIN_KEY) || '[]'); } catch (e) { return []; } }
    function togglePin(alias) {
      var list = pins(), i = list.indexOf(alias);
      if (i < 0) { list.push(alias); } else { list.splice(i, 1); }
      store(PIN_KEY, JSON.stringify(list));
      show();
    }

    /* --------------------------------------------------------------- theme, size */
    function applyTheme(dark) {
      root.classList.toggle('dark', !!dark);
      /* The host's <body> keeps its margin; paint it in the page's own background so no light strip is left
         at the top in dark mode (and give the host its colour back in light mode). */
      document.body.style.backgroundColor = dark ? getComputedStyle(root).getPropertyValue('--cpj-bg').trim() : '';
    }
    var scale = 1;
    function setScale(s, keep) {
      scale = Math.max(0.7, Math.min(2.2, Math.round(s * 10) / 10));
      root.style.setProperty('--cpj-scale', String(scale));
      if (keep) { store(SCALE_KEY, String(scale)); }
    }

    /* ---------------------------------------------------------------- data */
    function load() {
      var url = apiUrl('projects');
      var p;
      if (typeof accessCT === 'function') {
        p = accessCT(url, {});
      } else {
        p = fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
          .then(function (r) { return r.json(); });
      }
      return p.then(function (out) {
        if (!out || out.error) { fail((out && out.error) || 'empty answer'); return; }
        DATA = { pages: out.pages || [], others: out.others || [], repos: out.repos || [] };
        $('cpj-error').hidden = true;
        show();
      }).catch(function (e) { fail(String(e)); });
    }
    function loadView() {
      return call('view', {}).then(function (v) {
        VIEW = v;
        $('cpj-error').hidden = true;
        show();
      }).catch(function (e) { fail(e.message || String(e)); });
    }
    function fail(msg) {
      var box = $('cpj-error');
      box.textContent = 'Could not load the page list: ' + msg;
      box.hidden = false;
    }

    /* -------------------------------------------------------------- the cards */
    function matches(p, ws) {
      if (!ws.length) { return true; }
      var hay = [p.page, p.alias, p.name, p.desc, p.repo, (p.tags || []).join(' ')].join(' ').toLowerCase();
      return ws.every(function (w) { return hay.indexOf(w) >= 0; });
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
    function renderCards(q) {
      var ws = words(q), pinned = pins();
      var none = DATA.pages.length === 0;
      var shown = DATA.pages.filter(function (p) { return matches(p, ws); });
      var html = [];
      var pin = shown.filter(function (p) { return pinned.indexOf(p.alias) >= 0; });
      if (pin.length) { html.push(group('Pinned', pin.map(function (p) { return card(p, true); }), pin.length)); }
      var rest = shown.filter(function (p) { return pinned.indexOf(p.alias) < 0; });
      DATA.repos.forEach(function (repo) {
        var items = rest.filter(function (p) { return (p.repo || '') === repo; });
        if (items.length) { html.push(group(repo || 'local', items.map(function (p) { return card(p, false); }), items.length)); }
      });
      /* No page at all (a fresh install): say what a page is instead of an empty grid. */
      $('cpj-empty').hidden = !none;
      $('cpj-groups').innerHTML = html.length ? html.join('') :
        (none ? '' : '<p class="cpj-muted">No page matches <code>' + esc(q) + '</code>.</p>');
      $('cpj-count').textContent = none ? '' : (ws.length
        ? '(' + shown.length + ' of ' + DATA.pages.length + ' shown)'
        : '(' + DATA.pages.length + (DATA.pages.length === 1 ? ' page)' : ' pages)'));
      var others = DATA.others || [];
      $('cpj-others').hidden = others.length === 0;
      $('cpj-others-count').textContent = others.length;
      $('cpj-others-list').innerHTML = others.map(function (p) {
        return '<li><code>' + esc(p.alias) + '</code> - ' + esc(p.repo) + (p.name ? ' - ' + esc(p.name.split(' - ')[0]) : '') + '</li>';
      }).join('');
      var first = $('cpj-groups').querySelector('.cpj-card');
      if (first && ws.length) { first.classList.add('cpj-hit'); }
    }

    /* -------------------------------------------------------------- the view */
    /* No view yet: what it is, and (where this browser may write) where to keep it */
    function makePanel() {
      var n = (VIEW.loose || []).length;
      var box = h('div', { 'class': 'cpj-make' },
        h('h2', {}, 'Your own view of the pages'),
        h('p', {}, 'Sections of buttons with names of your own, in the order you choose - instead of the cards. It starts from the ' +
          n + ' page' + (n === 1 ? '' : 's') + ' of this machine: a section per repository, a button per page. Then Edit: rename a section or a ' +
          'button, drag them, mark the important ones, add sections, and buttons for the pages of other machines (their addresses).'));
      if (!VIEW.edit) {
        box.appendChild(h('p', { 'class': 'cpj-muted' }, 'A view is made from a browser on this machine, or one that signed in with the server\'s password.'));
        return box;
      }
      var sel = h('select', { id: 'cpj-make-repo', 'aria-label': 'The repository that keeps the view' });
      (VIEW.repos || []).forEach(function (r) {
        var o = h('option', { value: r }, r);
        if (r === VIEW.default_repo) { o.selected = true; }
        sel.appendChild(o);
      });
      var go = h('button', { type: 'button', 'class': 'cpj-go', id: 'cpj-make-go' }, 'Make my view');
      go.addEventListener('click', function () {
        go.disabled = true;
        call('view_make', { repo: sel.value })
          .then(function (r) { toast('Your view: ' + r.made + ' buttons, in ' + r.home); return loadView(); })
          .catch(function (e) { toast(e.message, true); go.disabled = false; });
      });
      box.appendChild(h('p', {}, 'Its buttons are artifacts of ', h('code', {}, 'cserver.projects'), ', one per button, kept in the repository ',
        sel, ' - choose one that syncs between your machines, and each of them shows the same view.'));
      box.appendChild(h('p', {}, go));
      return box;
    }
    function board_() {
      if (!b) {
        b = board({ edit: !!CFG.edit, host: root, cref_url: CFG.cref_url || '', footnote: true,
                    call: function (action, p) { return call('view_' + action, p); },
                    changed: loadView, ui: { toast: toast, toastAction: toastAction },
                    top: function () { return $('cpj-bar') ? $('cpj-bar').getBoundingClientRect().bottom : 0; } });
        $('cpj-board').appendChild(b.el);
      }
      return b;
    }
    function renderView(q) {
      var box = $('cpj-board');
      var panel = box.querySelector('.cpj-make');
      if (panel) { panel.remove(); }
      if (!VIEW) { $('cpj-count').textContent = ''; return; }
      if (!VIEW.buttons.length) {
        board_().el.hidden = true;
        box.insertBefore(makePanel(), box.firstChild);
        $('cpj-count').textContent = '';
        return;
      }
      var bd = board_();
      bd.el.hidden = false;
      var r = bd.set(VIEW, words(q));
      $('cpj-count').textContent = words(q).length ? '(' + r.shown + ' of ' + r.total + ' shown)'
                                                    : '(' + r.total + ' buttons in ' + r.sections + ' sections)';
    }

    /* ----------------------------------------------------------- the two ways */
    function show() {
      var q = $('cpj-search').value;
      root.classList.toggle('cpj-custom', custom);
      $('cpj-custom').setAttribute('aria-pressed', custom ? 'true' : 'false');
      $('cpj-custom').classList.toggle('cpj-on', custom);
      $('cpj-subtext').textContent = custom ? 'Your own view of the pages of this server.'
                                            : 'Every cserver.* page plugged into this machine, grouped by repository.';
      var canEdit = custom && VIEW && VIEW.edit && VIEW.buttons.length > 0;
      var editing = !!(b && b.editing());
      if (!canEdit && editing) { b.setEditing(false); editing = false; }
      $('cpj-edit').hidden = !canEdit;
      $('cpj-add').hidden = !canEdit;
      $('cpj-edit').textContent = editing ? 'Done' : 'Edit';
      $('cpj-edit').classList.toggle('cpj-on', editing);
      $('cpj-edit').setAttribute('aria-pressed', editing ? 'true' : 'false');
      if (custom) {
        $('cpj-groups').hidden = true;
        $('cpj-empty').hidden = true;
        $('cpj-others').hidden = true;
        $('cpj-board').hidden = false;
        renderView(q);
      } else {
        $('cpj-board').hidden = true;
        $('cpj-groups').hidden = false;
        renderCards(q);
      }
    }
    function setCustom(on) {
      custom = !!on;
      store(CUSTOM_KEY, custom ? '1' : '0');
      if (b && b.editing()) { b.setEditing(false); }
      show();
      if (custom && !VIEW) { loadView(); }
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
    function openFirst() {
      if (b && b.editing() && custom) { return; }
      var a = custom ? $('cpj-board').querySelector('.cpj-pill[href]') : $('cpj-groups').querySelector('.cpj-card .cpj-link');
      if (a) { window.location.href = a.getAttribute('href'); }
    }

    /* one dark or light for every page of this server: cmeta.theme, read first (this page's own key until there is
       one, which then becomes the shared one), written by the switch, followed when another page changes it */
    var t0 = stored(SHARED_THEME);
    if (!t0) { t0 = stored(THEME_KEY); if (t0) { store(SHARED_THEME, t0); } }
    applyTheme(t0 ? t0 === 'dark' : !!CFG.dark_mode);
    window.addEventListener('storage', function (e) { if (e.key === SHARED_THEME && e.newValue) { applyTheme(e.newValue === 'dark'); } });
    var asked = parseFloat((/[?&]font=([\d.]+)/.exec(window.location.search) || [])[1]);
    setScale(asked > 0 ? asked : (parseFloat(stored(SCALE_KEY)) || 1), false);

    $('cpj-json').href = apiUrl('projects');
    if (window.matchMedia && window.matchMedia('(max-width: 640px)').matches) { $('cpj-search').placeholder = 'Search the pages'; }
    $('cpj-search').addEventListener('input', show);
    $('cpj-search').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); openFirst(); }
      else if (e.key === 'Escape') { this.value = ''; show(); }
    });
    $('cpj-theme').addEventListener('click', function () {
      var dark = !root.classList.contains('dark');
      applyTheme(dark);
      store(SHARED_THEME, dark ? 'dark' : 'light');
      store(THEME_KEY, dark ? 'dark' : 'light');
    });
    $('cpj-smaller').addEventListener('click', function () { setScale(scale - 0.1, true); });
    $('cpj-bigger').addEventListener('click', function () { setScale(scale + 0.1, true); });
    $('cpj-reload').addEventListener('click', function () { load(); if (custom) { loadView(); } });
    $('cpj-custom').addEventListener('click', function () { setCustom(!custom); });
    $('cpj-edit').addEventListener('click', function () { board_().setEditing(!board_().editing()); show(); });
    $('cpj-add').addEventListener('click', function () { board_().add(''); });

    $('cpj-groups').addEventListener('click', function (e) {
      var pinBtn = e.target.closest('.cpj-pin');
      var copyBtn = e.target.closest('.cpj-copy');
      var cardEl = e.target.closest('.cpj-card');
      if (!cardEl) { return; }
      var alias = cardEl.getAttribute('data-alias');
      if (pinBtn) { e.preventDefault(); togglePin(alias); return; }
      if (copyBtn) { e.preventDefault(); copyUrl(alias, copyBtn); return; }
      if (!e.target.closest('a')) {
        var a = cardEl.querySelector('.cpj-link');
        if (a) { window.location.href = a.getAttribute('href'); }
      }
    });
    document.addEventListener('keydown', function (e) {
      var tag = (e.target && e.target.tagName) || '';
      if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(tag) && !e.target.isContentEditable) {
        e.preventDefault();
        $('cpj-search').focus();
      }
    });

    show();
    load();
    if (custom) { loadView(); }
  }

  window.CmetaProjects = { board: board, page: page, hits: hits, words: words };
  if (document.getElementById('cpj')) {
    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', page); } else { page(); }
  }
})();
