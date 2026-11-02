# Module : `protocole`

> Dossier : `src/modules/protocole/`. Référence complète : [`SPECIFICATION.md`](SPECIFICATION.md). Notice historique : `docs/notices/notice_protocole_au2.md`.

## 1. Rôle
Protocole commun PC ↔ AU2 ↔ AU1 (trames `AA 55`, CRC, cycle de vie, arrêt d'urgence) et contrat des fichiers de vol écrits par AU2 sur sa carte SD. Fournit les en-têtes C++ pour Arduino, des vecteurs de test et un banc AU2 exécutable sur PC.

## 2. Interfaces (Contrat d'entrée/sortie)
- **Point d'entrée** : `arduino/ProtocoleDrone/ProtocoleDrone.h` et `FichiersVol.h` (bibliothèque Arduino) ; `SPECIFICATION.md` (référence).
- **Entrées** :
  - mission du planificateur (spécification § 6.5, § 8.2) ;
  - alertes et télémétrie d'AU1, ordres du sol (ATTERRISSAGE, RETOUR_MAISON, ARRET_URGENCE).
- **Sorties** (contrat avec `pipeline-analyse`, ne pas modifier sans prévenir) :
  - dossier de vol `/vols/mission_<id 5 chiffres>_<n>/` avec `photos.csv` (`fichier;horodatage_utc;lat;lon;altitude_rel_m;cap_deg;index_waypoint;id_mission`) et `boite_noire.csv` (`horodatage_utc;temps_ms;source;categorie;code;nom;gravite;action;valeur;actif;detail`) ;
  - `vecteurs_test.json` (généré par `outils/generer_vecteurs.py`).

## 3. Dépendances Déclarées
- **Consomme** : aucun
- **Fournit à** : `planificateur`, `pipeline-analyse`, `formation-tp`, `au1-au2` (futur programme de vol)
- **Données (`data/`)** : aucune ; `outils/verifier_fichiers_vol.py` lit un dossier de vol

## 4. Commandes Propres
Depuis `src/modules/protocole/`.
- **Techno** : C++ (Arduino) + Python (outils)
- **Installer** : compilateur C++ et `make` pour les tests hôte ; Python ≥ 3.10 sans dépendance
- **Lint / Build** : `python outils/generer_vecteurs.py` (régénère `vecteurs_test.json` et `vecteurs_test.h`)
- **Tests** : `make -C arduino/test_hote` ; `python outils/verifier_fichiers_vol.py exemples_fichiers/vol_exemple`

## 5. Règle d'Isolation (Interdits)
- Ne jamais changer les colonnes de `photos.csv` / `boite_noire.csv` sans prévenir (contrat avec `pipeline-analyse`) ; mettre alors `docs/contrats.md` à jour.
- Ne jamais utiliser `printf("%f")` pour écrire les fichiers de vol (mise en forme par `FichiersVol.h`).
- La sécurité (refus de mission si armé, arrêt d'urgence à deux ordres) ne se contourne pas dans un module consommateur.
