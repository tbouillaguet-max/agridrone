"""Validation d'un dossier de run contre le standard (STANDARD.md).

Usage programmatique ::

    from ml_dashboard.validate import validate_run
    report = validate_run("runs/mon-projet/20261029_180500_effnet-b0")
    print(report.format())
    assert report.ok

Deux niveaux de problème :

* **erreur** : le dashboard ne peut pas lire le run correctement → à corriger ;
* **alerte** : le run est lisible mais incomplet ou suspect.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import yaml

from . import standard as S
from .schema_lite import load_schema, validate_instance

Level = Literal["error", "warning"]


# --------------------------------------------------------------------------- #
# Rapport
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Issue:
    """Un problème trouvé dans un run."""

    level: Level
    file: str  # chemin relatif au dossier du run, "." pour le dossier lui-même
    message: str


@dataclass
class ValidationReport:
    """Résultat de la validation d'un run."""

    run_dir: Path
    issues: list[Issue] = field(default_factory=list)
    schema_version: int | None = None

    # -- ajout --------------------------------------------------------------
    def error(self, file: str, message: str) -> None:
        self.issues.append(Issue("error", file, message))

    def warn(self, file: str, message: str) -> None:
        self.issues.append(Issue("warning", file, message))

    # -- lecture ------------------------------------------------------------
    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        """Vrai si aucune erreur (les alertes sont tolérées)."""
        return not self.errors

    def format(self) -> str:
        """Rapport lisible, en ASCII pour la console Windows."""
        head = "[OK]    " if self.ok else "[ECHEC] "
        lines = [f"{head}{self.run_dir}  ({len(self.errors)} erreur(s), {len(self.warnings)} alerte(s))"]
        for issue in self.errors + self.warnings:
            tag = "ERREUR" if issue.level == "error" else "ALERTE"
            lines.append(f"    {tag:<6}  {issue.file} : {issue.message}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_dir": str(self.run_dir),
            "ok": self.ok,
            "schema_version": self.schema_version,
            "issues": [issue.__dict__ for issue in self.issues],
        }


# --------------------------------------------------------------------------- #
# Utilitaires de lecture
# --------------------------------------------------------------------------- #
def _read_json(path: Path, report: ValidationReport, rel: str) -> Any | None:
    try:
        # UTF-8 explicite : sous Windows l'encodage par défaut est cp1252.
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.error(rel, f"JSON invalide ({exc.msg}, ligne {exc.lineno})")
    except UnicodeDecodeError:
        report.error(rel, "fichier non encodé en UTF-8")
    return None


def _read_csv(path: Path, report: ValidationReport, rel: str) -> pd.DataFrame | None:
    try:
        # dtype=str : on contrôle nous-mêmes les conversions (une classe "1"
        # doit rester la chaîne "1", pas devenir l'entier 1).
        return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    except pd.errors.EmptyDataError:
        report.error(rel, "fichier CSV vide (même l'en-tête manque)")
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        report.error(rel, f"CSV illisible : {exc}")
    return None


def _to_numeric(series: pd.Series) -> tuple[pd.Series, int]:
    """Convertit en float ; les cellules vides deviennent NaN.

    Renvoie la série convertie et le nombre de cellules non vides invalides.
    """
    stripped = series.str.strip()
    numeric = pd.to_numeric(stripped.replace("", np.nan), errors="coerce")
    bad = int((numeric.isna() & (stripped != "")).sum())
    return numeric, bad


def _schema_check(data: Any, schema_name: str, report: ValidationReport, rel: str) -> bool:
    errs = validate_instance(data, load_schema(schema_name))
    for err in errs:
        report.error(rel, err)
    return not errs


