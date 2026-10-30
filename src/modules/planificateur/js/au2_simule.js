// AU2 simulé : imite la réception de mission d'AU2 (SPECIFICATION.md § 8.2)
// pour essayer le planificateur sans carte (bouton « AU2 simulé ») et pour les
// tests. Il livre ses réponses par petits morceaux (comme une liaison série)
// pour exercer le recollage des trames, stocke la mission, répond aux
// relectures, la valide à MISSION_FIN, et refuse toute nouvelle mission
// quand il est « armé » (§ 4.1). Même interface que CanalSerie.

import {
  DRAPEAU, DecodeurTrames, ELEMENT, EMETTEUR, STATUT, Sequenceur, TYPE, decoderMessage, encoderMessage, encoderTrame,
  crc16,
} from "./protocole.js";

export class AU2Simule {
  constructor({ capacites, taillePaquet = 20, pertes = 0, abimer = null, heartbeatMs = null } = {}) {
    this.capacites = capacites;
    this.taillePaquet = taillePaquet;
    this.pertes = pertes; // probabilité de perdre une trame (0 à 1)
    this.abimer = abimer; // fonction (type, donnees) -> donnees : simule un stockage défaillant
    this.arme = false; // true : le drone est armé ou en vol, toute nouvelle mission est refusée
    this.ecouteurs = [];
    this.decodeur = new DecodeurTrames();
    this.sequenceur = new Sequenceur();
    this.surDeconnexion = () => {};
    this.reinitialiser();
    if (heartbeatMs) this.minuterie = setInterval(() => this.heartbeat(), heartbeatMs);
  }

  reinitialiser() {
    this.debut = null;
    this.stock = new Map(); // "element:index" -> { type, donnees }
    this.missionValidee = false;
  }

  ajouterEcouteur(f) { this.ecouteurs.push(f); }
  get connecte() { return true; }
  async connecter() { return {}; }
  deconnecter() { clearInterval(this.minuterie); }

  heartbeat() {
    let etat = DRAPEAU.DEPART_DEFINI;
    if (this.arme) etat |= DRAPEAU.ARME;
    if (this.missionValidee) etat |= DRAPEAU.MISSION_CHARGEE;
    this.repondre(TYPE.HEARTBEAT, { emetteur: EMETTEUR.AU2, etat, temps_ms: Math.round(performance.now()) });
  }

  texte(gravite, texte) {
    this.repondre(TYPE.TEXTE, { gravite, source: EMETTEUR.AU2, texte: `AU2 (simulé) : ${texte}` });
  }

  /** Côté PC -> AU2 : la trame est recollée comme si elle arrivait par morceaux. */
  async envoyerTrame(octets) {
    await new Promise((r) => setTimeout(r, 1));
    if (this.pertes && Math.random() < this.pertes) return;
    for (let i = 0; i < octets.length; i += this.taillePaquet) {
      for (const t of this.decodeur.pousser(octets.slice(i, i + this.taillePaquet))) this.traiter(t);
    }
  }

  repondre(type, champsOuDonnees) {
    if (this.pertes && Math.random() < this.pertes) return;
    const donnees = champsOuDonnees instanceof Uint8Array ? champsOuDonnees : encoderMessage(type, champsOuDonnees);
    const octets = encoderTrame(type, this.sequenceur.suivant(), donnees);
    const decodeurPc = this.decodeurPc ?? (this.decodeurPc = new DecodeurTrames());
    setTimeout(() => {
      for (let i = 0; i < octets.length; i += this.taillePaquet) {
        for (const t of decodeurPc.pousser(octets.slice(i, i + this.taillePaquet))) for (const f of this.ecouteurs) f(t);
      }
    }, 2);
  }

  ack(id, element, index, statut) {
    this.repondre(TYPE.MISSION_ACK, { id_mission: id, element, index, statut });
  }

  traiter(t) {
    let m;
    try {
      m = decoderMessage(t.type, t.donnees);
    } catch {
      return;
    }
    const cle = (e, i) => `${e}:${i}`;
    const stocker = (e, i) => {
      const donnees = this.abimer ? this.abimer(t.type, t.donnees) : t.donnees;
      this.stock.set(cle(e, i), { type: t.type, donnees });
    };
    switch (t.type) {
      case TYPE.MISSION_DEBUT: {
        const c = this.capacites;
        let statut = STATUT.OK;
        if (this.arme) {
          statut = STATUT.ETAT_INCOMPATIBLE;
          this.texte(2, "mission refusée, drone armé");
        } else if (m.nb_waypoints > c.maxWaypoints || m.nb_zones > c.maxZones ||
          m.nb_sommets_limites > c.maxSommetsLimites) {
          statut = STATUT.CAPACITE_DEPASSEE;
        }
        if (statut === STATUT.OK) {
          this.reinitialiser();
          this.debut = m;
          stocker(ELEMENT.DEBUT, 0);
        }
        this.ack(m.id_mission, ELEMENT.DEBUT, 0, statut);
        break;
      }
      case TYPE.MISSION_LIMITES:
      case TYPE.ZONE_INTERDITE:
      case TYPE.MISSION_WAYPOINT: {
        const element = t.type === TYPE.MISSION_LIMITES ? ELEMENT.LIMITES
          : t.type === TYPE.ZONE_INTERDITE ? ELEMENT.ZONE : ELEMENT.WAYPOINT;
        const index = t.type === TYPE.ZONE_INTERDITE ? m.index_zone : t.type === TYPE.MISSION_WAYPOINT ? m.index : 0;
        if (!this.debut || this.debut.id_mission !== m.id_mission) { this.ack(m.id_mission, element, index, STATUT.ID_INCONNU); break; }
        stocker(element, index);
        this.ack(m.id_mission, element, index, STATUT.OK);
        break;
      }
      case TYPE.MISSION_VERIFICATION: {
        const e = this.stock.get(cle(m.element, m.index));
        if (!this.debut || this.debut.id_mission !== m.id_mission) this.ack(m.id_mission, m.element, m.index, STATUT.ID_INCONNU);
        else if (!e) this.ack(m.id_mission, m.element, m.index, STATUT.INCOMPLETE);
        else this.repondre(e.type, e.donnees);
        break;
      }
      case TYPE.MISSION_FIN: {
        const d = this.debut;
        if (!d || d.id_mission !== m.id_mission) { this.ack(m.id_mission, ELEMENT.FIN, 0, STATUT.ID_INCONNU); break; }
        const attendus = [[ELEMENT.DEBUT, 0], [ELEMENT.LIMITES, 0]];
        for (let i = 0; i < d.nb_zones; i++) attendus.push([ELEMENT.ZONE, i]);
        for (let i = 0; i < d.nb_waypoints; i++) attendus.push([ELEMENT.WAYPOINT, i]);
        if (!attendus.every(([e, i]) => this.stock.has(cle(e, i)))) {
          this.ack(m.id_mission, ELEMENT.FIN, 0, STATUT.INCOMPLETE);
          break;
        }
        let crc = 0xffff;
        for (const [e, i] of attendus) {
          const s = this.stock.get(cle(e, i));
          crc = crc16(s.donnees, 0, s.donnees.length, crc);
        }
        if (crc !== m.crc_mission) { this.ack(m.id_mission, ELEMENT.FIN, 0, STATUT.CRC_INVALIDE); break; }
        this.missionValidee = true;
        this.ack(m.id_mission, ELEMENT.FIN, 0, STATUT.OK);
        this.texte(1, `mission ${m.id_mission} validée (CRC correct), prête à voler`);
        break;
      }
      default:
        break;
    }
  }
}
