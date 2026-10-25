// Writes the static search index (_site/pagefind/) from the records that
// pipeline/build.py prepares. Pagefind splits the index into small chunks, so a
// search downloads only the pieces it needs, even with tens of thousands of studies.
//
//   node pipeline/search_index.mjs RECORDS.json OUTPUT_DIR
import { readFile } from "node:fs/promises";
import * as pagefind from "pagefind";

const [recordsPath, outputPath] = process.argv.slice(2);
const records = JSON.parse(await readFile(recordsPath, "utf8"));

// One index for every study, whatever its language: Pagefind would otherwise
// make a separate index per language and an English query would miss the rest.
const { index, errors } = await pagefind.createIndex({ forceLanguage: "en" });
if (!index) {
  console.error("pagefind: could not start", errors);
  process.exit(1);
}
let n = 0;
for (const r of records) {
  const { errors: e } = await index.addCustomRecord({
    url: r.url,
    content: r.content,
    language: "en",
    meta: r.meta,
    filters: r.filters,
    sort: r.sort,
  });
  if (e && e.length) {
    console.error("pagefind:", r.url, e);
    continue;
  }
  n++;
}
const { errors: we } = await index.writeFiles({ outputPath });
if (we && we.length) {
  console.error("pagefind: write failed", we);
  process.exit(1);
}
await pagefind.close();
console.error(`pagefind: indexed ${n} studies into ${outputPath}`);
