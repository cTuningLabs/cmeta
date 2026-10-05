/* Licensed under the Apache License, Version 2.0. See the COPYRIGHT and LICENSE files in the project root for details.
 *
 * cserver.browse - the graph: a force layout in SVG, with no third-party libraries.
 *
 * The layout is category membership alone: each artifact hangs off its category node on a spring, categories
 * push each other apart, and the connections between artifacts are never springs - as springs they pulled every
 * connected artifact into one knot. A connection is a dashed line, drawn for the node under the pointer and for
 * the selected one, or for all at once (setLinks); a `uses` edge (a task and what it runs) is always drawn, with
 * an arrow. Without category nodes, the connections are the springs, and are drawn.
 * Hover, click and drag go to the node under the pointer, worked out from its position: a dot is a few pixels
 * across on a large graph, so the target is a padded box around the dot and its name. Names never cover each
 * other (unless every name is asked for): the hovered node and its neighbours first, then the biggest categories.
 * Zoomed out, dots and names shrink less than the drawing, so a graph fitted at 10% stays readable.
 *
 *   wheel          zoom about the pointer, by how far the wheel turned (it stops when the wheel stops)
 *   drag           pan; grab a dot to move it
 *   click          select: its connections stay drawn, opts.onSelect(node)
 *   double-click   opts.onFocus(node); on the background: fit
 *
 * CBRGraph.create(svg, {nodes, links}, opts) -> {stop, fit, reset, relayout, setLabels, setLinks, setDark,
 * select, resize, layoutMs, buildMs}. A node: {id, kind: artifact|category|core, label, cat, deg, n, hop, added};
 * a link: {s, t, k: member|core|link|uses}.
 */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';

  // The categorical palette (validated slot order, light and dark steps). A category keeps its colour whatever
  // else is drawn: the slot comes from its name, not from its rank. Beyond 8 categories colours repeat, and the
  // category node's label (each artifact hangs off it) says which is which.
  var PALETTE_LIGHT = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'];
  var PALETTE_DARK = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'];

  function colour(cat, dark) {
    var h = 0, s = String(cat || '');
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    var pal = dark ? PALETTE_DARK : PALETTE_LIGHT;
    return pal[h % pal.length];
  }

  // Pointing tolerances
  var HIT_PAD = 5;        // world units of room around a dot and its label
  var HIT_TOL_PX = 11;    // how far outside its box the pointer still counts
  var MIN_HIT_PX = 20;    // a box is never thinner than this on screen ...
  var MIN_HIT_MAX = 34;   // ... but that must not run away when zoomed far out
  var DRAG_TOL_PX = 7;    // grabbing a dot to move it is fussier: the rest of the canvas pans

  var DECAY = 0.985;      // the layout cools by this per step and stops below ALPHA_MIN (~350 steps)
  var ALPHA_MIN = 0.005;

  function el(tag, cls) {
    var e = document.createElementNS(NS, tag);
    if (cls) e.setAttribute('class', cls);
    return e;
  }
  function now() { return (window.performance && performance.now) ? performance.now() : Date.now(); }

  function create(svg, data, opts) {
    var tStart = now();
    opts = opts || {};
    if (svg._cbrStop) svg._cbrStop();
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var W = svg.clientWidth || 900, H = svg.clientHeight || 600;
    var nodes = (data.nodes || []).slice();
    var N = nodes.length;
    var byId = {};
    nodes.forEach(function (n, i) { n.i = i; byId[n.id] = n; });
    var links = (data.links || []).filter(function (l) { return byId[l.s] && byId[l.t] && l.s !== l.t; });
    var nbr = {};
    nodes.forEach(function (n) { nbr[n.id] = {}; });
    links.forEach(function (l) { l.a = byId[l.s]; l.b = byId[l.t]; nbr[l.s][l.t] = 1; nbr[l.t][l.s] = 1; });

    var dark = !!opts.dark;
    var namesAll = !!opts.labelsAll;           // every artifact's name, even where names overlap
    var showLinks = !!opts.showLinks;

    function radius(n) {
      if (n.kind === 'core') return 15;
      if (n.kind === 'category') return 8 + Math.min(9, Math.sqrt(n.n || 1));
      return 4 + Math.min(6, n.deg || 0) + (n.hop === 0 ? 3 : 0);
    }

    /* -------------------------------------------------------------- layout */
    // The forces scale with N: what looks right for 50 nodes collapses into a blob at 600 unless repulsion grows
    // and the pull to the centre weakens.
    var scale = Math.sqrt(Math.max(N, 1) / 50);
    var REPEL = 6000 * scale, SPRING = 0.035, CENTER = 0.010 / scale, DAMP = 0.84;
    var CUT2 = Math.pow(700 * scale, 2), SPREAD = 260 * scale;
    var seed = 7;
    function rnd() { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; }

    // A seeded start, so the same data lays out the same way: the categories on a ring, every artifact near its
    // category, the cMeta node in the middle. Starting near the answer also settles in far fewer steps.
    var hubs = nodes.filter(function (n) { return n.kind === 'category'; });
    var hubOf = {};
    links.forEach(function (l) { if (l.k === 'member') hubOf[l.t] = l.a; });
    function seedLayout() {
      seed = 7;
      hubs.forEach(function (n, i) {
        var a = i / Math.max(hubs.length, 1) * Math.PI * 2;
        n.x = W / 2 + Math.cos(a) * SPREAD * 0.8;
        n.y = H / 2 + Math.sin(a) * SPREAD * 0.8;
      });
      nodes.forEach(function (n) {
        if (n.kind === 'core') { n.x = W / 2; n.y = H / 2; }
        else if (n.kind === 'artifact') {
          var hub = hubOf[n.id];
          var a = rnd() * Math.PI * 2, r = SPREAD * (hub ? 0.25 : 1) * (0.3 + rnd() * 0.7);
          n.x = (hub ? hub.x : W / 2) + Math.cos(a) * r;
          n.y = (hub ? hub.y : H / 2) + Math.sin(a) * r;
        }
        n.vx = 0; n.vy = 0;
      });
    }
    seedLayout();

    // With category nodes, membership is the only spring and a connection is an annotation. Without them there
    // is nothing else to give the picture a shape: the connections become (weaker) springs and are always drawn.
    var linksShape = !hubs.length;
    var springs = links.filter(function (l) {
      return l.k === 'member' || l.k === 'core' || (linksShape && (l.k === 'link' || l.k === 'uses' || l.k === 'ai'));
    });
    function restLen(l) { return (l.k === 'core' ? 170 : (l.k === 'member' ? 80 : 60)) * scale; }
    function stiffness(l) { return l.k === 'member' || l.k === 'core' ? SPRING : SPRING * 0.5; }

    var alpha = 1;
    function step() {
      var i, j, n, m, dx, dy, d2, d, f;
      for (i = 0; i < N; i++) {
        n = nodes[i];
        for (j = i + 1; j < N; j++) {
          m = nodes[j];
          dx = n.x - m.x; dy = n.y - m.y;
          d2 = dx * dx + dy * dy || 0.01;
          if (d2 > CUT2) continue;
          f = REPEL / Math.max(d2, 25);          // no explosion when two dots start on top of each other
          if (n.kind !== 'artifact') f *= 2.2;
          if (m.kind !== 'artifact') f *= 2.2;
          d = Math.sqrt(d2); dx /= d; dy /= d;
          n.vx += dx * f; n.vy += dy * f;
          m.vx -= dx * f; m.vy -= dy * f;
        }
      }
      for (i = 0; i < springs.length; i++) {
        var l = springs[i], a = l.a, b = l.b;
        dx = b.x - a.x; dy = b.y - a.y;
        d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        f = (d - restLen(l)) * stiffness(l);
        dx /= d; dy /= d;
        a.vx += dx * f; a.vy += dy * f;
        b.vx -= dx * f; b.vy -= dy * f;
      }
      for (i = 0; i < N; i++) {
        n = nodes[i];
        if (n.fixed) { n.vx = n.vy = 0; continue; }
        var pull = n.kind === 'core' ? CENTER * 8 : CENTER;
        n.vx += (W / 2 - n.x) * pull;
        n.vy += (H / 2 - n.y) * pull;
        n.vx *= DAMP; n.vy *= DAMP;
        n.x += n.vx * alpha; n.y += n.vy * alpha;
      }
      alpha *= DECAY;
    }

    /* -------------------------------------------------------------- render */
    var defs = el('defs');
    defs.innerHTML = '<marker id="cbr-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerUnits="userSpaceOnUse" ' +
      'markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z"/></marker>';
    svg.appendChild(defs);
    var arrow = defs.firstChild;
    // Layers, bottom up: the edges, the hover box, the dots, the names (so no dot covers a name)
    var gRoot = el('g'), gE = el('g'), gN = el('g'), gL = el('g');
    var hoverBox = el('rect', 'cbr-hover');
    hoverBox.setAttribute('rx', '4');
    hoverBox.setAttribute('visibility', 'hidden');
    gRoot.appendChild(gE); gRoot.appendChild(hoverBox); gRoot.appendChild(gN); gRoot.appendChild(gL);
    svg.appendChild(gRoot);

    var edgeEls = links.map(function (l) {
      var e = el('line', 'edge ' + l.k + (l.k === 'link' && !linksShape ? ' ghost' : ''));
      if (l.k === 'uses' || l.k === 'ai') e.setAttribute('marker-end', 'url(#cbr-arrow)');
      gE.appendChild(e);
      return e;
    });
    var labelEls = [];
    var nodeEls = nodes.map(function (n) {
      var c = el('circle', 'node ' + n.kind + (n.added ? ' added' : '') + (n.hop === 0 ? ' focus' : ''));
      if (n.kind !== 'core') c.setAttribute('fill', colour(n.cat, dark));
      gN.appendChild(c);
      var t = el('text', 'lbl ' + n.kind + (n.hop === 0 ? ' focus' : ''));
      t.textContent = n.label.length > 48 ? n.label.slice(0, 46) + '…' : n.label;
      gL.appendChild(t);
      labelEls.push(t);
      return c;
    });
    var circles = nodeEls;
    function fontPx(n) { return n.kind === 'core' ? 14 : (n.kind === 'category' ? 12 : 10.5); }

    // Label widths at the nominal size, measured once while every label shows
    var labelW = labelEls.map(function (t) {
      try { return t.getComputedTextLength(); } catch (e) { return 0; }
    });
    var shownLabel = labelEls.map(function () { return true; });

    // Zoomed out, dots and names shrink less than the drawing - a dot to 40% of its size at most, a name to 85% -
    // so a large graph fitted at 10% stays readable; zoomed in, they grow with it. Lines never scale (CSS).
    // tsDot and tsText are the world units of one nominal pixel.
    var tsDot = 0, tsText = 0;
    function applySizes() {
      gRoot.style.setProperty('--cbr-ts', String(tsText));
      arrow.setAttribute('markerWidth', String(8 * tsText));
      arrow.setAttribute('markerHeight', String(8 * tsText));
      for (var i = 0; i < N; i++) circles[i].setAttribute('r', String(radius(nodes[i]) * tsDot));
    }
    function placeLabel(i) {                   // a name sits right of its dot, in world units
      var n = nodes[i];
      labelEls[i].setAttribute('x', String(n.x + radius(n) * tsDot + 4 * tsText));
      labelEls[i].setAttribute('y', String(n.y + 3.5 * tsText));
    }

    var view = {x: 0, y: 0, k: 1};
    var hitK = 0;
    function applyView() {
      gRoot.setAttribute('transform', 'translate(' + view.x + ',' + view.y + ') scale(' + view.k + ')');
      // sizes, names and hit boxes follow the zoom - every ~10% of it is enough
      if (hitK === 0 || Math.abs(Math.log(view.k / hitK)) > 0.1) {
        hitK = view.k;
        var d2 = Math.max(1, 0.4 / view.k), t2 = Math.max(1, 0.85 / view.k);
        if (d2 !== tsDot || t2 !== tsText) { tsDot = d2; tsText = t2; applySizes(); draw(); }
        placeLabels();
      }
      if (opts.onZoom) opts.onZoom(view.k);
    }

    // Which names show. Always: the node under the pointer (or the selected one) with its neighbours, and every
    // artifact with "all names". Then, only where they cover no name already placed: the categories, the biggest
    // first, and the artifacts of a small graph, the best connected first. Checked on screen, in 64 px cells.
    var placeOrder = nodes.map(function (n, i) { return i; }).sort(function (a, b) {
      var A = nodes[a], B = nodes[b];
      var ka = A.kind === 'core' ? 0 : (A.kind === 'category' ? 1 : 2);
      var kb = B.kind === 'core' ? 0 : (B.kind === 'category' ? 1 : 2);
      if (ka !== kb) return ka - kb;
      return ka === 1 ? (B.n || 0) - (A.n || 0) : (B.deg || 0) - (A.deg || 0);
    });
    function placeLabels() {
      var id = hover ? hover.id : (pinned ? pinned.id : null);
      var grid = {}, CELL = 64, k = view.k, i, j;
      function rectOf(i) {
        var n = nodes[i], h = fontPx(n) * tsText * k * 1.2;
        var x = (n.x + radius(n) * tsDot + 4 * tsText) * k + view.x, y = n.y * k + view.y;
        return {x0: x - 2, x1: x + labelW[i] * tsText * k + 2, y0: y - h / 2, y1: y + h / 2};
      }
      function each(r, fn) {
        for (var cx = Math.floor(r.x0 / CELL); cx <= Math.floor(r.x1 / CELL); cx++) {
          for (var cy = Math.floor(r.y0 / CELL); cy <= Math.floor(r.y1 / CELL); cy++) {
            if (fn(cx + ',' + cy)) return true;
          }
        }
        return false;
      }
      function covers(r) {
        return each(r, function (key) {
          var list = grid[key] || [];
          for (var m = 0; m < list.length; m++) {
            var o = list[m];
            if (r.x0 < o.x1 && o.x0 < r.x1 && r.y0 < o.y1 && o.y0 < r.y1) return true;
          }
          return false;
        });
      }
      function take(r) { each(r, function (key) { (grid[key] = grid[key] || []).push(r); return false; }); }
      var want = new Array(N), force = new Array(N);
      for (i = 0; i < N; i++) {
        var n = nodes[i], near = !!id && (id === n.id || !!nbr[id][n.id]);
        force[i] = near || (n.kind === 'artifact' && namesAll);
        want[i] = force[i] || n.kind !== 'artifact' || N <= 90;
      }
      var on = new Array(N);
      for (i = 0; i < N; i++) if (force[i]) { on[i] = true; take(rectOf(i)); }
      for (j = 0; j < N; j++) {
        i = placeOrder[j];
        if (force[i] || !want[i]) continue;
        var r = rectOf(i);
        if (!covers(r)) { on[i] = true; take(r); }
      }
      for (i = 0; i < N; i++) {
        var show = !!on[i];
        if (show !== shownLabel[i]) {
          shownLabel[i] = show;
          labelEls[i].classList.toggle('lbl-hide', !show);
        }
        if (show) placeLabel(i);
      }
      sizeBoxes();                             // a box frames the dot and its name, when it shows
    }

    // box[i] = {x0, x1, y}: world units around the node centre - the dot, and its name when it shows
    var boxes = [];
    function sizeBox(i) {
      var n = nodes[i], r = radius(n) * tsDot, pad = HIT_PAD * tsDot;
      var minHalf = Math.min(MIN_HIT_PX / view.k / 2, MIN_HIT_MAX * tsDot);
      var right = shownLabel[i] ? r + (4 + (labelW[i] || 0)) * tsText : r;
      boxes[i] = {x0: Math.min(-r - pad, -minHalf), x1: Math.max(right + pad, minHalf),
                  y: Math.max(r + pad, minHalf, shownLabel[i] ? fontPx(n) * 0.6 * tsText : 0)};
    }
    function sizeBoxes() { for (var i = 0; i < N; i++) sizeBox(i); }

    function boxDist(i, wx, wy) {
      var n = nodes[i], b = boxes[i];
      if (!b) return Infinity;
      var dx = Math.max(n.x + b.x0 - wx, 0, wx - (n.x + b.x1));
      var dy = Math.max(n.y - b.y - wy, 0, wy - (n.y + b.y));
      return Math.sqrt(dx * dx + dy * dy);
    }
    // The node under the pointer: of the boxes it is in or near, the one whose dot it is closest to (inside a dot
    // beats anything outside), or whose name it is on. So a big dot wins where the pointer is on it, and a small
    // one next to it - an artifact by its category - stays reachable.
    function nodeAt(wx, wy) {
      var tol = HIT_TOL_PX / view.k, best = null, bestS = Infinity;
      for (var i = 0; i < N; i++) {
        if (boxDist(i, wx, wy) > tol) continue;
        var n = nodes[i], dx = wx - n.x, dy = wy - n.y, r = radius(n) * tsDot;
        var s = Math.sqrt(dx * dx + dy * dy) - r;
        if (shownLabel[i] && dx > r && dx < r + (4 + labelW[i]) * tsText &&
            Math.abs(dy) < fontPx(n) * 0.6 * tsText) s = Math.min(s, 0);
        if (s < bestS) { best = n; bestS = s; }
      }
      return best;
    }
    function dotAt(wx, wy) {
      var tol = DRAG_TOL_PX / view.k, best = null, bestD = Infinity;
      for (var i = 0; i < N; i++) {
        var n = nodes[i];
        var d = Math.sqrt((n.x - wx) * (n.x - wx) + (n.y - wy) * (n.y - wy)) - radius(n) * tsDot;
        if (d <= tol && d < bestD) { best = n; bestD = d; }
      }
      return best;
    }

    function showHover(n) {
      var b = n && boxes[n.i];
      if (!b) { hoverBox.setAttribute('visibility', 'hidden'); return; }
      hoverBox.setAttribute('x', String(n.x + b.x0));
      hoverBox.setAttribute('y', String(n.y - b.y));
      hoverBox.setAttribute('width', String(b.x1 - b.x0));
      hoverBox.setAttribute('height', String(2 * b.y));
      hoverBox.setAttribute('visibility', 'visible');
    }

    function draw() {
      for (var i = 0; i < links.length; i++) {
        var l = links[i], a = l.a, b = l.b, e = edgeEls[i], x2 = b.x, y2 = b.y;
        if (l.k === 'uses' || l.k === 'ai') {  // stop at the target's edge, so the arrowhead shows
          var dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 1;
          var r = radius(b) * tsDot + 3 * tsText;
          x2 -= dx / d * r; y2 -= dy / d * r;
        }
        e.setAttribute('x1', a.x); e.setAttribute('y1', a.y);
        e.setAttribute('x2', x2); e.setAttribute('y2', y2);
      }
      for (var j = 0; j < N; j++) {
        nodeEls[j].setAttribute('cx', nodes[j].x);
        nodeEls[j].setAttribute('cy', nodes[j].y);
        if (shownLabel[j]) placeLabel(j);
      }
      if (hover) showHover(hover);
    }

    /* -------------------------------------------------------------- highlight */
    var hover = null, pinned = null;
    // The node under the pointer (else the selected one) and its neighbours stay; the rest fades. Their names
    // show, and the connections of that node are drawn.
    function highlight() {
      var id = hover ? hover.id : (pinned ? pinned.id : null);
      for (var i = 0; i < N; i++) {
        var n = nodes[i];
        var near = !!id && (id === n.id || !!nbr[id][n.id]);
        nodeEls[i].classList.toggle('dim', !!id && !near);
        labelEls[i].classList.toggle('dim', !!id && !near);
        nodeEls[i].classList.toggle('pinned', !!pinned && pinned.id === n.id);
      }
      placeLabels();
      for (var k = 0; k < links.length; k++) {
        var l = links[k], on = !!id && (l.s === id || l.t === id);
        var e = edgeEls[k];
        e.classList.toggle('hi', on);
        e.classList.toggle('dim', !!id && !on);
        if (l.k === 'link' && !linksShape) {
          var shown = showLinks || on;
          e.classList.toggle('on', shown);
          // the category colour only when every connection is drawn: there a hundred identical dashes say
          // nothing, and the colour says where each one leads; one revealed line reads best in plain ink
          e.style.stroke = (shown && showLinks && !on) ? colour(l.a.cat, dark) : '';
        }
      }
    }
    function setHover(n) {
      if (n === hover) return;
      hover = n;
      highlight();
      showHover(n);
      svg.classList.toggle('over', !!n);
    }

    /* -------------------------------------------------------------- pan, zoom, drag */
    function toWorld(ev) {
      var r = svg.getBoundingClientRect();
      return {x: (ev.clientX - r.left - view.x) / view.k, y: (ev.clientY - r.top - view.y) / view.k};
    }
    var drag = null, pan = null, moved = false, userView = false;

    // While a large graph is being arranged out of sight, the pointer does nothing (there is nothing to point at)
    svg.onpointerdown = function (ev) {
      if (hidden || (ev.button !== undefined && ev.button !== 0)) return;
      var w = toWorld(ev), n = dotAt(w.x, w.y);
      moved = false;
      if (n) { drag = {node: n, x: ev.clientX, y: ev.clientY}; n.fixed = true; svg.classList.add('dragging'); }
      else { pan = {x: ev.clientX, y: ev.clientY, vx: view.x, vy: view.y}; svg.classList.add('panning'); }
      try { svg.setPointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
    };
    svg.onpointermove = function (ev) {
      if (drag) {
        if (Math.abs(ev.clientX - drag.x) + Math.abs(ev.clientY - drag.y) > 3) moved = true;
        var w = toWorld(ev);
        drag.node.x = w.x; drag.node.y = w.y;
        draw();
        showHover(drag.node);
      } else if (pan) {
        if (Math.abs(ev.clientX - pan.x) + Math.abs(ev.clientY - pan.y) > 3) moved = true;
        view.x = pan.vx + (ev.clientX - pan.x);
        view.y = pan.vy + (ev.clientY - pan.y);
        userView = true;
        applyView();
      } else if (!hidden) {
        var p = toWorld(ev);
        setHover(nodeAt(p.x, p.y));
      }
    };
    svg.onpointerup = svg.onpointercancel = function () {
      if (drag) {
        drag.node.fixed = false;
        if (moved) kick(0.25);
      }
      drag = null; pan = null;
      svg.classList.remove('dragging'); svg.classList.remove('panning');
    };
    svg.onpointerleave = function () { if (!drag && !pan) setHover(null); };
    // A click selects at once; onSelect (the detail) waits for the double-click interval, so that a double-click
    // focuses without opening the detail of the same node on the way.
    var selectTimer = 0;
    svg.onclick = function (ev) {
      if (hidden) return;
      if (moved) { moved = false; return; }   // that was a pan or a move, not a click
      var w = toWorld(ev), n = nodeAt(w.x, w.y);
      pinned = n;                              // the background deselects
      highlight();
      clearTimeout(selectTimer);
      if (n && opts.onSelect && ev.detail < 2) selectTimer = setTimeout(function () { opts.onSelect(n); }, 300);
    };
    svg.ondblclick = function (ev) {
      clearTimeout(selectTimer);
      if (hidden) return;
      var w = toWorld(ev), n = nodeAt(w.x, w.y);
      if (!n) { fit(); return; }
      if (opts.onFocus) opts.onFocus(n);
    };

    // Zoom by how far the wheel turned, applied at most once per frame: a smooth wheel or a touchpad sends a
    // burst of small events for one notch and a few more after the hand stops, and a fixed step per event made one
    // small turn zoom many times over and drift on. Proportional, it stops when the wheel stops.
    var wheelDy = 0, wheelX = 0, wheelY = 0, wheelRaf = 0;
    function zoomTo(k2, mx, my) {
      k2 = Math.max(0.05, Math.min(20, k2));
      view.x = mx - (mx - view.x) * (k2 / view.k);
      view.y = my - (my - view.y) * (k2 / view.k);
      view.k = k2;
      applyView();
    }
    function zoomStep() {
      wheelRaf = 0;
      var f = Math.exp(-Math.max(-300, Math.min(300, wheelDy)) * 0.0015);
      wheelDy = 0;
      zoomTo(view.k * f, wheelX, wheelY);
    }
    svg.onwheel = function (ev) {
      ev.preventDefault();
      if (hidden) return;
      var dy = ev.deltaY * (ev.deltaMode === 1 ? 16 : (ev.deltaMode === 2 ? H : 1));
      if (Math.abs(dy) < 0.5) return;
      var r = svg.getBoundingClientRect();
      wheelX = ev.clientX - r.left; wheelY = ev.clientY - r.top;
      wheelDy += dy;
      userView = true;
      if (!wheelRaf) wheelRaf = requestAnimationFrame(zoomStep);
    };

    function fit() {
      if (!N) return;
      var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      nodes.forEach(function (n) {
        x0 = Math.min(x0, n.x); x1 = Math.max(x1, n.x); y0 = Math.min(y0, n.y); y1 = Math.max(y1, n.y);
      });
      var pad = 70;
      var k = Math.min((W - pad) / Math.max(x1 - x0, 1), (H - pad) / Math.max(y1 - y0, 1));
      view.k = Math.max(0.05, Math.min(2.5, k));
      view.x = W / 2 - (x0 + x1) / 2 * view.k;
      view.y = H / 2 - (y0 + y1) / 2 * view.k;
      applyView();
    }
    function reset() {                         // 100%, centred on the middle of the drawing
      var cx = 0, cy = 0;
      nodes.forEach(function (n) { cx += n.x; cy += n.y; });
      cx /= Math.max(N, 1); cy /= Math.max(N, 1);
      view.k = 1; view.x = W / 2 - cx; view.y = H / 2 - cy;
      userView = true;
      applyView();
    }

    /* -------------------------------------------------------------- the loop */
    // The layout runs before the picture shows, and the picture is fitted once: a drawing that moves and then
    // jumps to fit looks like zoom drifting. Up to ~0.4 s it runs at once (a few hundred nodes settle in that);
    // a larger graph goes on out of sight in frames of ~12 ms, under the spinner, and appears when it settles.
    // Later runs (a moved node, a resize) are small and stay on screen.
    var raf = 0, settled = false, t0 = now(), tLayout = 0, tBuild = t0 - tStart, tPlaced = 0, hidden = false;
    function conceal(on) {
      if (on === hidden) return;
      hidden = on;
      gRoot.style.visibility = on ? 'hidden' : '';
      if (opts.onBusy) opts.onBusy(on, N);
    }
    function frame() {
      raf = 0;
      var until = now() + 12;
      do { step(); } while (alpha > ALPHA_MIN && now() < until);
      if (alpha > ALPHA_MIN) {
        if (!hidden) {
          draw();
          if (now() - tPlaced > 250) { placeLabels(); tPlaced = now(); }   // names follow, a few times a second
        }
        raf = requestAnimationFrame(frame);
        return;
      }
      draw();
      if (!settled) {
        settled = true;
        tLayout = now() - t0;
        if (hidden && !userView) fit();
        placeLabels();
        conceal(false);
        if (opts.onSettled) opts.onSettled(tLayout);
      }
    }
    function kick(a) {
      alpha = Math.max(alpha, a);
      if (!raf) raf = requestAnimationFrame(frame);
    }
    var until0 = now() + 400;
    while (alpha > ALPHA_MIN && now() < until0) step();
    draw();
    fit();                                     // sets the sizes, places the names, sizes the boxes
    if (opts.selectId && byId[opts.selectId]) { pinned = byId[opts.selectId]; }
    highlight();
    if (alpha > ALPHA_MIN) conceal(true);
    raf = requestAnimationFrame(frame);

    function stop() {
      clearTimeout(selectTimer);
      conceal(false);
      if (raf) cancelAnimationFrame(raf);
      if (wheelRaf) cancelAnimationFrame(wheelRaf);
      raf = wheelRaf = 0;
      svg.onpointerdown = svg.onpointermove = svg.onpointerup = svg.onpointercancel = svg.onpointerleave = null;
      svg.onclick = svg.ondblclick = svg.onwheel = null;
      svg._cbrStop = null;
    }
    svg._cbrStop = stop;

    return {
      stop: stop,
      fit: function () { userView = false; fit(); },
      reset: reset,
      relayout: function () {                  // from the seeded start again: undoes every node you moved
        seedLayout();
        alpha = 1; settled = false; userView = false; t0 = now();
        conceal(true);                         // out of sight until it settles, then fitted once
        kick(1);
      },
      setLabels: function (on) { namesAll = !!on; placeLabels(); if (hover) showHover(hover); },
      setLinks: function (on) { showLinks = !!on; highlight(); },
      setDark: function (on) {
        dark = !!on;
        nodes.forEach(function (n, i) { if (n.kind !== 'core') circles[i].setAttribute('fill', colour(n.cat, dark)); });
        highlight();
      },
      select: function (id) { pinned = byId[id] || null; highlight(); },
      resize: function () {
        W = svg.clientWidth || W; H = svg.clientHeight || H;
        kick(0.05);
      },
      layoutMs: function () { return settled ? tLayout : null; },
      buildMs: function () { return tBuild; }       // the SVG elements and the label measurement
    };
  }

  window.CBRGraph = {create: create, colour: colour};
})();
