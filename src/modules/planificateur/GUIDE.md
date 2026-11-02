# Planificateur de mission (PC, Chrome)

Page web qui sert à préparer une mission au bureau ou au bord du champ, puis à
l'envoyer à AU2 (Arduino Mega de navigation) par le **câble USB**, et à
l'archiver pour le pipeline d'analyse des images.

Notice complète (entrées, sorties, place dans le flux de travail) :
[docs/planificateur.md](../../../docs/planificateur.md) et, dans le Projet,
`notices/notice_planificateur.md`.

* **Culture** de la parcelle (blé, maïs, pommier) : obligatoire, enregistrée
  dans le fichier de mission, non transmise au drone.

* Carte : orthophotos IGN (gratuites, 20 cm en France), plan IGN, OpenStreetMap ;
  calques facultatifs : parcelles agricoles (RPG) et cadastre.
* Tracé des **limites** du terrain et des **zones interdites** (polygones).
* Chemin : **quadrillage automatique** qui contourne les zones interdites, ou
  **waypoints manuels**.
* Calculs : résolution au sol, emprise, espacements, nombre de photos,
  longueur, durée, énergie.
* Vérifications avant envoi (polygones valides, chemin dans les limites et hors
  des zones, altitudes, nombre de waypoints compatible avec AU2, culture…).
* Fichiers de mission JSON (enregistrer, ouvrir) ; brouillon gardé dans le navigateur.
* **Confirmation** par l'opérateur (case « J'ai vérifié… », décochée à chaque
  modification), puis envoi par le **câble USB** (Web Serial) : accusés de
  réception, relecture finale, CRC ; refus d'AU2 si le drone est armé.
* **Archivage** de chaque mission chargée dans `data\missions\mission_<id>.json`
  (suffixe `_2`… si l'identifiant existe déjà), et journal des erreurs
  `journal_planificateur.txt` dans le même dossier.

## Lancer

Web Serial n'est autorisé que sur `https://` ou `http://localhost` : il faut
donc servir la page en local (un double-clic suffit). Le même serveur archive
les missions.

| Système | Commande |
|---|---|
| Windows | double-cliquer `lancer.bat` |
| Linux / macOS | `./lancer.sh` |
| n'importe où | `python serveur_local.py [--missions DOSSIER]` puis ouvrir http://localhost:8000 dans Chrome |

Le serveur (`serveur_local.py`, bibliothèque standard de Python) n'écoute que
sur la machine elle-même. Sans carte, le bouton **AU2 simulé** permet
d'essayer tout le transfert.

Une mission d'exemple est fournie : `exemples/mission_exemple.json` (bouton « Ouvrir… »).

## Organisation du code

| Fichier | Rôle |
|---|---|
| `js/config.js` | **tous les paramètres** (cartes, caméra provisoire, cultures, capacités d'AU2, énergie, liaison série) |
| `js/protocole.js` | trames, CRC, messages, décodeur de flux |
| `js/geometrie.js` | projection en mètres, polygones, segments, intervalles |
| `js/quadrillage.js` | génération automatique (cellules, aller-retour, détours) |
| `js/calculs.js` | photo, durée, énergie |
| `js/verifications.js` | contrôles avant envoi |
| `js/mission.js` | modèle (dont la culture), fichier JSON, conversion en trames |
| `js/transfert.js` | transfert fiable (accusés, relecture, fin) |
| `js/canal_serie.js` | Web Serial : câble USB vers AU2 |
| `js/au2_simule.js` | faux AU2 pour essayer sans matériel |
| `js/archivage.js` | dialogue avec `serveur_local.py` (archivage, identifiant libre, journal) |
| `serveur_local.py` | serveur local, archivage des missions, journal sur disque |
| `js/carte.js`, `js/app.js` | carte Leaflet et interface |

## Tests

```bash
cd planificateur
npm test          # ou : node --test "tests/*.test.mjs"   (Node 20 ou plus, aucune dépendance)
python -m unittest discover -s tests -p "test_*.py"      # archivage (serveur_local.py)
```

Ils vérifient le protocole contre les vecteurs partagés, la géométrie, le
quadrillage (sécurité sur 60 terrains aléatoires, couverture), les
vérifications (dont la culture), le fichier JSON, le transfert (pertes,
relecture qui détecte un stockage défaillant, refus quand le drone est armé),
que la culture n'est jamais transmise au drone, et l'archivage (suffixes,
refus explicites). Avec `BANC_AU2=hôte:port`, un test envoie aussi une mission
au banc AU2 écrit en C++ (voir [docs/tests.md](../../../docs/tests.md)).
