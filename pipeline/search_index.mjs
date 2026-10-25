// Writes the static search index (_site/pagefind/) from the records that
// pipeline/build.py prepares. Pagefind splits the index into small chunks, so a
// search downloads only the pieces it needs, even with tens of thousands of studies.
//
//   node pipeline/search_index.mjs RECORDS.json OUTPUT_DIR
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
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
// Take the files in memory and write them here: index.writeFiles() can resolve
// before Pagefind's own process has finished writing, and close() then cuts the
// larger files short (they stop at 32 KB), which silently breaks the search.
const { errors: fe, files } = await index.getFiles();
if (fe && fe.length) {
  console.error("pagefind: could not produce the index", fe);
  process.exit(1);
}
let bytes = 0;
for (const f of files) {
  const dest = join(outputPath, f.path);
  await mkdir(dirname(dest), { recursive: true });
  await writeFile(dest, f.content);
  bytes += f.content.length;
}
await pagefind.close();
console.error(`pagefind: wrote ${files.length} files, ${(bytes / 1048576).toFixed(1)} MB`);
console.error(`pagefind: indexed ${n} studies into ${outputPath}`);
