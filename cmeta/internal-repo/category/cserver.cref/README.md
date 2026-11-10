# cserver.cref - the page of one artifact, named by its cRef

```
http://127.0.0.1:8004/cref/<category>::<alias>,<UID>[/<relative path>]
http://127.0.0.1:8004/cref?cref=<cRef>
```

The category's UID may be added (`<category>,<UID>::<alias>,<UID>`), the artifact's UID or the category left out when
the alias is unique, or the `{{{<cRef>}}}/<path>` form of a text pasted as it is: the reference is resolved by
`cserver.browse` (the UID decides when it is given), and the address bar keeps the cRef - it is how artifacts are
referenced, and a reader sees what is referenced.

## What the page shows

1. the title (the `_cmeta` name, else the alias) and the cRef, each with a button that copies it - the cRef also as
   `{{{<cRef>}}}`, the form a text holds (a note, a memory, an AI prompt) -, the category and the repository, the
   tags, then a line;
2. the artifact's **text**: `README.md` (then `_info.md`, `note.md`, `index.md`), or the file its category names in
   `cref_view.text`, with `README.md` and `_info.md` after it when the artifact has them; a relative path after the
   cRef shows that file instead; Markdown is rendered, and inside it `{{{<cRef>}}}/<path>` references and the
   artifact's wikilinks (`_desc.ck.wikilinks`, written by an importer) become links to their pages;
3. folded at the end, for the technical personas only: the commands, `See _cmeta`, `See _desc`, the lists - the
   **connections**, the **AI uses** (whose memory and skills the artifact's AI sessions read), what it **uses** (a
   task's sub-tasks) and what **connects to** it (from the connection index of `cserver.browse`) -, the files (only
   where the file browser is on - the server's own machine, or `browse_files` in the cserver config). A list shows
   each category, then its artifacts under it, each with a button that copies its cRef, and "copy all" (the cRefs with
   `;` between them, what the field of another artifact takes). The browser keeps a list open once it was opened.
   Another persona sees the connections and what connects to it after the text instead.

## Editing from the page

Where this reader may write (`cserver.browse`'s rules: a browser on the server's own machine, `browse_edit` in the
cserver config, or what a host grants a signed-in reader):

- the texts are edited where they are read (`edit` under each; Ctrl+S saves), and a missing `README.md` or `_info.md` is
  made with its `+` button - `cserver.browse`'s save, with its checks and the fingerprint that keeps a file changed
  meanwhile from being overwritten;
- the **connections** and the **AI uses** change in their lists, also when the artifact has none yet: the field adds
  names or cRefs (`;` between several; it offers the AI contexts by their short names and the artifacts whose names
  hold what is typed), `x` removes one after asking on its line. `cserver.browse`'s `link` makes the change with the
  category's own `update` (`--ct`, `-ai`): the full cRef of each artifact, a hand-written `_desc.yaml` keeping its
  text around the list. A connection is added on this side (the other artifact lists it under "connects to it"), and
  removed from both sides where the reader may write - as `--connect=-<name>` does: the graph draws a connection
  declared on either side;
- the `_cmeta` and the `_desc` are edited from their sections, any file from the files.

The page is drawn again after each change, with what the change said.

The graph links of the page (Graph, Focus the graph here) ask for every repository (`repos=*`): a connection into a
repository the server unticks by default (`browse_untick_repos`, an archive) is drawn too.

Links to the browser and to the graph open `cserver.browse` on the same artifact. The rules are the browser's: hidden
repositories and key or secret categories are not shown; a key-looking file is never read.

## Extending the view

`cref_view` in a category's `_cmeta.yaml` (every artifact of the category), or in an artifact's `_desc` (that one):

```yaml
cref_view:
  text: [ck/{ck.latest.date}/note.md, README.md]   # a file or candidates; {ck.<key>} placeholders read the _desc
  title: ck.title                                   # a dotted key of the _desc
  hide: [files, commands]                           # connections, incoming, commands, cmeta, desc, files
```

A host may pass `misc.persona` (a site's audience view): anything but `engineering`, `dev`, `internal` or `all` hides
the technical sections; `misc.cref_url` and `misc.browse_url` tell the page where it and the browser are served
(defaults: `<url_server>cref/` and `<url_server>browse`).

## Dark or light

The page decides its theme before it is drawn: `?dark=1` (or `0`) in its address; else the theme of the page of this
server the reader came from - every page keeps its own in the browser as `cserver.<name>.theme`
(`cserver.browse.theme`, `cserver.projects.theme`, a page of another repository the same way), so a link from a dark
page opens a dark cRef page with nothing passed; else the choice kept by this page (`cserver.cref.theme`); else the
server's (`misc.theme`, `?dark`). What is decided is kept, so the next cRef page opened from this one has it too. The
switch at the top right (&#9680;) turns it and keeps it. In dark mode the page colours the window. Inside the
cPlatform's shell (`misc.ctuning_server`) it follows the shell's theme (`html[data-ctp-theme]`, switched there without
a reload) and shows no switch.
