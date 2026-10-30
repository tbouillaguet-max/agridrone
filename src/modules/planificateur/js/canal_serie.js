// Canal série vers AU2 par le câble USB, avec l'API Web Serial de Chrome.
//
// Le port USB de la Mega (AU2) transporte les trames du protocole commun
// (SPECIFICATION.md § 1) : 115 200 bauds, 8N1. Le flux d'octets reçu est
// découpé en trames par le décodeur du § 2.2.
//
// Même interface que AU2Simule (au2_simule.js), utilisée par transfert.js :
//   ajouterEcouteur(f), connecte, connecter(), envoyerTrame(octets),
//   deconnecter(), surDeconnexion.

import { DecodeurTrames } from "./protocole.js";

const attendre = (ms) => new Promise((r) => setTimeout(r, ms));

/** Message d'erreur compréhensible pour une exception Web Serial. */
export function expliquerErreur(e) {
  const t = `${e?.name ?? ""} ${e?.message ?? e}`;
  if (/NotFoundError/.test(t)) return "aucun port choisi (ou recherche annulée)";
  if (/SecurityError/.test(t)) return "Web Serial exige une page en http://localhost (voir lancer.bat)";
  if (/InvalidStateError/.test(t)) return "ce port est déjà ouvert (autre onglet, moniteur série de l'IDE Arduino ?)";
  if (/NetworkError/.test(t)) return "port inaccessible : fermez le moniteur série de l'IDE Arduino, puis réessayez";
  if (/NotSupportedError|serial.*undefined/i.test(t)) return "Web Serial indisponible : utilisez Chrome ou Edge sur PC";
  if (/BreakError|FramingError|BufferOverrunError|ParityError/.test(t)) return "erreur de transmission sur le câble";
  return t.trim();
}

export class CanalSerie {
  constructor({ debitBauds = 115200, attenteDemarrageMs = 2000, journal = () => {} } = {}) {
    this.debitBauds = debitBauds;
    this.attenteDemarrageMs = attenteDemarrageMs;
    this.journal = journal;
    this.decodeur = new DecodeurTrames();
    this.ecouteurs = [];
    this.surDeconnexion = () => {};
    this.fileEcriture = Promise.resolve();
    this.port = null;
    this.lecteur = null;
    this.ouvert = false;
  }

  static disponible() {
    return typeof navigator !== "undefined" && !!navigator.serial;
  }

  ajouterEcouteur(f) { this.ecouteurs.push(f); }

  get connecte() { return this.ouvert; }

  /** Ouvre le sélecteur de Chrome, ouvre le port, attend le redémarrage de la Mega. */
  async connecter() {
    if (!CanalSerie.disponible()) throw new Error("Web Serial indisponible : utilisez Chrome ou Edge sur PC");
    this.port = await navigator.serial.requestPort();
    await this.port.open({ baudRate: this.debitBauds, dataBits: 8, stopBits: 1, parity: "none", bufferSize: 4096 });
    this.ouvert = true;
    navigator.serial.addEventListener?.("disconnect", (ev) => {
      if (ev.target === this.port) this.fermer("câble USB débranché");
    });
    const info = this.port.getInfo?.() ?? {};
    this.journal(`port ouvert (${this.debitBauds} bauds), attente du démarrage d'AU2…`);
    this.decodeur = new DecodeurTrames();
    this.boucleLecture();
    // La Mega redémarre quand le port s'ouvre (DTR) : ses premières trames
    // arrivent après le chargeur d'amorçage.
    await attendre(this.attenteDemarrageMs);
    this.journal("AU2 connecté par le câble USB", "ok");
    return { usbVendorId: info.usbVendorId, usbProductId: info.usbProductId };
  }

  async boucleLecture() {
    while (this.ouvert && this.port?.readable) {
      this.lecteur = this.port.readable.getReader();
      try {
        for (;;) {
          const { value, done } = await this.lecteur.read();
          if (done) break;
          if (value) for (const trame of this.decodeur.pousser(value)) for (const f of this.ecouteurs) f(trame);
        }
      } catch (e) {
        // Erreur passagère (BreakError…) : on reprend la lecture ; sinon on ferme.
        this.journal(`lecture interrompue : ${expliquerErreur(e)}`, "erreur");
        if (!/BreakError|FramingError|BufferOverrunError|ParityError/.test(`${e?.name}`)) {
          this.lecteur.releaseLock();
          await this.fermer("liaison série perdue");
          return;
        }
      } finally {
        try { this.lecteur.releaseLock(); } catch { /* déjà libéré */ }
      }
    }
  }

  /** Envoie une trame complète. Les envois sont mis en file (un seul écrivain à la fois). */
  envoyerTrame(octets) {
    const envoi = this.fileEcriture.then(async () => {
      if (!this.ouvert || !this.port?.writable) throw new Error("AU2 n'est pas connecté");
      const ecrivain = this.port.writable.getWriter();
      try {
        await ecrivain.write(octets);
      } finally {
        ecrivain.releaseLock();
      }
    });
    this.fileEcriture = envoi.catch(() => {});
    return envoi;
  }

  async fermer(raison) {
    if (!this.ouvert) return;
    this.ouvert = false;
    try { await this.lecteur?.cancel(); } catch { /* rien */ }
    try { await this.port?.close(); } catch { /* rien */ }
    this.journal(`AU2 déconnecté (${raison})`, "avertissement");
    this.surDeconnexion(raison);
  }

  deconnecter() { return this.fermer("à la demande"); }
}
