# Planificateur de mission : utilisation

Le code et son organisation sont décrits dans
[GUIDE.md du module](../src/modules/planificateur/GUIDE.md). Ce document explique
comment le servir, préparer une mission, l'envoyer à AU2 par le câble USB et
l'archiver pour le pipeline d'analyse.

## 1. Servir la page en local (la manière la plus simple)

Web Serial (l'accès au câble USB) n'est autorisé par Chrome que dans un
**contexte sécurisé** : une page `https://…` ou `http://localhost`. Ouvrir
`index.html` en double-clic (`file://`) ne fonctionne pas (ni câble USB, ni
modules JavaScript). La solution retenue est un mini-serveur Python, sans
installation de paquet. Il sert aussi à **archiver** les missions envoyées :
la page ne peut pas écrire seule dans un dossier du PC.

| Système | Commande | Remarque |
|---|---|---|
| Windows | double-clic sur `planificateur\lancer.bat` | Python 3 doit être installé (python.org, cocher « Add python.exe to PATH ») |
| macOS / Linux | `./planificateur/lancer.sh` | Python 3 est en général déjà présent |
| partout | `python serveur_local.py [port] [--sans-navigateur] [--missions DOSSIER]` | port 8000 par défaut ; dossier d'archive par défaut : `data\missions` |

Le serveur n'écoute que sur `127.0.0.1` (la machine elle-même : personne
d'autre sur le réseau ne voit la page), impose les bons types MIME et désactive
le cache. Il ouvre Chrome sur `http://localhost:8000` et affiche le dossier
d'archive (avec un avertissement s'il n'existe pas). Arrêt : `Ctrl+C`.

Pourquoi pas `https` ? Il faudrait un certificat (auto-signé, donc des
avertissements) pour un gain nul : `localhost` est considéré comme sûr par
Chrome.

## 2. Navigateurs

| Navigateur | Web Serial (câble USB vers AU2) |
|---|---|
| Chrome ou Edge, Windows 10/11, macOS, Linux | oui (sous Linux : être dans le groupe `dialout` pour ouvrir `/dev/ttyACM0`) |
| Firefox, Safari | non (le planificateur fonctionne, mais sans envoi) |

Sans Web Serial, tout le reste (carte, tracé, calculs, vérifications, fichiers,
**AU2 simulé**, archivage) fonctionne.

## 3. Préparer une mission

1. **Culture de la parcelle** (obligatoire) : blé, maïs ou pommier. Elle est
   enregistrée dans le fichier de mission (`"culture": "ble" | "mais" |
   "pommier"`) mais **n'est pas transmise au drone** : le pipeline d'analyse
   s'en sert pour choisir son modèle de détection. Un ancien fichier sans
   culture s'ouvre, mais l'envoi reste bloqué tant qu'elle n'est pas choisie.
2. **Carte** : orthophotos IGN par défaut (20 cm en France) ; *Plan IGN* et
   *OpenStreetMap* au choix ; calques *Parcelles agricoles (RPG)* et *Cadastre*
   pour retrouver les limites. *Ma position* centre la carte sur le PC.
3. **Tracer les limites** : cliquer les sommets, *Terminer le tracé* (ou
   cliquer le premier point). Les sommets se déplacent à la souris ; clic
   droit sur un sommet pour le supprimer. *Annuler le dernier point* pendant le
   tracé.
4. **Ajouter une zone interdite** (arbres, ligne électrique, bâtiment…) : même
   principe ; jusqu'à 8 zones.
5. **Placer le décollage** : sert aux estimations (trajets aller et retour).
6. **Chemin** :
   * *automatique* : altitude, vitesse maximale (0 = automatique),
     recouvrements frontal et latéral, marges aux limites et aux zones, cap des
     passes (automatique = passes parallèles au côté qui donne la plus petite
     largeur de terrain, donc le moins de passes) ; le quadrillage contourne
     les zones interdites ;
   * *manuel* : *Ajouter des waypoints sur la carte*, avec altitude, vitesse et
     action (passage, photo unique, début ou fin des photos).
7. **Fin de mission** : retour au départ, atterrissage sur place ou vol stationnaire.
8. **Lire les calculs** : résolution au sol, emprise d'une photo, espacement
   des passes et des photos, nombre de photos, longueur, durée, énergie
   (pourcentage de batterie avec réserve). Les avertissements s'affichent en
   orange (vitesse réduite par la cadence photo, flou de bougé probable…).
9. **Vérifications** : la liste doit être entièrement verte pour envoyer
   (culture choisie, polygones fermés et valides, chemin entièrement dans les
   limites et hors des zones, altitudes dans les bornes, nombre de waypoints
   compatible avec la mémoire d'AU2, vitesses). Tant que la caméra n'est pas
   choisie, « Paramètres de la caméra » reste en **avertissement** (valeurs
   provisoires dans `js/config.js`).
10. **Enregistrer…** la mission (fichier `.json`) ; *Ouvrir…* pour la
   recharger. Le brouillon en cours est aussi gardé par le navigateur.

### Formules utilisées

| Grandeur | Formule | Exemple (caméra provisoire 12 Mpx, 10 m, 0,7 s entre photos) |
|---|---|---|
| emprise d'une photo | hauteur × taille du capteur / focale | 10 × 7,2 / 5,4 = 13,3 m (et 10 m) |
| résolution au sol (GSD) | emprise / nombre de pixels | 13,3 m / 4000 = 3,3 mm/pixel |
| espacement des passes | emprise transversale × (1 − recouvrement latéral) | 13,3 × 0,35 = 4,7 m |
| distance entre photos | emprise longitudinale × (1 − recouvrement frontal) | 10 × 0,25 = 2,5 m |
| vitesse maximale | distance entre photos / intervalle minimal | 2,5 / 0,7 = 3,6 m/s |
| exposition maximale | flou admis (pixels) × GSD / vitesse | 1 × 3,3 mm / 3 m/s = 1,1 ms |

## 4. Brancher AU2

1. Fermer le moniteur série de l'IDE Arduino (il occuperait le port).
2. Brancher le câble USB d'AU2 au PC, drone **posé et désarmé**.
3. **Connecter AU2 (câble USB)** → choisir le port de la Mega dans la liste de
   Chrome (« Arduino Mega 2560 », `COMx` sous Windows).
4. La Mega redémarre à l'ouverture du port : le planificateur attend 2 s,
   puis affiche l'état du drone d'après son heartbeat (« Drone désarmé ·
   mission non chargée »).

## 5. Envoyer une mission

1. Relire la carte, la culture, les calculs et les vérifications, puis cocher
   **« J'ai vérifié… »**. Cette case remplace toute confirmation sur le drone :
   elle se **décoche toute seule** à chaque modification de la mission et
   après chaque envoi.
2. **Envoyer la mission** : un nouvel identifiant (non encore archivé) est
   attribué ; la barre de progression suit l'envoi (accusé de réception de
   chaque élément), puis la **relecture** complète, puis la fin (CRC). Une
   coupure est rattrapée par réémission ; un élément relu différent est
   renvoyé.
3. Succès : « Mission N chargée dans AU2 (relue et validée) », puis
   **archivage** dans `data\missions\mission_N.json` (chemin affiché).
   Si ce numéro est déjà archivé avec une autre mission, le fichier prend un
   suffixe (`mission_N_2.json`) : rien n'est jamais écrasé.
4. Refus : le journal donne la raison. **Drone armé ou en vol** : AU2 refuse
   toute nouvelle mission ; attendre l'atterrissage (le drone se désarme seul
   au bout de 3 s posé), puis renvoyer.

