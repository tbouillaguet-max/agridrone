# Étape 4 — Page web : carte, tracé des limites et des zones interdites

> Durée indicative : 5 h · Matériel : PC avec Chrome, Python 3, Node 20+ · Prérequis : bases de JavaScript

## 1. Objectif et ce qui sera testable

Construire la première brique du planificateur : une page web qui affiche les
**orthophotos IGN**, permet de **tracer les limites** du terrain et des **zones
interdites**, et vérifie leur géométrie (polygone simple, zone dans les
limites, surface).

Ce qui sera vérifié :

| Livrable | Vérification |
|---|---|
| `tp/exercices_web/etape04/geometrie.mjs` (5 fonctions) | `npm test` : 5 tests verts (étape 4) |
| `tp/exercices_web/etape04/carte.mjs` (page) | tracé dans Chrome : terrain vert, polygone croisé en rouge, zone hors limites en pointillés, surfaces affichées |

## 2. Notions et fonctions

### 2.1 Une page web pour un développeur C++

* **HTML** décrit le contenu (`<button id="btn-limites">`), **CSS** sa
  présentation, **JavaScript** son comportement.
* Le JavaScript moderne s'écrit en **modules** (`import` / `export`), sans
  compilation : le navigateur lit directement les fichiers.

| C++ | JavaScript |
|---|---|
| `const int n = 3;` | `const n = 3;` |
| `int x = 0;` | `let x = 0;` (jamais `var`) |
| `std::vector<P> v; v.push_back(p);` | `const v = []; v.push(p);` |
| `struct P { double x, y; };` | objet littéral `{ x: 1, y: 2 }` |
| `std::pair<double,double>` | tableau `[48.3, 1.6]` |
| `[](P p) { return p.x; }` | `(p) => p.x` |
| `for (auto& p : v)` | `for (const p of v)` |
| `v.size()` | `v.length` |
| `std::abs`, `std::hypot` | `Math.abs`, `Math.hypot` |
| exception | `throw new Error("…")` |
| `printf` | `console.log(…)` (outils de développement : F12) |

Les nombres sont tous des `double` (64 bits) ; `===` compare sans conversion
(toujours préférer `===` à `==`).

Le navigateur appelle nos fonctions sur des **événements** :

```js
document.getElementById("btn-limites").onclick = () => commencer("limites");
carte.on("click", (e) => ajouterSommet([e.latlng.lat, e.latlng.lng]));
```

### 2.2 Leaflet et les tuiles WMTS de l'IGN

**Leaflet** (40 ko, copié dans `planificateur/lib/leaflet/`) affiche une carte
faite de **tuiles** : des images de 256 × 256 pixels, numérotées par niveau de
zoom, ligne et colonne. L'IGN les sert gratuitement, sans clé, par sa
**Géoplateforme** (service WMTS, licence ouverte Etalab 2.0) :

```js
const IGN_ORTHO = "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0" +
  "&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/jpeg";

const carte = L.map("carte").setView([46.6, 2.4], 6);                    // centre [lat, lon], zoom
L.tileLayer(IGN_ORTHO, { maxNativeZoom: 19, maxZoom: 22, attribution: "© IGN Géoplateforme" }).addTo(carte);
L.polygon([[48.30, 1.60], [48.30, 1.61], [48.31, 1.61]], { color: "green" }).addTo(carte);
```

`maxNativeZoom: 19` : l'IGN fournit des tuiles jusqu'au niveau 19 (≈ 20 cm par
pixel) ; au-delà, Leaflet agrandit les tuiles du niveau 19.

### 2.3 Des degrés aux mètres

