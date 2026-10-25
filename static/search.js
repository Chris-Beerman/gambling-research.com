// Search page: queries the static Pagefind index in /pagefind/ and renders the
// results in the same form as the lists elsewhere on the site. State lives in
// the address bar (?q=...&topic=...), so a search can be bookmarked or shared.
const form = document.getElementById("search");
const input = document.getElementById("sq");
const sortSel = document.getElementById("ssort");
const list = document.getElementById("sresults");
const status = document.getElementById("sstatus");
const more = document.getElementById("smore");
const selects = Array.from(form.querySelectorAll("select[data-filter]"));
const oa = form.querySelector('input[data-filter="access"]');
const PAGE = 20;
let pagefind = null;
let results = [];
let shown = 0;
let seq = 0;

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

function render(item) {
  const m = item.meta || {};
  const li = el("li", "entry");
  const year = (m.published || "").slice(-4);
  li.appendChild(el("span", "entry-date", year));
  const body = el("div", "entry-body");
  const h = el("h3", "entry-title");
  const a = el("a", null, m.title || item.url);
  a.href = item.url;
  a.rel = "noopener";
  h.appendChild(a);
  body.appendChild(h);
  let meta = (m.journal || "") + (m.published ? ", " + m.published : "") + ".";
  if (m.authors) meta += " " + m.authors + ".";
  const mp = el("p", "entry-meta", meta);
  if (m.setting) mp.appendChild(el("span", "setting", " Setting: " + m.setting + "."));
  if (m.language) mp.appendChild(document.createTextNode(" In " + m.language + "."));
  if (m.retracted) {
    mp.appendChild(document.createTextNode(" "));
    mp.appendChild(el("strong", null, "Retracted."));
  }
  body.appendChild(mp);
  if (m.summary) body.appendChild(el("p", "entry-summary", m.summary));
  const tags = el("p", "entry-tags");
  if (m.oa) {
    const t = el("a", "tag tag-oa", "free full text");
    t.href = m.oa;
    t.rel = "noopener";
    tags.appendChild(t);
  }
  (m.topics || "").split("|").filter(Boolean).forEach((pair) => {
    const [slug, label] = pair.split("~");
    const t = el("a", "tag", label || slug);
    t.href = "/research/topics/" + slug + "/";
    tags.appendChild(t);
  });
  (m.designs || "").split("|").filter(Boolean).forEach((d) => tags.appendChild(el("span", "tag tag-design", d)));
  if (tags.childNodes.length) body.appendChild(tags);
  li.appendChild(body);
  return li;
}

function currentFilters() {
  const f = {};
  selects.forEach((s) => { if (s.value) f[s.dataset.filter] = s.value; });
  if (oa.checked) f.access = oa.dataset.value;
  return f;
}

function syncUrl() {
  const p = new URLSearchParams();
  if (input.value.trim()) p.set("q", input.value.trim());
  selects.forEach((s) => { if (s.value) p.set(s.name, s.value); });
  if (oa.checked) p.set("oa", "1");
  if (sortSel.value) p.set("sort", sortSel.value);
  const qs = p.toString();
  history.replaceState(null, "", qs ? "?" + qs : location.pathname);
}

async function showMore() {
  const batch = results.slice(shown, shown + PAGE);
  const mine = seq;
  const data = await Promise.all(batch.map((r) => r.data()));
  if (mine !== seq) return;
  data.forEach((d) => list.appendChild(render(d)));
  shown += batch.length;
  more.classList.toggle("is-hidden", shown >= results.length);
}

async function run() {
  syncUrl();
  const q = input.value.trim();
  const filters = currentFilters();
  if (!q && !Object.keys(filters).length) {
    seq++;
    results = [];
    list.replaceChildren();
    more.classList.add("is-hidden");
    status.textContent = "Type a word or name, or choose a filter.";
    return;
  }
  const opts = { filters };
  if (sortSel.value === "new") opts.sort = { published: "desc" };
  if (sortSel.value === "old") opts.sort = { published: "asc" };
  const mine = ++seq;
  status.textContent = "Searching…";
  const res = await pagefind.debouncedSearch(q || null, opts, 200);
  if (res === null || mine !== seq) return;
  results = res.results;
  shown = 0;
  list.replaceChildren();
  const n = results.length;
  status.textContent = n ? `${n.toLocaleString()} ${n === 1 ? "study" : "studies"}` + (q ? ` match “${q}”` : "") : "Nothing matches. Try fewer words, or fewer filters.";
  if (n) await showMore();
  else more.classList.add("is-hidden");
}

async function fillFilters() {
  const all = await pagefind.filters();
  selects.forEach((s) => {
    const counts = all[s.dataset.filter] || {};
    let names = Object.keys(counts);
    if (s.dataset.filter === "year") names.sort((a, b) => b.localeCompare(a));
    else names.sort((a, b) => counts[b] - counts[a] || a.localeCompare(b));
    names.forEach((name) => {
      const o = el("option", null, `${name} (${counts[name].toLocaleString()})`);
      o.value = name;
      s.appendChild(o);
    });
    if (!names.length) s.closest("label").classList.add("is-hidden");
  });
}

async function start() {
  try {
    pagefind = await import("/pagefind/pagefind.js");
    await pagefind.options({ excerptLength: 0 });
    pagefind.init();
  } catch (e) {
    status.textContent = "Search could not load. The archive lists every study by month.";
    return;
  }
  await fillFilters();
  const p = new URLSearchParams(location.search);
  input.value = p.get("q") || "";
  selects.forEach((s) => { if (p.get(s.name)) s.value = p.get(s.name); });
  oa.checked = p.get("oa") === "1";
  sortSel.value = p.get("sort") || "";
  form.addEventListener("submit", (e) => { e.preventDefault(); run(); });
  input.addEventListener("input", run);
  selects.concat([sortSel, oa]).forEach((x) => x.addEventListener("change", run));
  more.addEventListener("click", showMore);
  run();
}

start();