Chaque erreur et chaque avertissement du journal est aussi écrit dans
`data\missions\journal_planificateur.txt` (date UTC, niveau, mission,
texte).

**AU2 simulé** remplace la carte par une imitation dans la page : pratique
pour essayer sans matériel. Dans la console du navigateur,
`planificateur.au2Simule.arme = true` simule un drone armé.

## 6. Dépannage

| Message | Que faire |
|---|---|
| « Web Serial exige une page en http://localhost » | passer par `lancer.bat` / `lancer.sh` |
| « Web Serial indisponible » | Chrome ou Edge sur PC |
| « aucun port choisi » | choisir le port de la Mega dans la liste ; vérifier le câble (un câble « charge seule » ne transporte pas de données) |
| « port inaccessible » / « déjà ouvert » | fermer le moniteur série de l'IDE Arduino ou l'autre onglet du planificateur |
| « pas de réponse » | le croquis d'AU2 ne répond pas au protocole (mauvais croquis, autre débit que 115 200) |
| « drone armé ou en vol » | poser le drone ; attendre le désarmement automatique ; renvoyer |
| « Archivage impossible : serveur d'archivage absent » | ouvrir la page par `lancer.bat`, pas par un autre serveur |
| « Archivage impossible : dossier introuvable » | créer `Bureau\drone`, ou lancer `serveur_local.py --missions DOSSIER` |
| Vérification « Culture » en échec | choisir la culture en haut de la section 1 |
| Fond de carte gris | pas de réseau, ou zoom au-delà de la résolution disponible ; essayer *Plan IGN* ou *OpenStreetMap* |
| Vérification « nombre de waypoints » en échec | augmenter l'altitude, réduire le recouvrement latéral, découper la parcelle |
| Énergie > 100 % | même remèdes ; ou plusieurs missions |