Les positions sont en **degrés** (WGS 84, comme le GPS). Pour mesurer des
distances et des surfaces, on passe en **mètres** dans un repère local
(x vers l'est, y vers le nord) autour d'une origine. Sur une parcelle de
quelques centaines de mètres, la Terre est plate à quelques millimètres près :

```
y = (lat − lat₀) × 111 132,92 m          (longueur d'un degré de latitude)
x = (lon − lon₀) × 111 320 m × cos(lat₀) (un degré de longitude rétrécit vers les pôles)
```

### 2.4 Algorithmes de géométrie

* **Aire** (formule du lacet) : ½ |Σ (xᵢ·yᵢ₊₁ − xᵢ₊₁·yᵢ)|.
* **Orientation** de trois points : le signe du produit vectoriel
  (b − a) × (c − a) dit si c est à gauche (> 0), à droite (< 0) ou aligné (0).
* **Deux segments se coupent** si chacun a les extrémités de l'autre de part et
  d'autre de lui ; plus les cas d'alignement (contact, chevauchement).
* **Polygone simple** : aucun côté ne coupe un côté non adjacent. Un polygone
  « papillon » (côtés croisés) n'a pas d'intérieur bien défini : le quadrillage
  et les contrôles du planificateur le refusent.
* **Point dans un polygone** : une demi-droite horizontale partant du point
  traverse un nombre **impair** de côtés si le point est dedans.

```
   orientation > 0              segments qui se coupent         point dans un polygone
        c                         c       b                      ┌───────┐
       /                           \     /                       │   p ──┼──▶  1 croisement : dedans
  a ──────▶ b                       \   /                        │       │
                                      ╳                          └───────┘   p ──▶  0 : dehors
                                    /   \
                                  a       d
```

### 2.5 Servir la page en local

Chrome refuse les modules JavaScript ouverts par double-clic (`file://`), et
plus tard l'accès au câble USB (Web Serial) hors de `https://` ou
`http://localhost`. On sert donc
la racine du dépôt avec le petit serveur Python du planificateur :

```bash
./tp/exercices_web/lancer.sh        # Windows : double-clic sur tp\exercices_web\lancer.bat
# → http://localhost:8001/tp/exercices_web/
```

## 3. Tâche

### 3.1 Géométrie (tests automatiques)

Compléter `tp/exercices_web/etape04/geometrie.mjs` :

1. `versMetres(origine, p)` et `versGeo(origine, v)` ;
2. `aire(poly)` ;
3. `segmentsSeCoupent(a, b, c, d)` (un contact compte) ;
4. `estSimple(poly)` ;
5. `contient(poly, p)`.

### 3.2 La page (essai dans Chrome)

Compléter `tp/exercices_web/etape04/carte.mjs` (TODO 1 à 5) :

* la carte IGN centrée sur la France ;
* **Tracer les limites** : chaque clic ajoute un sommet ; **Terminer le tracé** (3 sommets au moins) ;
* **Ajouter une zone interdite** : même principe, plusieurs zones possibles, seulement s'il y a des limites ;
* dessin : limites en vert (en **rouge** si le polygone n'est pas simple),
  zones en rouge plein (en **pointillés** si une zone est invalide ou sort des
  limites), tracé en cours en bleu avec ses sommets ;
* sous la carte : nombre de sommets et surface des limites en **hectares**,
  et pour chaque zone sa surface en m² et si elle est dans les limites ;
* **Tout effacer**.

### Contraintes

* Polygones stockés en `[lat, lon]` (comme le fichier de mission du planificateur) ;
  calculs en mètres autour du premier sommet des limites.
* Aucune bibliothèque en plus de Leaflet ; aucune donnée envoyée sur Internet
  (seules les tuiles sont téléchargées).

### Critères de réussite

* `npm test` : les 5 tests « ex1 » à « ex5 » verts (ceux de l'étape 5 restent
  rouges pour l'instant).
* Sur une vraie parcelle (zoom 17 à 19), la surface affichée est à 2 % près
  celle du cadastre ou du RPG (calques du planificateur de référence).
* Un tracé en papillon s'affiche en rouge ; une zone qui déborde, en pointillés.

### Bonus

* Garder le tracé dans `localStorage` (il survit au rechargement de la page).
* Sommets déplaçables (`L.marker(p, { draggable: true })`, événement `dragend`).
* Bouton « Enregistrer » qui télécharge un JSON `{ limites, zones }`.

## 4. Test

```bash
cd tp/exercices_web
npm test                       # vos fonctions
npm run test:corrections       # (pour comparer) la correction
```

Dans Chrome (`lancer.sh` / `lancer.bat`) : *Étape 4 — votre page*. Ouvrir les
outils de développement (F12) : l'onglet *Console* ne doit afficher aucune
erreur. Tracer un terrain sur un champ de votre choix, une zone dedans, une
zone qui déborde, puis un terrain en papillon.

---
---

## 5. Correction

> ⚠️ **Correction de l'étape 4.** À lire après avoir terminé.

Fichiers : [`tp/corrections/web/etape04/`](corrections/web/etape04/) — page
directement utilisable : *Étape 4 — correction* sur la page d'accueil des exercices.

### 5.1 Géométrie

```js
export function versMetres([lat0, lon0], [lat, lon]) {
  return {
    x: (lon - lon0) * 111320 * Math.cos((lat0 * Math.PI) / 180),
    y: (lat - lat0) * 111132.92,
  };
}

export function aire(poly) {
  let s = 0;
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i];
    const b = poly[(i + 1) % poly.length];      // le dernier sommet se referme sur le premier
    s += a.x * b.y - b.x * a.y;
  }
  return Math.abs(s) / 2;
}

const orientation = (a, b, c) => (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
const surSegment = (a, b, c) =>
  Math.min(a.x, b.x) <= c.x && c.x <= Math.max(a.x, b.x) && Math.min(a.y, b.y) <= c.y && c.y <= Math.max(a.y, b.y);

export function segmentsSeCoupent(a, b, c, d) {
  const o1 = orientation(a, b, c), o2 = orientation(a, b, d);
  const o3 = orientation(c, d, a), o4 = orientation(c, d, b);
  if (((o1 > 0 && o2 < 0) || (o1 < 0 && o2 > 0)) && ((o3 > 0 && o4 < 0) || (o3 < 0 && o4 > 0))) return true;
  return (o1 === 0 && surSegment(a, b, c)) || (o2 === 0 && surSegment(a, b, d)) ||
    (o3 === 0 && surSegment(c, d, a)) || (o4 === 0 && surSegment(c, d, b));
}
```

`estSimple` compare chaque côté à tous les côtés **non adjacents** (deux côtés
voisins partagent un sommet : ce contact-là est normal) ; `contient` compte les
croisements d'une demi-droite horizontale, avec la condition
`(a.y > p.y) !== (b.y > p.y)` qui traite proprement le cas d'un sommet à la
hauteur exacte du point.

Le planificateur de référence ([`planificateur/js/geometrie.js`](../planificateur/js/geometrie.js))
a les mêmes fonctions, avec une projection un peu plus précise (formules de
la longueur d'un degré sur l'ellipsoïde).

### 5.2 La page

L'état de la page tient dans un objet ; **chaque modification** se termine par
`redessiner()`, qui efface le calque et redessine tout. C'est simple et
largement assez rapide pour quelques polygones (c'est aussi le principe de
Compose : l'écran est une fonction de l'état).

```js
const etat = { mode: null, enCours: [], limites: null, zones: [] };
const calque = L.layerGroup().addTo(carte);

carte.on("click", (e) => {
  if (!etat.mode) return;
  etat.enCours.push([e.latlng.lat, e.latlng.lng]);
  redessiner();
});

function redessiner() {
  calque.clearLayers();
  if (etat.limites) {
    const ok = estSimple(enMetres(etat.limites));
    L.polygon(etat.limites, { color: ok ? "#2e7d32" : "#c62828", weight: 3, fillOpacity: 0.1 }).addTo(calque);
  }
  for (const z of etat.zones) {
    const ok = zoneValide(z);                    // simple ET tous ses sommets dans les limites
    L.polygon(z, { color: "#d32f2f", fillOpacity: ok ? 0.4 : 0.1, dashArray: ok ? null : "6 4" }).addTo(calque);
  }
  // … tracé en cours (polyline + circleMarker), puis afficherBilan()
}
```

Le bonus `localStorage` est dans la correction (`enregistrer()` et la relecture
au chargement). Le planificateur de référence va plus loin
([`planificateur/js/carte.js`](../planificateur/js/carte.js)) : sommets
déplaçables, suppression au clic droit, fermeture en cliquant le premier
sommet, calques RPG et cadastre, point de décollage.

Remarque : « tous les sommets de la zone sont dans les limites » ne suffit pas
pour un terrain **concave** (une zone peut enjamber le creux d'un terrain en L).
Le planificateur le vérifie aussi côté par côté (`segmentDansPolygone`) ; c'est
l'objet de l'exercice 6 de l'étape suivante.
