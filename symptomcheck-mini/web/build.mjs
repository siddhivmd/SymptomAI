// Builds the static site into dist/ for Vercel or Netlify.
// - Writes dist/config.js from the BACKEND_URL environment variable.
// - Copies the latest benchmark results from ../eval/results/.
import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const dist = join(root, "dist");
const resultsSrc = join(root, "..", "eval", "results");

rmSync(dist, { recursive: true, force: true });
mkdirSync(join(dist, "results"), { recursive: true });

for (const file of ["index.html", "styles.css", "app.js"]) {
  cpSync(join(root, file), join(dist, file));
}

const apiUrl = (process.env.BACKEND_URL || "").trim();
if (!apiUrl) {
  console.warn("warning: BACKEND_URL is not set; the deployed site will only work against a local backend.");
}
writeFileSync(
  join(dist, "config.js"),
  `window.SYMPTOMCHECK_CONFIG = ${JSON.stringify({ apiUrl })};\n`,
);

for (const file of ["results.csv", "accuracy_by_arm.png"]) {
  const src = join(resultsSrc, file);
  if (existsSync(src)) cpSync(src, join(dist, "results", file));
  else console.warn(`warning: ${src} not found; the results tab will show a placeholder.`);
}

console.log(`Built dist/ (BACKEND_URL=${apiUrl || "<unset>"})`);
