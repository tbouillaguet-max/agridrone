# Essais intégrés avec le vrai drone

Ce document organise la **progression** des essais, du banc au vol complet.
On ne passe à l'étape suivante que si tous les critères de l'étape courante
sont remplis. Le programme de vol d'AU1 et d'AU2 est dans un autre dépôt :
ici, on vérifie que la chaîne mission → vol → journaux fonctionne et que
chaque carte respecte la [spécification](../src/modules/protocole/SPECIFICATION.md).

> **Réglementation (France).** L'exploitant est responsable de son vol.
> Avant tout vol extérieur : enregistrement de l'exploitant et du drone sur
> AlphaTango, formation exigée par la catégorie de vol, vol à vue, hauteur
> maximale de 120 m, respect des zones réglementées (carte « Restrictions UAS »
> du Géoportail), accord du propriétaire du terrain, et ici **l'autorisation
> de la préfecture**. Vérifier les règles en vigueur sur le site du ministère
> chargé des transports : elles évoluent.

## 1. Progression

| Étape | Montage | Objectif | Critères pour passer à la suite |
|---|---|---|---|
| **0. Banc, hélices démontées** | drone complet sur l'établi, AU1 + AU2, carte SD | toute la chaîne au sol | mission chargée et relue ; heartbeats AU1 ↔ AU2 ; pannes injectées détectées et **écrites dans la boîte noire** (§ 3) ; arrêt d'urgence vérifié |
| **1. Moteurs, hélices démontées** | idem, moteurs à mi-gaz | parasites électriques | aucune ligne `ERREUR_LIAISON` pendant 5 min ; aucune perte AU1 ↔ AU2 |
| **2. Stationnaire, 2 à 3 m** | terrain dégagé, câble USB retiré | vibrations, stabilité, LoRa | position et alertes reçues au sol ; ordre `ATTERRISSAGE` exécuté ; **désarmement automatique** après l'atterrissage |
| **3. Mission courte** | 2 passes, 5 m, petite surface, sans zone | suivi du chemin, photos (caméra **TO DO**) | `photos.csv` conforme (`verifier_fichiers_vol.py`) ; nombre de photos = estimation (± 1) ; retour au départ |
| **4. Mission avec zone interdite** | idem + une zone | détours | trajectoire hors de la zone (positions de `photos.csv`) |
| **5. Mission complète** | parcelle réelle, altitude de travail | production | rapport du pipeline d'analyse produit sans erreur ; batterie restante ≥ réserve prévue |

## 2. Listes de contrôle

### La veille

- [ ] Mission préparée, **culture choisie**, vérifications toutes vertes, fichier `.json` enregistré.
- [ ] Batteries du drone chargées ; carte SD d'AU2 vide et testée (`au2_journal_vol`).
- [ ] Capacités identiques partout (planificateur `config.js`, constantes d'AU2).
- [ ] Boîtier sol LoRa chargé ; **arrêt d'urgence** essayé au banc (double appui).

### Sur le terrain, avant le décollage

- [ ] Drone posé, **désarmé**, interrupteur d'arrêt en position sûre.
- [ ] Planificateur : *Connecter AU2 (câble USB)*, « J'ai vérifié… », *Envoyer* :
      « Mission N chargée dans AU2 » et « Archivée ».
- [ ] Débrancher le câble USB.
- [ ] Carte SD en place ; caméra propre et fixée au nadir.
- [ ] Liaison LoRa : position reçue au sol.

### Après l'atterrissage

- [ ] Attendre le **désarmement automatique** (3 s posé) avant de manipuler le drone.
- [ ] Transférer le dossier du vol et les photos vers `data\vols\entrant\<vol>\` (Wi-Fi : **TO DO** ; d'ici là, lire les cartes SD sur le PC).
- [ ] `python protocole/outils/verifier_fichiers_vol.py <dossier> --mission data\missions\mission_<id>.json`.
- [ ] Lire `boite_noire.csv` : toute ligne `CRITIQUE` ou `URGENCE` s'explique avant le vol suivant.
- [ ] Noter : durée, pourcentage de batterie consommé (pour étalonner
  `drone.puissanceMoyenneW` dans le planificateur), anomalies.

## 3. Injection de pannes au banc (hélices démontées)

Pour chaque panne, vérifier la réaction **et** la ligne de la boîte noire.

| Panne provoquée | Réaction attendue | Ligne attendue dans `boite_noire.csv` |
|---|---|---|
| Débrancher la liaison AU1 ↔ AU2 | AU1 : atterrissage lent ; AU2 : alerte au sol | `ALERTE;0x0E;PERTE_LIAISON_AU2` (AU1, à la reconnexion) et `ALERTE;0x0D;PERTE_LIAISON_AU1` (AU2) |
| Redémarrer AU1 (reset) | AU2 note l'incident | `ALERTE;0x13;REDEMARRAGE` |
| Retirer la carte SD | alerte par LoRa, retour maison | aucune (la carte est absente) : alerte `DEFAUT_SD` reçue au sol |
| Débrancher le GPS | pas de ligne dans `photos.csv` sans heure GPS | `ALERTE;0x06;GPS_PERDU` |
| Envoyer une mission drone armé | refus `ETAT_INCOMPATIBLE` | `MISSION;0x06;MISSION_REFUSEE` |
| Un seul ordre `ARRET_URGENCE` | rien (attente de confirmation) | `ORDRE;0x24;ARRET_URGENCE` (1re demande) |
| Deux ordres `ARRET_URGENCE` en moins de 2 s | moteurs coupés, désarmé | `ORDRE;0x24` puis `ALERTE;0x11;ARRET_URGENCE` |
| Trame abîmée (fil débranché quelques millisecondes) | trame rejetée | `LIAISON;…;ERREUR_LIAISON` |

## 4. Analyse après vol

```bash
python protocole/outils/verifier_fichiers_vol.py "drone/vols/entrant/<vol>" --mission "drone/missions/mission_<id>.json"
```

* **`photos.csv`** : espacement entre positions successives à comparer à la
  « distance entre photos » du planificateur ; `index_waypoint` situe chaque
  photo sur le plan de vol.
* **`boite_noire.csv`** : se lit dans un tableur (séparateur `;`) ; trier par
  `temps_ms` ; filtrer `gravite` = `CRITIQUE` ou `URGENCE`.
* **Analyse des cultures** : le pipeline d'analyse (`src\modules\pipeline-analyse`)
  reprend le dossier du vol et la mission archivée.
