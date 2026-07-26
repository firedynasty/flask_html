"""
Build a self-contained HTML reader (html_js_ported/index.html) from
chapters.json + clean/<slug>.txt — all data embedded, no Flask, no server.

Same reader UI as app.py's templates (index grouped by section, unit read
view, unit outline view with prev/next + arrow keys), plus mobile viewport
and A-/A+ font controls. Outlines are computed fresh by outliner.py — the
same heuristic engine as 17-CS_Lewis.

Usage:
    python make_portable.py [bookdir]   # writes <bookdir>/html_js_ported/index.html
"""

import json
import os
import sys

import outliner

BASE = os.path.dirname(os.path.abspath(__file__))
BOOK_DIR = BASE
for a in sys.argv[1:]:
    if not a.startswith("--"):
        BOOK_DIR = os.path.join(BASE, a)
CHAPTERS_JSON = os.path.join(BOOK_DIR, "chapters.json")
CLEAN_DIR = os.path.join(BOOK_DIR, "clean")
OUT_DIR = os.path.join(BOOK_DIR, "html_js_ported")
OUT_HTML = os.path.join(OUT_DIR, "index.html")

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root { --ink:#2b2b2b; --dim:#777; --line:#e3e0d8; --accent:#7a5c2e; }
  * { box-sizing:border-box; }
  body { font-family: Georgia, 'Times New Roman', serif; color:var(--ink);
         margin:0; background:#faf8f3; }

  /* -- Index -- */
  #view-index { display:block; }
  header { padding:18px 28px; border-bottom:1px solid var(--line);
           display:flex; align-items:baseline; gap:18px; flex-wrap:wrap; }
  header h1 { font-size:20px; margin:0; }
  header .sub { color:var(--dim); font-size:13px; }
  .idx-main { max-width:860px; margin:0 auto; padding:20px 28px 60px; }
  h2 { font-size:16px; color:var(--accent); margin:26px 0 6px;
       border-bottom:1px solid var(--line); padding-bottom:4px; }
  ul.units { list-style:none; margin:0; padding:0; }
  ul.units li { margin:3px 0; line-height:1.5; display:flex; gap:10px;
                align-items:baseline; }
  ul.units .ttl { color:var(--ink); flex:1; cursor:pointer;
                  padding:3px 6px; border-radius:6px; }
  ul.units .ttl:hover { color:var(--accent); background:#f1ede2; }
  .words { color:var(--dim); font-size:12px; font-family:monospace;
           white-space:nowrap; }
  a.raw { color:var(--dim); font-size:12px; text-decoration:none;
          cursor:pointer; }
  a.raw:hover { color:var(--accent); text-decoration:underline; }

  /* -- Unit + outline -- */
  #view-unit, #view-outline { display:none; }
  nav, footer { padding:12px 28px; display:flex; gap:16px;
                align-items:center; font-size:14px; background:#faf8f3; }
  nav { border-bottom:1px solid var(--line); position:sticky; top:0;
        z-index:10; }
  footer { border-top:1px solid var(--line); margin-top:48px; }
  nav button, footer button { color:var(--accent); background:none;
                              border:none; font:inherit; padding:0;
                              cursor:pointer; white-space:nowrap; }
  nav button:hover, footer button:hover { text-decoration:underline; }
  nav button:disabled, footer button:disabled { color:var(--line);
                                                cursor:default;
                                                text-decoration:none; }
  .mid { margin:0 auto; text-align:center; color:var(--dim); font-size:12px;
         overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
         min-width:0; }
  .mid h1 { font-size:17px; margin:0; color:var(--ink); overflow:hidden;
            text-overflow:ellipsis; white-space:nowrap; }
  .u-main { max-width:760px; margin:0 auto; padding:18px 128px 80px; }
  .u-main h1 { font-size:19px; margin:6px 0 2px; }
  .meta { color:var(--dim); font-size:12px; font-family:monospace;
          margin-bottom:22px; }
  .meta a { color:inherit; cursor:pointer; }
  .meta a:hover { color:var(--accent); }
  .u-main p { font-size:1.03em; line-height:1.65; margin:0 0 14px;
              white-space:pre-line; overflow-wrap:anywhere; }

  .stats { padding:8px 28px; border-bottom:1px solid var(--line);
           font-family:monospace; font-size:12px; color:var(--dim);
           display:flex; gap:16px; flex-wrap:wrap; }
  .stats b { color:var(--ink); }
  .o-main { max-width:900px; margin:0 auto; padding:18px 128px 80px; }
  ul.tree, ul.tree ul { list-style:none; margin:0; padding-left:26px; }
  ul.tree { padding-left:0; }
  ul.tree li { position:relative; margin:4px 0; line-height:1.5; }
  ul.tree li::before { content:""; position:absolute; left:-16px; top:.72em;
                       width:5px; height:5px; border-radius:50%;
                       background:#b9b2a2; }
  ul.tree li.has-kids > .caret { cursor:pointer; position:absolute;
                                 left:-27px; top:.35em; font-size:10px;
                                 color:#a39b88; user-select:none;
                                 transition:transform .12s; }
  ul.tree li.collapsed > .caret { transform:rotate(-90deg); }
  ul.tree li.collapsed > ul { display:none; }
  .tag { font-family:monospace; font-size:11px; padding:1px 6px;
         border-radius:9px; margin-left:6px; white-space:nowrap; }
  .t-evidence      { background:#e2efe0; color:#3c7a3c; }
  .t-definition    { background:#ece2f0; color:#6d4a8a; }
  .t-qualification { background:#f7e8d4; color:#a05a16; }
  .t-example       { background:#dcefee; color:#2c7a76; }
  .t-analogy       { background:#ddeaf5; color:#2e6da4; }
  .t-concession    { background:#f5dddd; color:#a03a3a; }
  .t-consequence   { background:#dfe3f5; color:#3a4aa0; }
  .t-contrast      { background:#fbe9d5; color:#b3641a; }
  .t-restatement   { background:#eceae4; color:#6b675c; }
  .keys { color:var(--dim); font-size:11px; margin-left:auto; }

  .fontctl { display:flex; align-items:center; gap:5px; }
  header .fontctl { margin-left:auto; }
  .fontctl button { width:28px; height:28px; border:1px solid var(--line);
                    border-radius:6px; background:#fff; color:var(--accent);
                    font-size:14px; line-height:1; cursor:pointer; padding:0; }
  .fontctl button:hover { background:#f1ede2; text-decoration:none; }

  @media (max-width:700px) {
    header, nav, footer { padding-left:14px; padding-right:14px; gap:10px; }
    nav { flex-wrap:wrap; }
    .idx-main { padding:14px 14px 48px; }
    .u-main { padding:12px 14px 40px; }
    .o-main { padding:12px 14px 60px; }
    .stats { padding-left:14px; padding-right:14px; gap:10px; }
    ul.tree, ul.tree ul { padding-left:18px; }
    ul.tree li::before { left:-12px; }
    ul.tree li.has-kids > .caret { left:-19px; }
    .keys { display:none; }
  }
</style>
</head>
<body>

<div id="view-index">
  <header>
    <h1 id="idx-title"></h1>
    <span class="sub" id="idx-sub"></span>
    <span class="fontctl"><button class="font-dec" title="Smaller text">A\u2212</button><button class="font-inc" title="Larger text">A+</button></span>
  </header>
  <div class="idx-main" id="idx-body"></div>
</div>

<div id="view-unit">
  <nav>
    <button id="u-index">\u2190 index</button>
    <button id="u-prev">\u2190 prev</button>
    <div class="mid" id="u-group"></div>
    <button id="u-outline">outline</button>
    <button id="u-next">next \u2192</button>
    <span class="keys">\u2190 \u2192 navigate</span>
    <span class="fontctl"><button class="font-dec" title="Smaller text">A\u2212</button><button class="font-inc" title="Larger text">A+</button></span>
  </nav>
  <main class="u-main">
    <h1 id="u-title"></h1>
    <div class="meta" id="u-meta"></div>
    <div id="u-body"></div>
  </main>
  <footer>
    <button id="u-index2">\u2190 index</button>
    <button id="u-prev2">\u2190 prev</button>
    <div class="mid" id="u-footer-title"></div>
    <button id="u-outline2">outline</button>
    <button id="u-next2">next \u2192</button>
  </footer>
</div>

<div id="view-outline">
  <nav>
    <button id="o-index">\u2190 index</button>
    <button id="o-prev">\u2190 prev</button>
    <div class="mid"><h1 id="o-title"></h1><div id="o-sub"></div></div>
    <button id="o-read">read</button>
    <button id="o-next">next \u2192</button>
    <span class="keys">\u2190/\u2192 unit \u00b7 x collapse all</span>
    <span class="fontctl"><button class="font-dec" title="Smaller text">A\u2212</button><button class="font-inc" title="Larger text">A+</button></span>
  </nav>
  <div class="stats" id="o-stats"></div>
  <main class="o-main">
    <ul class="tree" id="o-tree"></ul>
  </main>
  <footer>
    <button id="o-index2">\u2190 index</button>
    <button id="o-prev2">\u2190 prev</button>
    <button id="o-top">home</button>
    <div class="mid" id="o-footer-title"></div>
    <button id="o-read2">read</button>
    <button id="o-next2">next \u2192</button>
  </footer>
</div>

<script>
// -- Embedded data -----------------------------------------------------------
var BOOK = __BOOK_JSON__;

var BY_SLUG = {};
BOOK.units.forEach(function(u, i) { u.i = i; BY_SLUG[u.slug] = u; });
var currentSlug = null;

function show(id) {
  ['view-index', 'view-unit', 'view-outline'].forEach(function(v) {
    document.getElementById(v).style.display = (v === id) ? 'block' : 'none';
  });
}
function visible() {
  if (document.getElementById('view-outline').style.display === 'block')
    return 'view-outline';
  if (document.getElementById('view-unit').style.display === 'block')
    return 'view-unit';
  return 'view-index';
}

function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

function downloadTxt(slug) {
  var u = BY_SLUG[slug];
  var blob = new Blob([u.title + '\\n\\n' + u.body + '\\n'],
                      {type: 'text/plain;charset=utf-8'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = slug + '.txt';
  a.click();
  URL.revokeObjectURL(a.href);
}

// -- Index view --------------------------------------------------------------
function renderIndex() {
  document.getElementById('idx-title').textContent =
    BOOK.book_title || 'EPUB reader';
  var total = BOOK.units.reduce(function(s, u) { return s + u.words; }, 0);
  document.getElementById('idx-sub').textContent =
    (BOOK.book_author ? BOOK.book_author + ' \u00b7 ' : '') +
    BOOK.units.length + ' units \u00b7 ' + total + ' words';

  var body = document.getElementById('idx-body');
  body.innerHTML = '';
  var groups = [], seen = {};
  BOOK.units.forEach(function(u) {
    if (!seen[u.group]) { seen[u.group] = []; groups.push([u.group, seen[u.group]]); }
    seen[u.group].push(u);
  });
  groups.forEach(function(pair) {
    body.appendChild(el('h2', null, pair[0]));
    var ul = el('ul', 'units');
    pair[1].forEach(function(u) {
      var li = el('li');
      var ttl = el('span', 'ttl', u.title);
      ttl.addEventListener('click', function() { openOutline(u.slug); });
      li.appendChild(ttl);
      li.appendChild(el('span', 'words', u.words + 'w'));
      var rd = el('a', 'raw', 'read');
      rd.addEventListener('click', function() { openUnit(u.slug); });
      li.appendChild(rd);
      var raw = el('a', 'raw', 'txt');
      raw.addEventListener('click', function() { downloadTxt(u.slug); });
      li.appendChild(raw);
      ul.appendChild(li);
    });
    body.appendChild(ul);
  });
  show('view-index');
  window.scrollTo(0, 0);
}

// -- Unit (read) view --------------------------------------------------------
function wireNav(prefix, u) {
  var n = BOOK.units.length;
  var prev = u.i > 0 ? BOOK.units[u.i - 1] : null;
  var next = u.i + 1 < n ? BOOK.units[u.i + 1] : null;
  var pv = document.getElementById(prefix + '-prev');
  var nx = document.getElementById(prefix + '-next');
  var pv2 = document.getElementById(prefix + '-prev2');
  var nx2 = document.getElementById(prefix + '-next2');
  pv.disabled = pv2.disabled = !prev;
  nx.disabled = nx2.disabled = !next;
  return {prev: prev, next: next};
}

function openUnit(slug) {
  var u = BY_SLUG[slug];
  if (!u) return;
  currentSlug = slug;
  var nb = wireNav('u', u);
  document.getElementById('u-group').textContent = u.group;
  document.getElementById('u-footer-title').textContent = BOOK.book_title || '';
  document.getElementById('u-title').textContent = u.title;
  var meta = document.getElementById('u-meta');
  meta.innerHTML = '';
  meta.appendChild(document.createTextNode(
    (u.i + 1) + ' of ' + BOOK.units.length + ' \u00b7 ' + u.words + ' words \u00b7 '));
  var raw = el('a', null, 'raw txt');
  raw.addEventListener('click', function() { downloadTxt(slug); });
  meta.appendChild(raw);

  var body = document.getElementById('u-body');
  body.innerHTML = '';
  u.body.split('\\n\\n').forEach(function(p) {
    if (p.trim()) body.appendChild(el('p', null, p));
  });

  var go = openUnit;  // read view's prev/next stays in read view
  wirePrevNext('u', nb, go);
  show('view-unit');
  window.scrollTo(0, 0);
}

function wirePrevNext(prefix, nb, go) {
  var pv = document.getElementById(prefix + '-prev');
  var nx = document.getElementById(prefix + '-next');
  var pv2 = document.getElementById(prefix + '-prev2');
  var nx2 = document.getElementById(prefix + '-next2');
  pv.onclick = pv2.onclick = nb.prev ? function() { go(nb.prev.slug); } : null;
  nx.onclick = nx2.onclick = nb.next ? function() { go(nb.next.slug); } : null;
}

// -- Outline view ------------------------------------------------------------
function parseMd(text) {
  var lines = text.split('\\n');
  var roots = [];
  var stack = [];
  var TAG_SUFFIX = /\\s+\\[([a-z][a-z\\-]*)\\]$/;
  var BULLET_RE  = /^( *)- (.+)$/;
  lines.forEach(function(line) {
    if (!line.trim() || line.charAt(0) === '#') return;
    var m = BULLET_RE.exec(line);
    if (!m) return;
    var depth = m[1].length / 2;
    var rest  = m[2];
    var tag   = null;
    var tm = TAG_SUFFIX.exec(rest);
    if (tm) { tag = tm[1]; rest = rest.slice(0, -tm[0].length); }
    var node  = { text: rest.trim(), tag: tag, children: [] };
    while (stack.length > depth) stack.pop();
    if (stack.length === 0) { roots.push(node); }
    else { stack[stack.length - 1].children.push(node); }
    stack.push(node);
  });
  return roots;
}

function renderNode(node) {
  var hasKids = node.children && node.children.length > 0;
  var li = document.createElement('li');
  if (hasKids) li.className = 'has-kids';
  if (hasKids) {
    var caret = document.createElement('span');
    caret.className = 'caret';
    caret.textContent = '\u25bc';
    caret.addEventListener('click', function() { li.classList.toggle('collapsed'); });
    li.appendChild(caret);
  }
  if (node.tag) {
    li.appendChild(document.createTextNode(node.text));
    var badge = document.createElement('span');
    badge.className = 'tag t-' + node.tag;
    badge.textContent = '[' + node.tag + ']';
    li.appendChild(badge);
  } else {
    var span = document.createElement('span');
    span.textContent = node.text;
    li.appendChild(span);
  }
  if (hasKids) {
    var ul = document.createElement('ul');
    node.children.forEach(function(c) { ul.appendChild(renderNode(c)); });
    li.appendChild(ul);
  }
  return li;
}

function openOutline(slug) {
  var u = BY_SLUG[slug];
  if (!u) return;
  currentSlug = slug;
  var nb = wireNav('o', u);
  wirePrevNext('o', nb, openOutline);
  document.getElementById('o-title').textContent = u.title;
  document.getElementById('o-sub').textContent = u.group;
  document.getElementById('o-footer-title').textContent = u.title;

  var st = u.stats;
  var stats = document.getElementById('o-stats');
  stats.innerHTML = '';
  function stat(label, val) {
    var s = el('span');
    s.appendChild(document.createTextNode(label + ' '));
    s.appendChild(el('b', null, String(val)));
    stats.appendChild(s);
  }
  stat('coverage', st.coverage + '%');
  stat('insertions', st.n_inserted);
  stat('nodes', st.nodes);
  stat('max depth', st.max_depth);
  stat('unplaced', st.unplaced);
  Object.keys(st.tags).sort().forEach(function(k) { stat(k, st.tags[k]); });

  var tree = document.getElementById('o-tree');
  tree.innerHTML = '';
  parseMd(u.outline).forEach(function(r) { tree.appendChild(renderNode(r)); });

  show('view-outline');
  window.scrollTo(0, 0);
}

// -- Font size control -------------------------------------------------------
var FS = parseInt(localStorage.getItem('gb-fs') || '16', 10);
var fsStyle = document.createElement('style');
document.head.appendChild(fsStyle);
function applyFS() {
  FS = Math.min(24, Math.max(12, FS));
  fsStyle.textContent = 'body{font-size:' + FS + 'px}';
  try { localStorage.setItem('gb-fs', String(FS)); } catch (e) {}
}
document.querySelectorAll('.font-dec').forEach(function(b) {
  b.addEventListener('click', function() { FS -= 2; applyFS(); });
});
document.querySelectorAll('.font-inc').forEach(function(b) {
  b.addEventListener('click', function() { FS += 2; applyFS(); });
});
applyFS();

// -- Wire up -----------------------------------------------------------------
document.getElementById('u-index').addEventListener('click', renderIndex);
document.getElementById('u-index2').addEventListener('click', renderIndex);
document.getElementById('o-index').addEventListener('click', renderIndex);
document.getElementById('o-index2').addEventListener('click', renderIndex);
document.getElementById('o-top').addEventListener('click', function() {
  window.scrollTo({top: 0, behavior: 'smooth'});
});
function cur() { return BY_SLUG[currentSlug]; }
document.getElementById('u-outline').addEventListener('click', function() { openOutline(currentSlug); });
document.getElementById('u-outline2').addEventListener('click', function() { openOutline(currentSlug); });
document.getElementById('o-read').addEventListener('click', function() { openUnit(currentSlug); });
document.getElementById('o-read2').addEventListener('click', function() { openUnit(currentSlug); });

document.addEventListener('keydown', function(e) {
  var v = visible();
  if (v === 'view-index') return;
  var u = cur();
  if (!u) return;
  var go = v === 'view-outline' ? openOutline : openUnit;
  if (e.key === 'ArrowLeft' && u.i > 0)
    go(BOOK.units[u.i - 1].slug);
  else if (e.key === 'ArrowRight' && u.i + 1 < BOOK.units.length)
    go(BOOK.units[u.i + 1].slug);
  else if (e.key === 'x' && v === 'view-outline') {
    var anyOpen = document.querySelectorAll('li.has-kids:not(.collapsed)').length > 0;
    document.querySelectorAll('li.has-kids').forEach(function(li) {
      li.classList.toggle('collapsed', anyOpen);
    });
  }
});

renderIndex();
</script>
</body>
</html>
"""


def build():
    with open(CHAPTERS_JSON, encoding="utf-8") as f:
        data = json.load(f)

    units = []
    for u in data["units"]:
        with open(os.path.join(CLEAN_DIR, u["slug"] + ".txt"),
                  encoding="utf-8") as f:
            text = f.read()
        parts = text.split("\n\n", 1)
        body = parts[1].strip() if len(parts) > 1 else ""

        paras = [p for p in body.split("\n\n") if p.strip()]
        roots = outliner.outline_chapter(paras)
        md = outliner.render_markdown(u["title"], roots)
        coverage, inserted, _ = outliner.verify_chapter(md, body)
        n_nodes, maxd, tags, n_unplaced = outliner.chapter_stats(roots)

        units.append({"slug": u["slug"], "title": u["title"],
                      "group": u["group"], "words": u["words"],
                      "body": body, "outline": md,
                      "stats": {"coverage": round(coverage * 100, 2),
                                "n_inserted": sum(inserted.values()),
                                "nodes": n_nodes, "max_depth": maxd,
                                "unplaced": n_unplaced, "tags": tags}})

    book = {"book_title": data.get("book_title"),
            "book_author": data.get("book_author"),
            "units": units}
    book_json = json.dumps(book, ensure_ascii=False).replace("</", "<\\/")

    html = TEMPLATE.replace("__BOOK_JSON__", book_json)
    title = (data.get("book_title") or "EPUB reader").replace("&", "&amp;")\
            .replace("<", "&lt;")
    html = html.replace("__TITLE__", title)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    size_kb = os.path.getsize(OUT_HTML) // 1024
    print(f"wrote {OUT_HTML} ({len(units)} units, {size_kb} KB)")


if __name__ == "__main__":
    build()
