/* cMeta - a small syntax colouring for the files the pages show (YAML, JSON, Python, Markdown, shell, bat, PowerShell,
   and a generic one for JS/CSS/HTML). No dependency: cmetaHL(text, name, opts) returns HTML with every character
   escaped and the tokens wrapped in <span class="hl-*"> (c comment, s string, k keyword or key, v value or variable,
   n number, h heading, d decorator, p punctuation, t tag); a cRef written as {{{category::alias,UID}}}/path becomes a
   link when opts.cref_url says where the artifact pages are. Shared by cserver.browse (a static file) and cserver.cref
   (inlined from this file). */
(function () {
  'use strict';
  var esc = function (s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); };
  var STR = /"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'/;
  var NUM = /\b\d+(?:\.\d+)?(?:e[+-]?\d+)?\b/i;
  var CREF = /\{\{\{([^{}:]+)::([^{}]+?),([0-9a-fA-F]{16})\}\}\}((?:\/[^\s"'`<>)\]]*)?)/;

  // the rules of a language, in order of priority: the earliest match wins, then the first rule listed
  var LANGS = {
    yaml: [['c', /(?:^|(?<=\s))#.*/], ['s', STR], ['k', /^[ \t]*(?:- )?[\w.\-\/@$ ]+?(?=:(?:\s|$))/m], ['v', /\b(?:true|false|null|yes|no|on|off|True|False|None|Yes|No)\b/], ['n', NUM], ['p', /^[ \t]*-(?=\s)/m]],
    json: [['k', /"(?:\\.|[^"\\])*"(?=\s*:)/], ['s', /"(?:\\.|[^"\\])*"/], ['v', /\b(?:true|false|null)\b/], ['n', NUM]],
    python: [['c', /#.*/], ['s', /"""[\s\S]*?"""|'''[\s\S]*?'''/], ['s', /\b[rbfu]{1,2}(?:"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'/i], ['d', /@\w[\w.]*/],
             ['k', /\b(?:def|class|import|from|return|if|elif|else|for|while|try|except|finally|with|as|lambda|yield|raise|pass|break|continue|and|or|not|in|is|global|nonlocal|assert|del|async|await)\b/],
             ['v', /\b(?:None|True|False|self|cls)\b/], ['n', NUM]],
    shell: [['c', /(?:^|(?<=\s))#.*/], ['s', STR], ['v', /\$\{[^}]*\}|\$\w+|\$\(/], ['k', /\b(?:if|then|else|elif|fi|for|in|do|done|while|case|esac|function|export|local|return|exit|set|cd|echo|sudo)\b/], ['n', NUM]],
    bat: [['c', /^[ \t]*(?:rem\b.*|::.*)/im], ['s', /"[^"\n]*"/], ['v', /%[\w~]+%|%~?\w|!\w+!/], ['k', /\b(?:echo|set|setlocal|endlocal|if|else|not|exist|defined|for|in|do|goto|call|exit|cd|pause|start)\b/i], ['n', NUM]],
    ps1: [['c', /<#[\s\S]*?#>|#.*/], ['s', STR], ['v', /\$env:\w+|\$\{[^}]*\}|\$\w+/i], ['k', /\b(?:function|param|if|else|elseif|foreach|for|while|switch|return|try|catch|finally|throw|[A-Z][a-z]+-[A-Z][A-Za-z]+)\b/], ['n', NUM]],
    markdown: [['c', /^(?:```|~~~).*$/m], ['h', /^#{1,6} .*$/m], ['s', /`[^`\n]+`/], ['k', /\*\*[^*\n]+\*\*/], ['v', /\[[^\]\n]*\]\([^)\n]*\)/], ['p', /^[ \t]*(?:[-*+]|\d+\.)(?= )/m]],
    code: [['c', /\/\/.*|\/\*[\s\S]*?\*\/|<!--[\s\S]*?-->/], ['s', /`(?:\\.|[^`\\])*`/], ['s', STR], ['t', /<\/?[a-zA-Z][^>]*>/],
           ['k', /\b(?:function|var|let|const|return|if|else|for|while|class|new|this|import|export|from|default|switch|case|break|continue|try|catch|finally|throw|typeof|instanceof|await|async)\b/],
           ['v', /\b(?:true|false|null|undefined)\b/], ['n', NUM]]
  };
  var EXT = {yml: 'yaml', yaml: 'yaml', toml: 'yaml', ini: 'yaml', cfg: 'yaml', conf: 'yaml', json: 'json', py: 'python', md: 'markdown', markdown: 'markdown',
             sh: 'shell', bash: 'shell', zsh: 'shell', bat: 'bat', cmd: 'bat', ps1: 'ps1', js: 'code', ts: 'code', css: 'code', html: 'code', htm: 'code', xml: 'code', svg: 'code'};

  function langOf(name) {
    var base = String(name || '').split('/').pop(), m = /\.([A-Za-z0-9]+)$/.exec(base), e = m ? m[1].toLowerCase() : '';
    if (e in EXT) return EXT[e];
    var b = base.toLowerCase();
    if (b === 'dockerfile' || b === 'makefile' || b.indexOf('.env') === 0) return 'shell';
    return '';
  }

  // a cRef token: a link to the artifact (and the file inside it) when the page says where /cref/ is, a span otherwise
  function crefHtml(m, crefUrl) {
    var text = esc(m[0]);
    if (!crefUrl) return '<span class="hl-r">' + text + '</span>';
    var rel = m[4].replace(/[.,;:]+$/, '');
    return '<a class="hl-r" href="' + esc(crefUrl + encodeURI(m[1] + '::' + m[2] + ',' + m[3]) + encodeURI(rel)) + '">' + text + '</a>';
  }

  // every rule scans the whole text once; the tokens are then laid out from the start, overlaps dropped
  function tokenize(text, rules, crefUrl) {
    var found = [];
    rules.forEach(function (r, pri) {
      var re = new RegExp(r[1].source, 'g' + (r[1].multiline ? 'm' : '') + (r[1].ignoreCase ? 'i' : ''));
      var m;
      while ((m = re.exec(text)) !== null) {
        if (!m[0].length) { re.lastIndex++; continue; }
        found.push([m.index, m.index + m[0].length, pri, r[0], r[0] === 'r' ? m : null]);
      }
    });
    found.sort(function (a, b) { return a[0] - b[0] || a[2] - b[2]; });
    var out = '', pos = 0;
    for (var i = 0; i < found.length; i++) {
      var t = found[i];
      if (t[0] < pos) continue;
      out += esc(text.slice(pos, t[0]));
      out += t[4] ? crefHtml(t[4], crefUrl) : '<span class="hl-' + t[3] + '">' + esc(text.slice(t[0], t[1])) + '</span>';
      pos = t[1];
    }
    return out + esc(text.slice(pos));
  }

  window.cmetaHL = function (text, name, opts) {
    text = String(text == null ? '' : text);
    var crefUrl = (opts && opts.cref_url) || '';
    if (text.length > 300000) return esc(text);
    var lang = langOf(name);
    try { return tokenize(text, [['r', CREF]].concat(LANGS[lang] || []), crefUrl); } catch (e) { return esc(text); }
  };
  window.cmetaHL.lang = langOf;
})();
