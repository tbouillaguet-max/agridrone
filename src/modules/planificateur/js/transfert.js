// Transfert fiable d'une mission vers AU2 (SPECIFICATION.md § 8.2) :
//   1. chaque élément est envoyé puis acquitté (MISSION_ACK), réémis si besoin ;
//   2. relecture : chaque élément est redemandé (MISSION_VERIFICATION) et
//      comparé octet par octet avec ce qui a été envoyé ;
//   3. MISSION_FIN avec le CRC : AU2 ne valide la mission qu'ici.
//
// Le « canal » est n'importe quel objet qui sait envoyer une trame et qui
// appelle ses écouteurs à chaque trame reçue : câble USB (canal_serie.js),
// AU2 simulé (au2_simule.js) ou, dans les tests, le banc AU2 en TCP.

import {
  ELEMENT, NOMS_ELEMENTS, NOMS_STATUTS, STATUT, Sequenceur, TYPE, decoderMessage, egaux, encoderTrame,
  encoderMessage, referenceElement,
} from "./protocole.js";

export class TransfertMission {
  constructor(canal, { delaiReponseMs = 2000, essais = 5, essaisRelecture = 2, journal = () => {} } = {}) {
    this.canal = canal;
    this.delaiReponseMs = delaiReponseMs;
    this.essais = essais;
    this.essaisRelecture = essaisRelecture;
    this.journal = journal;
    this.sequenceur = new Sequenceur(Math.floor(Math.random() * 0xffff));
    this.attente = null; // { correspond(trame, message) -> code|null, resoudre }
    canal.ajouterEcouteur((trame) => this.recevoir(trame));
  }

  recevoir(trame) {
    if (!this.attente) return;
    let message;
    try {
      message = decoderMessage(trame.type, trame.donnees);
    } catch {
      return;
    }
    const code = this.attente.correspond(trame, message);
    if (code !== null && code !== undefined) {
      const { resoudre } = this.attente;
      this.attente = null;
      resoudre(code);
    }
  }

  /** Envoie une trame et attend une réponse qui « correspond », avec réémissions. */
  async echanger(octets, correspond) {
    for (let essai = 0; essai < this.essais; essai++) {
      const reponse = new Promise((resoudre) => { this.attente = { correspond, resoudre }; });
      await this.canal.envoyerTrame(octets);
      let minuterie;
      const delai = new Promise((resoudre) => { minuterie = setTimeout(() => resoudre(null), this.delaiReponseMs); });
      const code = await Promise.race([reponse, delai]);
      clearTimeout(minuterie);
      if (code !== null) return code;
      this.attente = null;
      this.journal(`pas de réponse, nouvel essai (${essai + 2}/${this.essais})`, "avertissement");
    }
    return STATUT.PAS_DE_REPONSE;
  }

  async envoyerElement(e, id) {
    const ref = referenceElement(e.type, e.champs);
    const seq = this.sequenceur.suivant();
    const octets = encoderTrame(e.type, seq, e.donnees);
    return this.echanger(octets, (t, m) => {
      if (t.type === TYPE.MISSION_ACK && m.id_mission === id && m.element === ref.element && m.index === ref.index) {
        return m.statut;
      }
      if (t.type === TYPE.NACK && m.type_refuse === e.type && m.sequence_refusee === seq) return STATUT.NACK_RECU;
      return null;
    });
  }

  async relireElement(e, id) {
    const ref = referenceElement(e.type, e.champs);
    const seq = this.sequenceur.suivant();
    const octets = encoderTrame(TYPE.MISSION_VERIFICATION, seq,
      encoderMessage(TYPE.MISSION_VERIFICATION, { id_mission: id, element: ref.element, index: ref.index }));
    return this.echanger(octets, (t, m) => {
      if (t.type === TYPE.MISSION_ACK && m.id_mission === id && m.element === ref.element &&
        m.index === ref.index && m.statut !== STATUT.OK) return m.statut;
      if (t.type === e.type && m.id_mission === id) {
        const r = referenceElement(t.type, m);
        if (r && r.index === ref.index) return egaux(t.donnees, e.donnees) ? STATUT.OK : STATUT.RELECTURE_DIFFERENTE;
      }
      if (t.type === TYPE.NACK && m.type_refuse === TYPE.MISSION_VERIFICATION && m.sequence_refusee === seq) {
        return STATUT.NACK_RECU;
      }
      return null;
    });
  }

  /**
   * @param elements  liste ordonnée { type, champs, donnees } (mission.js)
   * @param progression(phase, index, total)  phase : "envoi" | "relecture" | "fin"
   * @returns {Promise<{succes, phase, element, index, code, message}>}
   */
  async transferer(elements, idMission, crc, progression = () => {}) {
    const total = elements.length;
    const echec = (phase, e, code) => {
      const ref = referenceElement(e.type, e.champs);
      const message = `échec (${phase}, ${NOMS_ELEMENTS[ref.element]} ${ref.index}) : ${NOMS_STATUTS[code] ?? code}`;
      this.journal(message, "erreur");
      return { succes: false, phase, element: ref.element, index: ref.index, code, message };
    };

    this.journal(`envoi de ${total} éléments (mission ${idMission})`);
    for (let i = 0; i < total; i++) {
      progression("envoi", i, total);
      const code = await this.envoyerElement(elements[i], idMission);
      if (code !== STATUT.OK) return echec("envoi", elements[i], code);
    }

    this.journal("relecture complète");
    for (let i = 0; i < total; i++) {
      progression("relecture", i, total);
      let code = await this.relireElement(elements[i], idMission);
      for (let essai = 0; code === STATUT.RELECTURE_DIFFERENTE && essai < this.essaisRelecture; essai++) {
        this.journal(`élément ${i} relu différent : renvoi`, "avertissement");
        const renvoi = await this.envoyerElement(elements[i], idMission);
        if (renvoi !== STATUT.OK) return echec("relecture", elements[i], renvoi);
        code = await this.relireElement(elements[i], idMission);
      }
      if (code !== STATUT.OK) return echec("relecture", elements[i], code);
    }

    progression("fin", total, total);
    const seq = this.sequenceur.suivant();
    const fin = encoderTrame(TYPE.MISSION_FIN, seq, encoderMessage(TYPE.MISSION_FIN, { id_mission: idMission, crc_mission: crc }));
    const code = await this.echanger(fin, (t, m) => {
      if (t.type === TYPE.MISSION_ACK && m.id_mission === idMission && m.element === ELEMENT.FIN) return m.statut;
      if (t.type === TYPE.NACK && m.type_refuse === TYPE.MISSION_FIN && m.sequence_refusee === seq) return STATUT.NACK_RECU;
      return null;
    });
    if (code !== STATUT.OK) {
      const message = `fin refusée : ${NOMS_STATUTS[code] ?? code}`;
      this.journal(message, "erreur");
      return { succes: false, phase: "fin", element: ELEMENT.FIN, index: 0, code, message };
    }
    this.journal("mission reçue, relue et validée par AU2", "ok");
    return { succes: true, phase: "fin", element: ELEMENT.FIN, index: 0, code: STATUT.OK, message: "mission transférée" };
  }
}