# --------------------------------------------------------------------------- #
# Contrôles par fichier
# --------------------------------------------------------------------------- #
def _check_meta(run: Path, report: ValidationReport) -> dict[str, Any] | None:
    path = run / S.META_FILE
    if not path.is_file():
        report.error(S.META_FILE, "fichier manquant")
        return None
    meta = _read_json(path, report, S.META_FILE)
    if not isinstance(meta, dict):
        if meta is not None:
            report.error(S.META_FILE, "doit contenir un objet JSON")
        return None

    version = meta.get("schema_version")
    report.schema_version = version if isinstance(version, int) else None
    if isinstance(version, int) and version not in S.SUPPORTED_SCHEMA_VERSIONS:
        newer = version > max(S.SUPPORTED_SCHEMA_VERSIONS)
        hint = " : mets à jour ml_dashboard" if newer else ""
        report.error(S.META_FILE, f"schema_version {version} non pris en charge{hint}")
        return None

    if not _schema_check(meta, "meta", report, S.META_FILE):
        # On renvoie quand même meta si les champs structurants sont lisibles,
        # pour pouvoir contrôler le reste du run.
        if meta.get("task") not in S.TASKS:
            return None

    if meta.get("run_id") != run.name:
        report.error(S.META_FILE, f"run_id {meta.get('run_id')!r} différent du nom du dossier {run.name!r}")
    if meta.get("project") != run.parent.name:
        report.warn(S.META_FILE, f"project {meta.get('project')!r} différent du dossier parent {run.parent.name!r}")
    if meta.get("status") == "completed":
        if meta.get("ended_at") is None or meta.get("duration_s") is None:
            report.warn(S.META_FILE, "run terminé sans ended_at/duration_s")
    return meta


def _check_config(run: Path, report: ValidationReport) -> None:
    path = run / S.CONFIG_FILE
    if not path.is_file():
        report.error(S.CONFIG_FILE, "fichier manquant")
        return
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        report.error(S.CONFIG_FILE, f"YAML invalide : {exc}")
        return
    except UnicodeDecodeError:
        report.error(S.CONFIG_FILE, "fichier non encodé en UTF-8")
        return
    if cfg is None:
        report.warn(S.CONFIG_FILE, "fichier vide : aucun hyperparamètre enregistré")
    elif not isinstance(cfg, dict):
        report.error(S.CONFIG_FILE, "doit contenir un dictionnaire (clé: valeur) à la racine")


@dataclass(frozen=True)
class ClassesInfo:
    """Contenu utile de classes.json pour les autres contrôles."""

    classes: list[str]
    label_mode: str  # "single" | "multi"


def _check_classes(run: Path, report: ValidationReport, task: str | None) -> ClassesInfo | None:
    path = run / S.CLASSES_FILE
    if not path.is_file():
        report.error(S.CLASSES_FILE, "fichier manquant")
        return None
    data = _read_json(path, report, S.CLASSES_FILE)
    if data is None or not _schema_check(data, "classes", report, S.CLASSES_FILE):
        return None
    classes: list[str] = data["classes"]
    positive = data["positive_class"]
    mode: str = data["label_mode"]
    if task in S.DETECTION_TASKS and mode != "single":
        report.error(S.CLASSES_FILE, "label_mode 'multi' réservé à la classification")
    if task == "classification" and mode == "single" and len(classes) < 2:
        report.error(S.CLASSES_FILE, "une classification mono-label exige au moins 2 classes")
    if positive is not None:
        if mode == "multi":
            report.error(S.CLASSES_FILE, "positive_class doit valoir null en multi-label")
        elif len(classes) != 2:
            report.error(S.CLASSES_FILE, "positive_class n'a de sens qu'avec exactement 2 classes")
        elif positive not in classes:
            report.error(S.CLASSES_FILE, f"positive_class {positive!r} absente de classes")
    elif task == "classification" and mode == "single" and len(classes) == 2:
        report.warn(S.CLASSES_FILE, f"binaire sans positive_class : le dashboard prendra {classes[1]!r}")
    return ClassesInfo(classes, mode)


