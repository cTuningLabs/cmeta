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

1. the title (the `_cmeta` name, else the alias), the category and the repository, the cRef with a copy button, the tags;
2. the artifact's **text**: `README.md` (then `_info.md`, `note.md`, `index.md`), or the file its category names in
   `cref_view.text`; a relative path after the cRef shows that file instead; Markdown is rendered, and inside it
   `{{{<cRef>}}}/<path>` references and the artifact's wikilinks (`_desc.ck.wikilinks`, written by an importer) become
   links to their pages;
3. the **connections**, grouped by category, then what **connects to** this artifact (from the connection index of
   `cserver.browse`);
4. folded at the end, for the technical personas only: the commands, `See _cmeta`, `See _desc`, the files (only where
   the file browser is on - the server's own machine, or `browse_files` in the cserver config).

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
