// Lance les tests des étapes 4 et 5, sur vos fichiers ou (--corrections) sur les corrections.
// Fonctionne sous Windows comme sous Linux/macOS (pas de variable d'environnement à poser à la main).
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const ici = dirname(fileURLToPath(import.meta.url));
const env = { ...process.env };
if (process.argv.includes("--corrections")) env.TP_CORRECTIONS = "1";
const r = spawnSync(process.execPath, ["--test", "etape04/geometrie.test.mjs", "etape05/calculs.test.mjs"],
  { cwd: ici, env, stdio: "inherit" });
process.exit(r.status ?? 1);