def _check_epochs(run: Path, report: ValidationReport, status: str | None) -> None:
    rel = S.EPOCHS_FILE
    path = run / rel
    if not path.is_file():
        report.error(rel, "fichier manquant")
        return
    df = _read_csv(path, report, rel)
    if df is None:
        return

    missing = [c for c in S.EPOCHS_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        report.error(rel, f"colonnes obligatoires manquantes : {missing}")
    extra = [c for c in df.columns if c not in S.EPOCHS_REQUIRED_COLUMNS]
    bad_names = [c for c in extra if not S.EPOCH_METRIC_PATTERN.match(c)]
    if bad_names:
        report.error(rel, f"colonnes non conformes (attendu train_*/val_* en minuscules) : {bad_names}")
    if len(set(df.columns)) != len(df.columns):
        report.error(rel, "colonnes en double")

    if df.empty:
        if status == "completed":
            report.error(rel, "run terminé mais aucune époque enregistrée")
        return

    for col in df.columns:
        values, bad = _to_numeric(df[col])
        if bad:
            report.error(rel, f"colonne {col!r} : {bad} valeur(s) non numérique(s)")
        if col == "epoch":
            if values.isna().any():
                report.error(rel, "colonne 'epoch' : valeurs vides")
            elif not (values % 1 == 0).all() or (values < 0).any():
                report.error(rel, "colonne 'epoch' : entiers positifs attendus")
            elif not values.is_monotonic_increasing or values.duplicated().any():
                report.error(rel, "colonne 'epoch' : doit être strictement croissante")
        elif col == "lr" and (values < 0).any():
            report.error(rel, "colonne 'lr' : valeurs négatives")
        elif col == "val_loss" and values.isna().all():
            report.warn(rel, "val_loss entièrement vide : pas de courbe de validation")


def _check_predictions(
    run: Path, report: ValidationReport, task: str | None, status: str | None, info: ClassesInfo | None
) -> None:
    pdir = run / S.PREDICTIONS_DIR
    if task in S.DETECTION_TASKS:
        if pdir.exists():
            report.warn(S.PREDICTIONS_DIR, "ignoré pour une tâche de détection/segmentation en schema_version 1")
        return
    if not pdir.is_dir():
        if status == "completed":
            report.error(S.PREDICTIONS_DIR, "dossier manquant : val.csv est obligatoire pour un run terminé")
        return

    for entry in sorted(pdir.iterdir()):
        if entry.is_file() and entry.suffix == ".csv" and entry.stem in S.SPLITS:
            continue
        report.error(f"{S.PREDICTIONS_DIR}/{entry.name}", "seuls val.csv et test.csv sont autorisés")

    if status == "completed" and not (pdir / "val.csv").is_file():
        report.error(f"{S.PREDICTIONS_DIR}/val.csv", "fichier manquant pour un run terminé")
    if (pdir / "test.csv").is_file() and status != "completed":
        report.error(
            f"{S.PREDICTIONS_DIR}/test.csv",
            "le test ne s'écrit qu'en fin de run : statut 'completed' attendu",
        )

    for split in S.SPLITS:
        path = pdir / f"{split}.csv"
        if path.is_file():
            _check_prediction_file(path, f"{S.PREDICTIONS_DIR}/{split}.csv", report, info)


def _check_prediction_file(path: Path, rel: str, report: ValidationReport, info: ClassesInfo | None) -> None:
    df = _read_csv(path, report, rel)
    if df is None:
        return
    missing = [c for c in S.PREDICTION_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        report.error(rel, f"colonnes obligatoires manquantes : {missing}")
        return
    if df.empty:
        report.error(rel, "aucune prédiction")
        return

    ids = df["id"].str.strip()
    if (ids == "").any():
        report.error(rel, "identifiants vides dans 'id'")
    if ids.duplicated().any():
        report.error(rel, f"{int(ids.duplicated().sum())} identifiant(s) en double dans 'id'")

    if info is None:
        report.warn(rel, "classes.json illisible : contrôle des classes et probabilités sauté")
        return
    classes = info.classes

    proba_cols = [S.proba_column(c) for c in classes]
    missing_p = [c for c in proba_cols if c not in df.columns]
    if missing_p:
        report.error(rel, f"colonnes de probabilité manquantes : {missing_p}")
        return
    known = set(S.PREDICTION_REQUIRED_COLUMNS) | set(proba_cols)
    unknown = [c for c in df.columns if c not in known]
    stray = [c for c in unknown if c.startswith(S.PROBA_PREFIX)]
    if stray:
        report.error(rel, f"probabilités de classes absentes de classes.json : {stray}")
    others = [c for c in unknown if c not in stray]
    if others:
        report.warn(rel, f"colonnes supplémentaires ignorées par le dashboard : {others}")

    for col in ("y_true", "y_pred"):
        if info.label_mode == "multi":
            cells = [S.split_labels(v) for v in df[col]]
            used = {c for labels in cells for c in labels}
            if any(len(labels) != len(set(labels)) for labels in cells):
                report.error(rel, f"{col} : classe répétée dans une même cellule")
        else:
            used = set(df[col])
        bad = sorted(used - set(classes))
        if bad:
            report.error(rel, f"{col} contient des classes inconnues : {bad[:5]}")

    probas = pd.DataFrame({c: _to_numeric(df[c])[0] for c in proba_cols})
    if probas.isna().any().any():
        report.error(rel, "probabilités vides ou non numériques")
        return
    if ((probas < 0) | (probas > 1)).any().any():
        report.error(rel, "probabilités hors de [0, 1]")
        return
    if info.label_mode == "multi":
        # Probas indépendantes : pas de contrainte de somme. On vérifie que
        # y_pred correspond au seuil par défaut, à titre indicatif.
        thr = S.DEFAULT_MULTI_LABEL_THRESHOLD
        expected = [
            {c for c in classes if probas.at[i, S.proba_column(c)] >= thr} for i in probas.index
        ]
        actual = [set(S.split_labels(v)) for v in df["y_pred"]]
        mismatch = sum(e != a for e, a in zip(expected, actual))
        if mismatch:
            report.warn(rel, f"{mismatch} ligne(s) où y_pred ne correspond pas au seuil {thr} (seuils réglés ?)")
        return

    sums = probas.sum(axis=1)
    off = int(((sums - 1).abs() > S.PROBA_SUM_TOLERANCE).sum())
    if off:
        report.error(
            rel, f"{off} ligne(s) dont les probabilités ne somment pas à 1 (label_mode 'single')"
        )

    argmax = probas.to_numpy().argmax(axis=1)
    pred_idx = df["y_pred"].map({c: i for i, c in enumerate(classes)})
    mismatch = int((pred_idx.notna() & (pred_idx != argmax)).sum())
    if mismatch:
        report.warn(rel, f"{mismatch} ligne(s) où y_pred n'est pas la classe de proba maximale (seuil réglé ?)")


def _check_detection(run: Path, report: ValidationReport, task: str | None, status: str | None,
                     info: ClassesInfo | None) -> None:
    ddir = run / S.DETECTION_DIR
    if task == "classification":
        if ddir.exists():
            report.warn(S.DETECTION_DIR, "ignoré pour une tâche de classification")
        return
    if task not in S.DETECTION_TASKS:
        return

    classes = info.classes if info else None
    rel = f"{S.DETECTION_DIR}/{S.DETECTION_METRICS_FILE}"
    mpath = ddir / S.DETECTION_METRICS_FILE
    if not mpath.is_file():
        if status == "completed":
            report.error(rel, "fichier manquant pour un run de détection terminé")
    else:
        data = _read_json(mpath, report, rel)
        if data is not None and _schema_check(data, "detection_metrics", report, rel):
            if task == "segmentation" and not data.get("mask"):
                report.warn(rel, "segmentation sans métriques 'mask'")
            if classes is not None:
                unknown = sorted({pc["class"] for pc in data["per_class"]} - set(classes))
                if unknown:
                    report.error(rel, f"per_class contient des classes inconnues : {unknown[:5]}")

    pr = ddir / S.DETECTION_PR_FILE
    if pr.is_file():
        prel = f"{S.DETECTION_DIR}/{S.DETECTION_PR_FILE}"
        df = _read_csv(pr, report, prel)
        if df is not None:
            missing = [c for c in ("class", "recall", "precision") if c not in df.columns]
            if missing:
                report.error(prel, f"colonnes obligatoires manquantes : {missing}")
            else:
                for col in ("recall", "precision"):
                    vals, bad = _to_numeric(df[col])
                    if bad or ((vals < 0) | (vals > 1)).any():
                        report.error(prel, f"colonne {col!r} : nombres dans [0, 1] attendus")
                if classes is not None:
                    unknown = sorted(set(df["class"]) - set(classes) - {"all"})
                    if unknown:
                        report.error(prel, f"classes inconnues : {unknown[:5]}")


def _check_manifest_dir(run: Path, report: ValidationReport, dirname: str, allowed_ext: frozenset[str],
                        manifest_required: bool) -> None:
    """Contrôle artifacts/ ou extra_results/ et leur manifest.json."""
    d = run / dirname
    if not d.is_dir():
        return
    files = {p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file() and p.name != S.MANIFEST_FILE}
    for f in sorted(files):
        if Path(f).suffix.lower() not in allowed_ext:
            report.warn(f"{dirname}/{f}", "extension non prise en charge par le dashboard")

    mpath = d / S.MANIFEST_FILE
    rel = f"{dirname}/{S.MANIFEST_FILE}"
    if not mpath.is_file():
        if files and manifest_required:
            report.error(rel, "fichier manquant (titre et description de chaque fichier)")
        return
    data = _read_json(mpath, report, rel)
    if data is None or not _schema_check(data, "manifest", report, rel):
        return
    listed: set[str] = set()
    for item in data["items"]:
        f = item["file"]
        target = (d / f).resolve()
        if d.resolve() not in target.parents:
            report.error(rel, f"{f!r} sort du dossier {dirname}/")
        elif f not in files:
            report.error(rel, f"{f!r} référencé mais absent")
        listed.add(f)
    unlisted = sorted(files - listed)
    if unlisted:
        report.warn(rel, f"fichiers non décrits dans le manifest : {unlisted[:5]}")


def _check_model(run: Path, report: ValidationReport, status: str | None) -> None:
    mdir = run / S.MODEL_DIR
    has_files = mdir.is_dir() and any(p.is_file() for p in mdir.rglob("*"))
    if status == "completed" and not has_files:
        report.warn(S.MODEL_DIR, "aucun checkpoint enregistré")


def _check_layout(run: Path, report: ValidationReport) -> None:
    for entry in sorted(run.iterdir()):
        if entry.name not in S.TOP_LEVEL_ENTRIES and not entry.name.startswith("."):
            report.warn(entry.name, "élément non prévu par le standard (ignoré)")


# --------------------------------------------------------------------------- #
# Points d'entrée
# --------------------------------------------------------------------------- #
def validate_run(run_dir: str | Path) -> ValidationReport:
    """Valide un dossier de run et renvoie un rapport détaillé."""
    run = Path(run_dir).expanduser().resolve()
    report = ValidationReport(run_dir=run)
    if not run.is_dir():
        report.error(".", "dossier introuvable")
        return report

    meta = _check_meta(run, report)
    if report.schema_version is not None and report.schema_version not in S.SUPPORTED_SCHEMA_VERSIONS:
        return report  # version inconnue : inutile de contrôler le reste

    task = meta.get("task") if meta else None
    status = meta.get("status") if meta else None

    _check_layout(run, report)
    _check_config(run, report)
    info = _check_classes(run, report, task)
    _check_epochs(run, report, status)
    _check_predictions(run, report, task, status, info)
    _check_detection(run, report, task, status, info)
    _check_manifest_dir(run, report, S.ARTIFACTS_DIR, S.IMAGE_EXTENSIONS | S.HTML_EXTENSIONS, True)
    _check_manifest_dir(run, report, S.EXTRA_RESULTS_DIR, frozenset({".csv"}), False)
    _check_model(run, report, status)
    return report


def find_runs(root: str | Path) -> list[Path]:
    """Liste les dossiers de run (contenant un meta.json) sous ``root``.

    ``root`` peut être un run, un dossier de projet ou le dossier central.
    """
    root = Path(root).expanduser().resolve()
    if (root / S.META_FILE).is_file():
        return [root]
    return sorted(p.parent for p in root.rglob(S.META_FILE))
