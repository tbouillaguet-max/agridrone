# Étape 5 — Page web : chemin manuel et quadrillage automatique, calculs, vérifications

> Durée indicative : 6 h · Matériel : PC avec Chrome, Node 20+ · Prérequis : étape 4

## 1. Objectif et ce qui sera testable

Calculer **comment photographier** un terrain avec la caméra du drone (résolution,
recouvrements, vitesse, exposition), générer un **chemin en aller-retour**,
estimer la mission (longueur, photos, durée) et **vérifier** le chemin avant
de l'envoyer. Puis comprendre comment le planificateur de référence traite les
terrains quelconques et les zones interdites.

Ce qui sera vérifié :

| Livrable | Vérification |
|---|---|
| `tp/exercices_web/etape05/calculs.mjs` (6 fonctions) | `npm test` : les 9 tests (étapes 4 et 5) verts |
| Une mission réelle préparée avec le planificateur de référence | fichier `.json` enregistré, vérifications vertes, chiffres comparés aux vôtres |

## 2. Notions et fonctions

### 2.1 La photo aérienne en quatre grandeurs

Un capteur de largeur *c* derrière une focale *f*, à la hauteur *H*, voit au
sol une bande de largeur **emprise = H × c / f** (triangles semblables).

```
          capteur c
           ┌──┐
            \/       focale f
            /\
           /  \      hauteur H
          /    \
   ──────┴──────┴──────  sol : emprise = H × c / f
```

| Grandeur | Formule | caméra d'exemple à 10 m (capteur 7,2 × 5,4 mm, focale 5,4 mm, 4000 × 3000 px) |
|---|---|---|
| emprise transversale (grand côté en travers) | H × 7,2 / 5,4 | 13,33 m |
| emprise longitudinale | H × 5,4 / 5,4 | 10 m |
| **GSD** (taille d'un pixel au sol) | emprise / pixels | 13,33 m / 4000 = **3,3 mm** |
| espacement des passes | emprise transversale × (1 − recouvrement latéral) | 65 % → 4,67 m |
| distance entre photos | emprise longitudinale × (1 − recouvrement frontal) | 75 % → 2,5 m |

Le **recouvrement** (60 à 80 %) est indispensable : le logiciel d'assemblage
(OpenDroneMap) retrouve les mêmes points sur plusieurs photos pour les
recoller et reconstituer le relief.

Deux limites sur la vitesse :

* **cadence** : la caméra ne prend pas plus d'une photo toutes les
  *intervalle minimal* secondes (à mesurer sur la caméra retenue) : v ≤ distance entre photos / intervalle ;
* **flou de bougé** : pendant l'exposition *t*, le drone avance de v × t ; pour
  rester sous 1 pixel : t ≤ GSD / v. À 3,6 m/s et 3,3 mm : t ≤ 0,93 ms. C'est
  pourquoi la caméra doit être réglée en **exposition courte**.

### 2.2 Couvrir un terrain : le parcours en aller-retour

Sur un rectangle, on trace des passes parallèles espacées de *e*, parcourues
alternativement dans un sens et dans l'autre (« boustrophédon », comme un
labour). Chaque passe est une paire de waypoints : `DEBUT_PHOTOS` au début,
`FIN_PHOTOS` à la fin. Le drone vole entre les passes sans photographier.

```
y=55  ●───────────────────────────▶●
                                    │
y=45  ●◀───────────────────────────●
      │
y=35  ●───────────────────────────▶●     ● waypoint ; ── photos actives ; │ transit
 …
```

### 2.3 Terrains quelconques et zones interdites (planificateur de référence)

`planificateur/js/quadrillage.js` généralise en cinq temps :

