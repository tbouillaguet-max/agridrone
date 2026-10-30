// Archivage des missions envoyées et journal des erreurs sur le disque.
//
// La page ne peut pas écrire seule dans un dossier du PC : elle demande à
// serveur_local.py (qui la sert sur http://localhost) d'écrire à sa place.
//
//   POST /api/missions?id=<idMission>   corps : JSON de la mission
//        -> { ok, chemin, suffixe }     mission_<id>.json, ou mission_<id>_2.json…
//           si l'identifiant est déjà archivé avec un AUTRE contenu
//   GET  /api/missions/libre?depuis=<id> -> { id }  premier identifiant non archivé
//   POST /api/journal                   corps : { niveau, texte, idMission }
//        -> ajoute une ligne à journal_planificateur.txt (même dossier)
//
// Le dossier est choisi au lancement du serveur (par défaut
// data\missions) : c'est l'entrée E3 du pipeline d'analyse.

async function requete(url, options = {}) {
  const r = await fetch(url, { ...options, headers: { "Content-Type": "application/json", ...(options.headers ?? {}) } });
  let corps = null;
  try { corps = await r.json(); } catch { /* pas de JSON */ }
  if (!r.ok) {
    if (r.status === 404 || r.status === 501) {
      throw new Error("serveur d'archivage absent : lancez le planificateur avec lancer.bat (serveur_local.py)");
    }
    throw new Error(corps?.erreur ?? `réponse HTTP ${r.status}`);
  }
  return corps;
}

/** Archive le JSON d'une mission envoyée. Ne lève jamais : renvoie { ok, chemin, suffixe } ou { ok: false, erreur }. */
export async function archiverMission(idMission, texteJson) {
  try {
    const r = await requete(`/api/missions?id=${encodeURIComponent(idMission)}`, { method: "POST", body: texteJson });
    return { ok: true, chemin: r.chemin, suffixe: !!r.suffixe };
  } catch (e) {
    return { ok: false, erreur: e.message };
  }
}

/** Premier identifiant ≥ depuis (en bouclant après 65535) qui n'est pas déjà archivé ; `depuis` si le serveur ne répond pas. */
export async function idMissionLibre(depuis) {
  try {
    const r = await requete(`/api/missions/libre?depuis=${encodeURIComponent(depuis)}`);
    return Number.isInteger(r?.id) && r.id >= 1 && r.id <= 0xffff ? r.id : depuis;
  } catch {
    return depuis;
  }
}

/** Ajoute une ligne au journal du planificateur sur le disque (sans jamais lever). */
export function journaliserSurDisque({ niveau, texte, idMission }) {
  if (typeof fetch === "undefined" || typeof location === "undefined" || !/^https?:$/.test(location.protocol)) return;
  fetch("/api/journal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ niveau, texte, idMission, horodatage: new Date().toISOString() }),
  }).catch(() => { /* serveur absent : le journal reste à l'écran */ });
}
