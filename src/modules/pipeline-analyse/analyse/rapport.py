"""Étape 6 — rapport HTML autonome (un seul fichier, ouvrable sans serveur).

Leaflet est intégré dans la page (copie de celle du planificateur) ; seuls les fonds de
carte (IGN, OSM) demandent une connexion. Les vignettes sont intégrées en base64 ;
les liens « image complète » pointent vers brut/images/ (chemins relatifs).
"""
from __future__ import annotations

import base64
import html
import io
import json
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from . import contrat as C

LIB = Path(__file__).with_name("lib")
LARGEUR_VIGNETTE = 360

# Mêmes fonds que le planificateur (planificateur/js/config.js).
FONDS = {
    "Orthophotos IGN": ["https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/jpeg",
                        {"maxNativeZoom": 19, "maxZoom": 22, "attribution": "© IGN Géoplateforme (orthophotos)"}],
    "Plan IGN": ["https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/png",
                 {"maxNativeZoom": 19, "maxZoom": 22, "attribution": "© IGN Géoplateforme"}],
    "OpenStreetMap": ["https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                      {"maxNativeZoom": 19, "maxZoom": 22, "attribution": "© contributeurs OpenStreetMap"}],
}


def _vignette(chemin: Path, detections, largeur: int = LARGEUR_VIGNETTE) -> str:
    with Image.open(chemin) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        W = im.width
        im.thumbnail((largeur, largeur * 2))
        k = im.width / W
        d = ImageDraw.Draw(im)
        for det in detections:
            if det.boite:
                x1, y1, x2, y2 = (v * k for v in det.boite)
                d.rectangle((x1, y1, x2, y2), outline=(230, 40, 30), width=2)
        tampon = io.BytesIO()
        im.save(tampon, "JPEG", quality=72, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(tampon.getvalue()).decode("ascii")


def _json(o) -> str:
    return json.dumps(o, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _e(t) -> str:
    return html.escape(str(t), quote=True)


def _pct(v: float) -> str:
    return f"{v * 100:.0f} %"


def _carte_image(a, rang: int | None, seuil: float, mode: str) -> str:
    p, r = a.photo, a.resultat
    statut = "malade" if r.malade else "sain"
    rang_txt = f'<span class="rang">{rang}</span>' if rang else ""
    if mode == "incertaine":
        info = f'<span class="chip {statut}">{statut}</span> score {r.score:.2f} · écart au seuil {abs(r.score - seuil):.2f}'
    else:
        info = f"confiance <strong>{r.score:.2f}</strong> · {len(r.detections)} zone(s) dans l'image"
    return f"""<figure class="vig" data-lat="{p.lat}" data-lon="{p.lon}">
  <a href="brut/images/{_e(p.fichier)}" target="_blank" rel="noopener"><img alt="{_e(p.fichier)}" data-vignette="{_e(p.fichier)}"></a>
  <figcaption>{rang_txt}<span class="nom">{_e(p.fichier)}</span><span class="info">{info}</span>
  <button type="button" class="voir">Voir sur la carte</button>
  <span class="pos">{p.lat:.6f}, {p.lon:.6f} · waypoint {p.index_waypoint}</span></figcaption>
</figure>"""


def ecrire_rapport(chemin: Path, *, vol, mission, modele, analyses, top, incertaines, zones,
                   explication_grille: str, avertissements: list[str], nb_top: int,
                   localisation: str = "v1", points_detections: list | None = None) -> Path:
    ok = [a for a in analyses if a.resultat]
    malades = [a for a in ok if a.resultat.malade]
    conf_moy = sum(a.resultat.score for a in malades) / len(malades) if malades else None
    a_vignette = {a.photo.fichier: a for a in ok}
    vignettes = {f: _vignette(vol.chemin_image(a.photo), a.resultat.detections) for f, a in a_vignette.items()}

    alertes_bn = [e for e in vol.evenements if e.gravite in C.GRAVITES_SIGNALEES]
    nb_avert_bn = sum(1 for e in vol.evenements if e.gravite == "AVERTISSEMENT")
    date_vol = vol.debut.strftime("%d/%m/%Y")
    heures = f"{vol.debut.strftime('%H:%M')}–{max(p.horodatage for p in vol.photos).strftime('%H:%M')} UTC"

    donnees = {
        "fonds": FONDS,
        "limites": mission.limites,
        "zones": mission.zones,
        "chemin": [[w["lat"], w["lon"]] for w in mission.waypoints],
        "photos": [{"f": a.photo.fichier, "lat": a.photo.lat, "lon": a.photo.lon,
                    "s": round(a.resultat.score, 3) if a.resultat else None,
                    "m": bool(a.resultat and a.resultat.malade), "e": a.erreur} for a in analyses],
        "cellules": zones,
        "seuil": modele.seuil,
        "detections": points_detections or [],
    }

    if not malades:
        verdict, classe_verdict = "Aucune image malade détectée", "sain"
    else:
        verdict = (f"{len(malades)} image{'s' if len(malades) > 1 else ''} malade{'s' if len(malades) > 1 else ''} "
                   f"sur {len(ok)}, dans {len(zones['features'])} zone{'s' if len(zones['features']) > 1 else ''} de la parcelle")
        classe_verdict = "malade"

    blocs_alerte = []
    if modele.factice:
        blocs_alerte.append('<div class="alerte forte"><strong>Modèle factice.</strong> Les résultats servent à tester '
                            "le pipeline et n'ont aucune valeur agronomique.</div>")
    for e in alertes_bn:
        quand = e.horodatage.strftime("%H:%M:%S UTC") if e.horodatage else f"t = {e.temps_ms / 1000:.1f} s"
        blocs_alerte.append(f'<div class="alerte forte"><strong>Boîte noire · {_e(e.gravite)}</strong> '
                            f'{_e(e.source)} {_e(e.nom)} à {quand} — {_e(e.detail or e.action)}</div>')
    for a in avertissements:
        if "FACTICE" in a:
            continue
        blocs_alerte.append(f'<div class="alerte">{_e(a)}</div>')

    top_html = "\n".join(_carte_image(a, k, modele.seuil, "top") for k, a in enumerate(top, 1)) \
        or '<p class="vide">Aucune image malade : rien à afficher ici.</p>'
    titre_top = (f"Les {len(top)} images malades les plus sûres" if len(malades) > nb_top
                 else f"Toutes les images malades ({len(malades)})")
    inc_html = "\n".join(_carte_image(a, k, modele.seuil, "incertaine") for k, a in enumerate(incertaines, 1))

    css = (LIB / "leaflet.css").read_text(encoding="utf-8")
    js = (LIB / "leaflet.js").read_text(encoding="utf-8")

    page = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rapport {_e(mission.nom)} — {date_vol}</title>
<style>{css}</style>
<style>
:root {{
  --fond:#f4f6f1; --surface:#ffffff; --texte:#1c261d; --doux:#5d6b5e; --trait:#d3dccf;
  --feuille:#2f7d3a; --feuille-pale:#e2efdf; --malade:#c0392b; --malade-pale:#f8e1dd;
  --ambre:#b7791f; --ambre-pale:#fbf0dc; --encre-carte:#ffffff;
  --police:"Segoe UI", system-ui, -apple-system, Roboto, sans-serif;
  --mono:Consolas, "Cascadia Mono", ui-monospace, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root {{
  --fond:#121713; --surface:#1a211b; --texte:#e3eae1; --doux:#9cab9c; --trait:#2f3b30;
  --feuille:#6cc27a; --feuille-pale:#1e3121; --malade:#ef7a6c; --malade-pale:#3a1f1b;
  --ambre:#e3ad5a; --ambre-pale:#352914; color-scheme:dark; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--fond); color:var(--texte); font:15px/1.5 var(--police); }}
.page {{ max-width:1200px; margin:0 auto; padding:28px 18px 60px; display:grid; gap:26px; }}
h1,h2 {{ margin:0; line-height:1.2; text-wrap:balance; }}
h1 {{ font-size:28px; }} h2 {{ font-size:19px; }}
.sur {{ font:600 11px/1 var(--mono); letter-spacing:.08em; text-transform:uppercase; color:var(--doux); }}
.meta {{ color:var(--doux); margin-top:6px; }}
.verdict {{ border-radius:10px; padding:16px 18px; font-size:19px; font-weight:600; }}
.verdict.malade {{ background:var(--malade-pale); color:var(--malade); }}
.verdict.sain {{ background:var(--feuille-pale); color:var(--feuille); }}
.chiffres {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; }}
.chiffre {{ background:var(--surface); border:1px solid var(--trait); border-radius:8px; padding:12px 14px; }}
.chiffre b {{ display:block; font-size:26px; font-variant-numeric:tabular-nums; }}
.chiffre span {{ color:var(--doux); font-size:13px; }}
.alertes {{ display:grid; gap:8px; }}
.alerte {{ background:var(--ambre-pale); color:var(--texte); border-left:4px solid var(--ambre); padding:8px 12px; border-radius:4px; font-size:14px; }}
.alerte.forte {{ background:var(--malade-pale); border-left-color:var(--malade); }}
#carte {{ height:540px; border-radius:10px; border:1px solid var(--trait); }}
.legende {{ display:flex; flex-wrap:wrap; gap:16px; font-size:13px; color:var(--doux); margin-top:8px; }}
.legende i {{ display:inline-block; width:12px; height:12px; border-radius:50%; margin-right:6px; vertical-align:-1px; }}
.legende i.carre {{ border-radius:2px; }}
section {{ display:grid; gap:12px; }}
.galerie {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:14px; }}
.vig {{ margin:0; background:var(--surface); border:1px solid var(--trait); border-radius:8px; overflow:hidden; display:flex; flex-direction:column; }}
.vig img {{ width:100%; aspect-ratio:4/3; object-fit:cover; display:block; background:var(--trait); }}
.vig figcaption {{ padding:10px 12px; display:grid; gap:4px; font-size:13px; }}
.vig .nom {{ font:600 13px var(--mono); }}
.vig .pos {{ color:var(--doux); font-size:12px; font-variant-numeric:tabular-nums; }}
.rang {{ float:right; font:700 12px var(--mono); color:var(--doux); }}
.chip {{ display:inline-block; padding:0 7px; border-radius:999px; font-size:11.5px; font-weight:600; }}
.chip.malade {{ background:var(--malade-pale); color:var(--malade); }}
.chip.sain {{ background:var(--feuille-pale); color:var(--feuille); }}
button.voir {{ justify-self:start; font:inherit; font-size:12.5px; color:var(--feuille); background:none; border:1px solid var(--trait); border-radius:5px; padding:2px 8px; cursor:pointer; }}
button.voir:hover, button.voir:focus-visible {{ border-color:var(--feuille); outline:none; }}
.note {{ color:var(--doux); font-size:13.5px; max-width:75ch; margin:0; }}
.vide {{ color:var(--doux); }}
footer {{ border-top:1px solid var(--trait); padding-top:14px; color:var(--doux); font-size:13px; display:grid; gap:4px; }}
code {{ font-family:var(--mono); font-size:12.5px; }}
.leaflet-popup-content img {{ width:240px; display:block; border-radius:4px; margin-bottom:6px; }}
</style>
</head>
<body>
<div class="page">
  <header>
    <div class="sur">Rapport d'analyse · drone agricole</div>
    <h1>{_e(mission.nom)}</h1>
    <div class="meta">Vol du {date_vol}, {heures} · culture : <strong>{_e(C.NOMS_CULTURES[mission.culture])}</strong> ·
      mission {mission.id} · modèle : {_e(modele.description or modele.type)} (seuil {modele.seuil:.2f})</div>
  </header>

  <div class="verdict {classe_verdict}">{_e(verdict)}</div>

  <div class="chiffres">
    <div class="chiffre"><b>{len(ok)}</b><span>images analysées{f" ({len(analyses) - len(ok)} en erreur)" if len(ok) < len(analyses) else ""}</span></div>
    <div class="chiffre"><b>{len(malades)}</b><span>images malades ({_pct(len(malades) / len(ok))})</span></div>
    <div class="chiffre"><b>{f"{conf_moy:.2f}" if conf_moy is not None else "—"}</b><span>confiance moyenne des malades</span></div>
    <div class="chiffre"><b>{len(zones["features"])}</b><span>zones malades sur la carte</span></div>
    <div class="chiffre"><b>{len(alertes_bn)}</b><span>alertes critiques en vol{f" · {nb_avert_bn} avertissement(s)" if nb_avert_bn else ""}</span></div>
  </div>

  {'<div class="alertes">' + "".join(blocs_alerte) + "</div>" if blocs_alerte else ""}

  <section>
    <h2>Carte des zones malades</h2>
    <div id="carte" role="region" aria-label="Carte de la parcelle"></div>
    <div class="legende">
      <span><i style="background:#2ea043"></i>photo saine</span>
      <span><i style="background:#e53935"></i>photo malade</span>
      <span><i class="carre" style="background:rgba(229,57,53,.55)"></i>zone malade (plus foncée = plus sûre)</span>
      {'<span><i style="background:#4a0d08"></i>détection projetée au sol</span>' if localisation == "v2" else ""}
      <span><i class="carre" style="background:transparent;border:2px solid #1b7f3b"></i>limites</span>
      <span><i class="carre" style="background:rgba(198,40,40,.3)"></i>zone interdite</span>
    </div>
    <p class="note">Localisation {_e(explication_grille)}. {"Une case est malade dès qu'une détection la recouvre ; sa fenêtre indique combien des photos qui la survolent l'ont vue malade." if localisation == "v2" else "Une zone regroupe les photos d'une même case de la grille."} Cliquer une photo
      pour voir sa vignette.</p>
  </section>

  <section>
    <h2>{_e(titre_top)}</h2>
    <div class="galerie">{top_html}</div>
  </section>

  <section>
    <h2>Images les moins sûres, à vérifier</h2>
    <p class="note">Les {len(incertaines)} images dont le score est le plus proche du seuil ({modele.seuil:.2f}),
      saines ou malades. Elles sont copiées dans <code>a_relabelliser\\</code> avec un fichier
      <code>a_relabelliser.csv</code> où noter le bon label pour le prochain entraînement.</p>
    <div class="galerie">{inc_html}</div>
  </section>

  <footer>
    <span>Pipeline d'analyse v{C.VERSION_PIPELINE} · généré le {datetime.now().strftime("%d/%m/%Y à %H:%M")}</span>
    <span>Mission : <code>{_e(mission.chemin.name)}</code> · données brutes : <code>brut\\</code> ·
      résultats : <code>resultats\\images.csv</code>, <code>detections.csv</code>, <code>zones_malades.geojson</code> ·
      déroulé : <code>journal_pipeline.txt</code></span>
  </footer>
</div>

<script>{js}</script>
<script>
const D = {_json(donnees)};
const V = {_json(vignettes)};
document.querySelectorAll("img[data-vignette]").forEach(i => {{ i.src = V[i.dataset.vignette] || ""; }});

const carte = L.map("carte", {{ zoomControl: true }});
const fonds = {{}};
for (const [nom, [url, opt]] of Object.entries(D.fonds)) fonds[nom] = L.tileLayer(url, opt);
Object.values(fonds)[0].addTo(carte);
L.control.scale({{ imperial: false }}).addTo(carte);

const terrain = L.layerGroup().addTo(carte);
const lim = L.polygon(D.limites, {{ color: "#1b7f3b", weight: 3, fillColor: "#2ea043", fillOpacity: 0.06 }}).addTo(terrain);
D.zones.forEach(z => L.polygon(z, {{ color: "#c62828", weight: 2, fillColor: "#e53935", fillOpacity: 0.3 }}).addTo(terrain));
const chemin = L.polyline(D.chemin, {{ color: "#00e5ff", weight: 2, opacity: 0.8, dashArray: "4 6" }});

function couleur(c) {{ // confiance moyenne -> opacité et teinte
  const t = Math.max(0, Math.min(1, (c - D.seuil) / Math.max(1e-6, 1 - D.seuil)));
  return {{ fillColor: t > 0.66 ? "#8e1b12" : t > 0.33 ? "#c62828" : "#ef6c00", fillOpacity: 0.35 + 0.35 * t }};
}}
const zonesMalades = L.geoJSON(D.cellules, {{
  style: f => Object.assign({{ color: "#7f1d1d", weight: 1 }}, couleur(f.properties.confiance_moyenne)),
  onEachFeature: (f, l) => {{
    const p = f.properties;
    l.bindPopup(`<strong>Zone malade</strong><br>vue malade sur ${{p.nb_malades}} des ${{p.nb_images}} photo(s) qui la couvrent` +
      (p.nb_detections ? ` · ${{p.nb_detections}} détection(s)` : "") + `<br>` +
      `confiance moyenne ${{p.confiance_moyenne.toFixed(2)}} · max ${{p.confiance_max.toFixed(2)}}<br>` +
      `<small>${{p.fichiers_malades.slice(0, 6).join(", ")}}${{p.fichiers_malades.length > 6 ? "…" : ""}}</small>`);
  }}
}}).addTo(carte);

const photos = L.layerGroup().addTo(carte);
const marqueurs = {{}};
D.photos.forEach(p => {{
  const c = p.e ? "#8a8a8a" : p.m ? "#e53935" : "#2ea043";
  const m = L.circleMarker([p.lat, p.lon], {{ radius: p.m ? 6 : 4, color: "#ffffff", weight: 1, fillColor: c, fillOpacity: 0.95 }});
  const statut = p.e ? "analyse impossible" : (p.m ? "malade" : "saine") + ` · score ${{p.s.toFixed(2)}}`;
  m.bindPopup(() => `${{V[p.f] ? `<img src="${{V[p.f]}}" alt="">` : ""}}<strong>${{p.f}}</strong><br>${{statut}}<br>` +
    `<a href="brut/images/${{encodeURIComponent(p.f)}}" target="_blank" rel="noopener">image complète</a>`, {{ maxWidth: 260 }});
  m.addTo(photos);
  marqueurs[p.f] = m;
}});

const dets = L.layerGroup();
D.detections.forEach(d => L.circleMarker([d.lat, d.lon], {{ radius: 2.5, stroke: false, fillColor: "#4a0d08", fillOpacity: 0.9 }})
  .bindTooltip(`${{d.f}} · ${{d.s.toFixed(2)}}`).addTo(dets));
const couches = {{ "Zones malades": zonesMalades }};
if (D.detections.length) {{ dets.addTo(carte); couches["Détections"] = dets; }}
Object.assign(couches, {{ "Photos": photos, "Chemin prévu": chemin, "Parcelle": terrain }});
L.control.layers(fonds, couches,
  {{ collapsed: false, position: "topright" }}).addTo(carte);
// les points de détection restent au-dessus des cases
zonesMalades.bringToBack();
carte.fitBounds(lim.getBounds().pad(0.15));

document.querySelectorAll("button.voir").forEach(b => b.addEventListener("click", () => {{
  const f = b.closest(".vig").querySelector(".nom").textContent;
  document.getElementById("carte").scrollIntoView({{ behavior: "smooth", block: "center" }});
  const m = marqueurs[f];
  if (m) {{ carte.setView(m.getLatLng(), Math.max(carte.getZoom(), 19)); m.openPopup(); }}
}}));
</script>
</body>
</html>
"""
    chemin.write_text(page, encoding="utf-8")
    return chemin
