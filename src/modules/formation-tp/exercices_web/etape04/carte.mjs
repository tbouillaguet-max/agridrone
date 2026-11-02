// =============================================================================
// Étape 4 — carte IGN, tracé des limites et des zones interdites
// (voir tp/etape_04_carte_web.md). Ouvrir la page avec tp/exercices_web/lancer.*
//
// Leaflet est chargé par index.html : il fournit la variable globale `L`
// (documentation : https://leafletjs.com/reference.html).
// =============================================================================
import { aire, contient, estSimple, versMetres } from "./geometrie.mjs";

// Orthophotos IGN (Géoplateforme, WMTS) : gratuites, sans clé, 20 cm en France.
const IGN_ORTHO = "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0" +
  "&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/jpeg";

// État de la page : les polygones sont des tableaux de [lat, lon] (comme le fichier de mission).
const etat = { mode: null, enCours: [], limites: null, zones: [] };
const $ = (id) => document.getElementById(id);
const message = (t) => { $("message").textContent = t; };

// TODO 1 — Créer la carte dans <div id="carte">, centrée sur la France ([46.6, 2.4], zoom 6),
//          avec le fond IGN_ORTHO (maxNativeZoom 19, maxZoom 22, attribution « © IGN Géoplateforme »).
//          Puis un L.layerGroup() ajouté à la carte, qui contiendra tout ce qu'on dessine.

// TODO 2 — Au clic sur la carte (événement "click", e.latlng), si un tracé est en cours
//          (etat.mode non nul), ajouter [lat, lon] à etat.enCours et redessiner.

// TODO 3 — redessiner() : vider le calque puis dessiner
//          - les limites (L.polygon) en vert, en ROUGE si le polygone n'est pas simple
//            (convertir en mètres avec versMetres autour du premier sommet, puis estSimple) ;
//          - chaque zone interdite en rouge, en pointillés si elle est invalide ou n'est pas
//            entièrement dans les limites (contient pour chacun de ses sommets) ;
//          - le tracé en cours (L.polyline + un L.circleMarker par sommet).

// TODO 4 — Boutons : #btn-limites et #btn-zone commencent un tracé (une zone exige des limites) ;
//          #btn-terminer l'achève (au moins 3 sommets) ; #btn-effacer remet tout à zéro.

// TODO 5 — Sous la carte (#bilan) : nombre de sommets, aire des limites en hectares,
//          validité ; pour chaque zone, son aire en m² et si elle est dans les limites.

// Bonus — Conserver le tracé dans localStorage ; sommets déplaçables (L.marker draggable).

message("À vous : complétez carte.mjs (TODO 1 à 5).");
void aire; void contient; void estSimple; void versMetres; void IGN_ORTHO; void etat; // (à retirer)