1. **rotation** pour que les passes soient horizontales, dans la direction
   qui donne le **moins de passes** (la plus petite largeur du terrain, testée
   sur chaque côté de l'enveloppe convexe) ;
2. sur chaque passe, les **intervalles libres** : dans les limites, hors des
   zones, à la distance de marge des bords ;
3. **cellules** : une zone au milieu du champ coupe certaines passes en deux ;
   on regroupe les intervalles en cellules couvrables chacune en aller-retour
   (décomposition « boustrophédon ») ;
4. **ordre** des cellules : à chaque fois la plus proche de la position courante ;
5. **détours** : une liaison qui couperait une zone est remplacée par le plus
   court chemin passant par les coins des obstacles (graphe de visibilité,
   algorithme de Dijkstra).

Le nombre de passes est choisi pour que les **photos** couvrent toute la
largeur : (n − 1) × espacement + emprise ≥ largeur.

### 2.4 Les vérifications avant envoi

Avant d'envoyer, le planificateur vérifie (`js/verifications.js`) — et AU2
refait à la réception les contrôles de format et de capacité (`MISSION_ACK`) :

* limites : polygone d'au moins 3 sommets, simple, d'aire non nulle ;
* zones : polygones simples, en nombre et en sommets compatibles avec AU2 ;
* nombre de waypoints ≤ capacité d'AU2 (150) ;
* chaque waypoint dans les limites et hors des zones ;
* **chaque tronçon** entièrement dans les limites et hors des zones (deux
  waypoints corrects peuvent être reliés par un tronçon qui coupe une zone) ;
* altitudes et vitesses dans les bornes.

### 2.5 JavaScript : tableaux d'objets

```js
const points = [];
points.push({ x: 5, y: 5, action: 1 }, { x: 95, y: 5, action: 2 });
const [xa, xb] = i % 2 === 0 ? [5, 95] : [95, 5];          // décomposition, comme std::tie
const total = points.reduce((s, p) => s + p.x, 0);         // std::accumulate
problemes.push(`waypoint ${i} hors des limites`);          // texte avec ${…} (gabarit)
```

## 3. Tâche

### 3.1 Calculs (tests automatiques)

Compléter `tp/exercices_web/etape05/calculs.mjs` (il importe **votre**
géométrie de l'étape 4) :

1. `prisesDeVue(p, camera)` — le grand côté de l'image perpendiculaire aux passes ;
2. `passesRectangle(largeurM, hauteurM, espacementM, margeM)` — spécification précise dans le fichier ;
3. `longueur(points)` ;
4. `nombrePhotos(points, pasM)` — une photo sur chaque extrémité, puis une tous les `pasM` mètres (SPECIFICATION.md § 6.5) ;
5. `duree(points, vitesseMs, altitudeM)` ;
6. `verifierChemin(limites, zones, points, maxWaypoints)` — messages imposés, dans l'ordre imposé.

### 3.2 Une vraie mission avec le planificateur de référence

1. `planificateur/lancer.bat` (ou `lancer.sh`).
2. Tracer une parcelle réelle (calque RPG pour retrouver ses limites), une zone
   interdite (un arbre, un poteau), placer le décollage.
3. Chemin automatique à 10 m, recouvrements 75 / 65 %. Relever : GSD,
   espacements, nombre de passes, de cellules, de photos, durée, énergie.
4. Refaire le calcul de l'emprise, du GSD et des espacements avec **vos**
   fonctions (console du navigateur ou petit script Node) : mêmes valeurs ?
5. Essayer : 5 m d'altitude (combien de waypoints ? que dit la vérification ?),
   puis une zone interdite qui touche la limite du terrain.
6. *Enregistrer…* la mission en JSON.

### Contraintes

* `verifierChemin` utilise vos fonctions de l'étape 4 (pas de nouvelle géométrie).
* Aucune valeur numérique « en dur » de la caméra dans `calculs.mjs` : tout
  vient des paramètres.

### Critères de réussite

* `npm test` : 9 tests verts.
* Les chiffres du planificateur et les vôtres concordent (à l'arrondi près).
* Vous savez expliquer pourquoi la mission à 5 m est refusée sur une grande parcelle.

### Bonus

* Passes dans une direction quelconque : tourner les points de −θ, générer
  les passes, tourner le résultat de +θ.
* Énergie : avec 200 W en moyenne et une batterie de 68 Wh dont 25 % de
  réserve, quelle surface peut-on couvrir à 10 m en un vol ?

## 4. Test

```bash
cd tp/exercices_web
npm test
```

Pour lire un test qui échoue : le message donne la valeur obtenue et la
valeur attendue (`13.2 ≠ 13.333 (± 0.001)`).

---
---

## 5. Correction

> ⚠️ **Correction de l'étape 5.** À lire après avoir terminé.

Fichier : [`tp/corrections/web/etape05/calculs.mjs`](corrections/web/etape05/calculs.mjs) ;
`npm run test:corrections`.

### 5.1 Prises de vue

```js
export function prisesDeVue(p, camera) {
  const empriseLargeurM = (p.altitudeM * camera.capteurLargeurMm) / camera.focaleMm;
  const empriseLongueurM = (p.altitudeM * camera.capteurHauteurMm) / camera.focaleMm;
  const gsdM = empriseLargeurM / camera.imageLargeurPx;
  const espacementPassesM = empriseLargeurM * (1 - p.recouvrementLateralPct / 100);
  const distancePhotosM = empriseLongueurM * (1 - p.recouvrementFrontalPct / 100);
  const vitesseMs = Math.min(p.vitesseMaxMs, distancePhotosM / camera.intervalleMinS);
  const expositionMaxUs = ((p.flouMaxPx * gsdM) / vitesseMs) * 1e6;
  return { empriseLargeurM, empriseLongueurM, gsdMm: gsdM * 1000, espacementPassesM, distancePhotosM, vitesseMs, expositionMaxUs };
}
```

La version de référence (`calculerPrisesDeVue` dans
[`planificateur/js/calculs.js`](../planificateur/js/calculs.js)) ajoute
l'option « grand côté dans l'axe » et produit des **avertissements**
(vitesse réduite par la cadence, flou probable) affichés en orange.

### 5.2 Passes, longueur, photos, durée

```js
export function passesRectangle(largeurM, hauteurM, espacementM, margeM) {
  const bande = hauteurM - 2 * margeM;
  const n = bande <= 0 ? 1 : Math.ceil(bande / espacementM) + 1;
  const points = [];
  for (let i = 0; i < n; i++) {
    const y = n === 1 ? hauteurM / 2 : margeM + (i * bande) / (n - 1);   // réparties régulièrement
    const [xa, xb] = i % 2 === 0 ? [margeM, largeurM - margeM] : [largeurM - margeM, margeM];
    points.push({ x: xa, y, action: 1 }, { x: xb, y, action: 2 });
  }
  return points;
}
```

Répartir les passes régulièrement garde un espacement réel **inférieur ou
égal** à l'espacement demandé : le recouvrement n'est jamais plus faible que
prévu. `nombrePhotos` est la règle de déclenchement d'AU2 réduite au comptage ;
`statistiquesChemin` (planificateur) fait le même calcul et ajoutent le temps de virage, de décollage et d'atterrissage,
le transit depuis le point de décollage, l'énergie et le pourcentage de batterie.

### 5.3 Vérifications

```js
const toucheBord = (a, b, poly) => poly.some((p, i) => segmentsSeCoupent(a, b, p, poly[(i + 1) % poly.length]));

export function verifierChemin(limites, zones, points, maxWaypoints) {
  const problemes = [];
  if (limites.length < 3 || !estSimple(limites)) problemes.push("limites invalides");
  if (points.length > maxWaypoints) problemes.push(`trop de waypoints (${points.length} > ${maxWaypoints})`);
  points.forEach((p, i) => {
    if (!contient(limites, p)) problemes.push(`waypoint ${i} hors des limites`);
    zones.forEach((z, j) => { if (contient(z, p)) problemes.push(`waypoint ${i} dans la zone ${j}`); });
  });
  for (let i = 0; i + 1 < points.length; i++) {
    if (toucheBord(points[i], points[i + 1], limites)) problemes.push(`tronçon ${i} coupe les limites`);
    zones.forEach((z, j) => { if (toucheBord(points[i], points[i + 1], z)) problemes.push(`tronçon ${i} traverse la zone ${j}`); });
  }
  return problemes;
}
```

Dans le test, les passes à y = 25 et y = 35 longent exactement les bords de la
zone : un **contact** compte comme une traversée (le drone frôlerait l'obstacle).
Le planificateur de référence est plus exigeant : il impose en plus une
**marge** (distance minimale aux limites et aux zones), mesurée avec
`distanceSegmentSegment`.

### 5.4 Réponses aux questions du § 3.2

* À 5 m, l'emprise transversale tombe à 6,7 m et l'espacement des passes à
  2,3 m (65 %) : le nombre de passes double, celui des waypoints aussi ; sur une
  grande parcelle on dépasse les **150 waypoints** qu'AU2 peut stocker, et
  l'énergie dépasse la batterie. Remèdes : monter, réduire le recouvrement
  latéral, ou découper la parcelle en plusieurs missions.
* Une zone qui touche la limite partage le terrain : le quadrillage crée des
  cellules de part et d'autre et les relie par un détour (s'il existe un
  passage assez large compte tenu des marges).
* Bonus énergie : 68 Wh × 75 % = 51 Wh utilisables, soit 51 / 200 h ≈ 15 min
  de vol. Pour un carré de 1 ha à 10 m : ⌈(100 − 13,3) / 4,67⌉ + 1 = 20 passes
  de 100 m, plus 19 liaisons de 4,67 m, soit 2 090 m à 3,57 m/s ≈ 585 s ; avec
  3 s par waypoint (40 × 3 = 120 s), la montée et la descente (13 s) et le
  décollage et l'atterrissage (30 s), ≈ 750 s = 12,5 min et 42 Wh. On couvre
  donc **environ 1 ha par vol** (un peu plus sur une parcelle allongée, où les
  virages pèsent moins).
