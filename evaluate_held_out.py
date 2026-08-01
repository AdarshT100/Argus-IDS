from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, f1_score


RANDOM_STATE: Final[int] = 42
BOOTSTRAP_ITERATIONS: Final[int] = 1_000
LABEL_COL: Final[str] = "Label"
DROP_COLS: Final[set[str]] = {"Flow ID", "Source IP", "Destination IP", "Timestamp"}
LOW_CONFIDENCE_THRESHOLD: Final[float] = 0.6

LABEL_TO_CLASS: Final[dict[str, str]] = {
    "benign": "BENIGN",
    "dos hulk": "DoS",
    "dos goldeneye": "DoS",
    "dos slowloris": "DoS",
    "dos slowhttptest": "DoS",
    "ddos": "DDoS",
    "portscan": "PortScan",
    "ftp-patator": "BruteForce",
    "ssh-patator": "BruteForce",
    "web attack - brute force": "BruteForce",
    "web attack - xss": "WebAttack",
    "web attack - sql injection": "WebAttack",
    "infiltration": "Infiltration",
    "bot": "Infiltration",
    "heartbleed": "Infiltration",
}


def configure_logging() -> None:
    """Configure process-wide logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the trained binary ensemble and Isolation Forest on "
            "Dataset/held_out_eval.csv."
        )
    )
    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=BOOTSTRAP_ITERATIONS,
        help="Number of bootstrap resamples used for 95%% confidence intervals.",
    )
    parser.add_argument(
        "--low-confidence-threshold",
        type=float,
        default=LOW_CONFIDENCE_THRESHOLD,
        help="Ensemble confidence threshold below which predictions are flagged.",
    )
    return parser.parse_args()


def model_path(model_dir: Path, filename: str) -> Path:
    """Return the path to a model artifact."""
    return model_dir / filename


def load_required_artifact(model_dir: Path, filename: str) -> object:
    """Load a required joblib artifact or raise a clear error."""
    path = model_path(model_dir, filename)
    if not path.exists():
        raise FileNotFoundError(f"Required model artifact not found: {path}")
    return joblib.load(path)


def load_optional_artifact(model_dir: Path, filename: str) -> object | None:
    """Load an optional joblib artifact when present."""
    path = model_path(model_dir, filename)
    return joblib.load(path) if path.exists() else None


def normalise_label(value: object) -> str:
    """Normalise CICIDS2017 label text for case-insensitive class matching."""
    label = str(value).strip()
    label = label.replace("\u2013", "-").replace("\u2014", "-").replace("\ufffd", "-")
    return " ".join(label.lower().split())


def map_eval_label(value: object) -> str:
    """Map a raw CICIDS2017 label to the held-out evaluation class."""
    normalized = normalise_label(value)
    if normalized not in LABEL_TO_CLASS:
        raise ValueError(f"Unsupported held-out label: {value!r}")
    return LABEL_TO_CLASS[normalized]


def load_held_out_csv(held_out_path: Path) -> pd.DataFrame:
    """Load and clean the frozen held-out evaluation CSV."""
    if not held_out_path.exists():
        raise FileNotFoundError(
            f"Held-out evaluation CSV not found: {held_out_path}. "
            "Run create_held_out_eval.py first."
        )

    df = pd.read_csv(held_out_path)
    df.columns = df.columns.str.strip()

    if LABEL_COL not in df.columns:
        raise ValueError(f"'{LABEL_COL}' column not found in {held_out_path}.")

    df.drop(columns=[col for col in DROP_COLS if col in df.columns], inplace=True)
    df.dropna(subset=[LABEL_COL], inplace=True)
    return df.reset_index(drop=True)


def prepare_features(
    df: pd.DataFrame,
    raw_feature_names: list[str],
    model_feature_names: list[str],
    scaler: object,
    pca: object | None,
) -> pd.DataFrame:
    """Align raw features, fill missing values with zero, then scale and project."""
    expected_features = set(raw_feature_names)
    missing_features = [feature for feature in raw_feature_names if feature not in df.columns]
    extra_features = [
        feature
        for feature in df.columns
        if feature not in expected_features and feature != LABEL_COL
    ]

    if missing_features:
        logging.warning(
            "Held-out CSV is missing %s training feature(s); filling with zero.",
            len(missing_features),
        )
    if extra_features:
        logging.info(
            "Ignoring %s held-out feature(s) not present in the training schema.",
            len(extra_features),
        )

    raw_features = df.reindex(columns=raw_feature_names, fill_value=0.0)
    raw_features.replace([np.inf, -np.inf], np.nan, inplace=True)
    nan_count = int(raw_features.isna().sum().sum())
    if nan_count:
        logging.warning(
            "Held-out model feature matrix contains %s NaN/inf value(s); filling with zero.",
            nan_count,
        )
        raw_features.fillna(0.0, inplace=True)

    scaled = scaler.transform(raw_features)

    if pca is not None:
        scaled = pca.transform(scaled)

    return pd.DataFrame(scaled, columns=model_feature_names)


def confidence_interval(values: np.ndarray) -> dict[str, float]:
    """Return a percentile 95% confidence interval for bootstrap values."""
    lower, upper = np.percentile(values, [2.5, 97.5])
    return {
        "lower": float(lower),
        "upper": float(upper),
    }


def bootstrap_metric_summary(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    iterations: int,
    random_state: int = RANDOM_STATE,
) -> dict[str, object]:
    """Compute bootstrap CIs for accuracy, macro F1, and per-class metrics."""
    if iterations <= 0:
        raise ValueError("bootstrap iterations must be greater than zero.")

    rng = np.random.default_rng(random_state)
    n_rows = len(y_true)

    accuracy_values: list[float] = []
    macro_f1_values: list[float] = []
    class_metric_values: dict[str, dict[str, list[float]]] = {
        "BENIGN": {"precision": [], "recall": [], "f1-score": []},
        "ATTACK": {"precision": [], "recall": [], "f1-score": []},
    }

    for _ in range(iterations):
        sample_idx = rng.integers(0, n_rows, size=n_rows)
        sample_true = y_true[sample_idx]
        sample_pred = y_pred[sample_idx]

        accuracy_values.append(float(accuracy_score(sample_true, sample_pred)))
        macro_f1_values.append(
            float(f1_score(sample_true, sample_pred, average="macro", zero_division=0))
        )

        report = classification_report(
            sample_true,
            sample_pred,
            labels=[0, 1],
            target_names=["BENIGN", "ATTACK"],
            output_dict=True,
            zero_division=0,
        )
        for class_name in ("BENIGN", "ATTACK"):
            for metric_name in ("precision", "recall", "f1-score"):
                class_metric_values[class_name][metric_name].append(
                    float(report[class_name][metric_name])
                )

    per_class_ci = {
        class_name: {
            metric_name: confidence_interval(np.asarray(values))
            for metric_name, values in metrics.items()
        }
        for class_name, metrics in class_metric_values.items()
    }

    return {
        "iterations": iterations,
        "random_state": random_state,
        "accuracy": confidence_interval(np.asarray(accuracy_values)),
        "macro_f1": confidence_interval(np.asarray(macro_f1_values)),
        "per_class": per_class_ci,
    }


def summarize_low_confidence(
    y_true: np.ndarray,
    confidences: np.ndarray,
    threshold: float,
) -> dict[str, object]:
    """Summarize predictions below the configured confidence threshold."""
    mask = confidences < threshold
    low_confidence_count = int(mask.sum())
    total = int(len(confidences))

    return {
        "threshold": float(threshold),
        "count": low_confidence_count,
        "rate": float(low_confidence_count / total) if total else 0.0,
        "by_true_label": {
            "BENIGN": int(np.logical_and(mask, y_true == 0).sum()),
            "ATTACK": int(np.logical_and(mask, y_true == 1).sum()),
        },
    }


def summarize_anomalies(
    y_true: np.ndarray,
    eval_labels: pd.Series,
    iso_labels: np.ndarray,
) -> dict[str, object]:
    """Summarize Isolation Forest anomaly labels overall and by class."""
    anomaly_mask = iso_labels == -1
    total = int(len(iso_labels))

    by_eval_class = {}
    for eval_class in sorted(eval_labels.unique()):
        class_mask = eval_labels.to_numpy() == eval_class
        class_total = int(class_mask.sum())
        class_anomalies = int(np.logical_and(anomaly_mask, class_mask).sum())
        by_eval_class[eval_class] = {
            "count": class_anomalies,
            "total": class_total,
            "rate": float(class_anomalies / class_total) if class_total else 0.0,
        }

    return {
        "count": int(anomaly_mask.sum()),
        "total": total,
        "rate": float(anomaly_mask.sum() / total) if total else 0.0,
        "by_true_label": {
            "BENIGN": int(np.logical_and(anomaly_mask, y_true == 0).sum()),
            "ATTACK": int(np.logical_and(anomaly_mask, y_true == 1).sum()),
        },
        "by_eval_class": by_eval_class,
    }


def summarize_detection_overlap(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    eval_labels: pd.Series,
    iso_labels: np.ndarray,
) -> dict[str, object]:
    """Measure whether anomaly detection catches binary-model misses."""
    anomaly_mask = iso_labels == -1
    false_negative_mask = np.logical_and(y_true == 1, y_pred == 0)
    true_positive_mask = np.logical_and(y_true == 1, y_pred == 1)
    false_positive_mask = np.logical_and(y_true == 0, y_pred == 1)
    true_negative_mask = np.logical_and(y_true == 0, y_pred == 0)

    false_negative_count = int(false_negative_mask.sum())
    false_negatives_anomalous = int(np.logical_and(false_negative_mask, anomaly_mask).sum())

    by_eval_class = {}
    eval_label_values = eval_labels.to_numpy()
    for eval_class in sorted(eval_labels.unique()):
        class_mask = eval_label_values == eval_class
        class_fn_mask = np.logical_and(false_negative_mask, class_mask)
        class_fn_count = int(class_fn_mask.sum())
        class_fn_anomalous = int(np.logical_and(class_fn_mask, anomaly_mask).sum())

        by_eval_class[eval_class] = {
            "false_negatives": class_fn_count,
            "false_negatives_anomaly_flagged": class_fn_anomalous,
            "false_negative_anomaly_coverage": (
                float(class_fn_anomalous / class_fn_count) if class_fn_count else 0.0
            ),
        }

    return {
        "confusion_counts": {
            "true_positive": int(true_positive_mask.sum()),
            "false_negative": false_negative_count,
            "false_positive": int(false_positive_mask.sum()),
            "true_negative": int(true_negative_mask.sum()),
        },
        "false_negative_anomaly_overlap": {
            "false_negatives": false_negative_count,
            "anomaly_flagged": false_negatives_anomalous,
            "coverage": (
                float(false_negatives_anomalous / false_negative_count)
                if false_negative_count
                else 0.0
            ),
        },
        "by_eval_class": by_eval_class,
    }


def build_results(
    held_out_path: Path,
    model_dir: Path,
    df: pd.DataFrame,
    eval_labels: pd.Series,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_proba: np.ndarray,
    iso_labels: np.ndarray,
    iso_scores: np.ndarray,
    bootstrap_iterations: int,
    low_confidence_threshold: float,
    raw_feature_names: list[str],
    model_feature_names: list[str],
    pca_enabled: bool,
) -> dict[str, object]:
    """Build the JSON-serializable evaluation result payload."""
    confidences = np.max(y_proba, axis=1)
    report = classification_report(
        y_true,
        y_pred,
        labels=[0, 1],
        target_names=["BENIGN", "ATTACK"],
        output_dict=True,
        zero_division=0,
    )
    report_text = classification_report(
        y_true,
        y_pred,
        labels=[0, 1],
        target_names=["BENIGN", "ATTACK"],
        zero_division=0,
    )

    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "held_out_path": str(held_out_path),
        "model_dir": str(model_dir),
        "row_count": int(len(df)),
        "feature_schema": {
            "raw_feature_count": int(len(raw_feature_names)),
            "model_feature_count": int(len(model_feature_names)),
            "pca_enabled": pca_enabled,
        },
        "class_counts": {
            str(class_name): int(count)
            for class_name, count in eval_labels.value_counts().sort_index().items()
        },
        "binary_class_counts": {
            "BENIGN": int((y_true == 0).sum()),
            "ATTACK": int((y_true == 1).sum()),
        },
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "classification_report": report,
        "bootstrap_ci": bootstrap_metric_summary(
            y_true=y_true,
            y_pred=y_pred,
            iterations=bootstrap_iterations,
        ),
        "low_confidence_predictions": summarize_low_confidence(
            y_true=y_true,
            confidences=confidences,
            threshold=low_confidence_threshold,
        ),
        "isolation_forest": {
            **summarize_anomalies(
                y_true=y_true,
                eval_labels=eval_labels,
                iso_labels=iso_labels,
            ),
            "score_summary": {
                "min": float(np.min(iso_scores)),
                "mean": float(np.mean(iso_scores)),
                "median": float(np.median(iso_scores)),
                "max": float(np.max(iso_scores)),
            },
        },
        "detection_overlap": summarize_detection_overlap(
            y_true=y_true,
            y_pred=y_pred,
            eval_labels=eval_labels,
            iso_labels=iso_labels,
        ),
        "text_report": report_text,
    }


def write_results(results: dict[str, object], output_path: Path) -> None:
    """Persist the evaluation result JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(results, file, indent=2)
        file.write("\n")


def main() -> int:
    """Evaluate the frozen held-out split with the production binary pipeline."""
    configure_logging()
    args = parse_args()

    data_dir = Path(os.environ.get("ARGUS_DATA_DIR", "./Dataset"))
    model_dir = Path(os.environ.get("ARGUS_MODEL_DIR", "backend/model"))
    held_out_path = data_dir / "held_out_eval.csv"
    output_path = model_dir / "held_out_eval_results.json"

    logging.info("Loading held-out CSV from %s", held_out_path)
    df = load_held_out_csv(held_out_path)
    eval_labels = df[LABEL_COL].map(map_eval_label)
    y_true = eval_labels.map(lambda label: 0 if label == "BENIGN" else 1).to_numpy()

    logging.info("Loading binary ensemble, scaler, feature list, and Isolation Forest")
    ensemble = load_required_artifact(model_dir, "ensemble_model.pkl")
    scaler = load_required_artifact(model_dir, "scaler.pkl")
    iso_forest = load_required_artifact(model_dir, "iso_forest.pkl")
    raw_feature_names = list(load_required_artifact(model_dir, "rf_features.pkl"))
    model_feature_names = list(
        load_optional_artifact(model_dir, "model_features.pkl") or raw_feature_names
    )

    metadata_path = model_dir / "metadata.json"
    pca_enabled = False
    if metadata_path.exists():
        with metadata_path.open("r", encoding="utf-8") as file:
            metadata = json.load(file)
        pca_enabled = bool(metadata.get("ARGUS_USE_PCA"))

    pca = load_optional_artifact(model_dir, "pca.pkl") if pca_enabled else None
    if pca_enabled and pca is None:
        raise FileNotFoundError("metadata.json indicates PCA was used, but pca.pkl is missing.")

    logging.info("Preparing %s held-out rows for inference", len(df))
    X_eval = prepare_features(
        df=df,
        raw_feature_names=raw_feature_names,
        model_feature_names=model_feature_names,
        scaler=scaler,
        pca=pca,
    )

    logging.info("Running calibrated binary ensemble")
    y_proba = ensemble.predict_proba(X_eval)
    y_pred = np.argmax(y_proba, axis=1).astype(int)

    logging.info("Running Isolation Forest anomaly layer")
    iso_labels = iso_forest.predict(X_eval)
    iso_scores = iso_forest.score_samples(X_eval)

    results = build_results(
        held_out_path=held_out_path,
        model_dir=model_dir,
        df=df,
        eval_labels=eval_labels,
        y_true=y_true,
        y_pred=y_pred,
        y_proba=y_proba,
        iso_labels=iso_labels,
        iso_scores=iso_scores,
        bootstrap_iterations=args.bootstrap_iterations,
        low_confidence_threshold=args.low_confidence_threshold,
        raw_feature_names=raw_feature_names,
        model_feature_names=model_feature_names,
        pca_enabled=pca_enabled,
    )
    write_results(results, output_path)

    logging.info("Accuracy: %.4f", results["accuracy"])
    logging.info("Macro F1: %.4f", results["macro_f1"])
    logging.info(
        "95%% CI accuracy: [%.4f, %.4f]",
        results["bootstrap_ci"]["accuracy"]["lower"],
        results["bootstrap_ci"]["accuracy"]["upper"],
    )
    logging.info(
        "Isolation Forest anomaly rate: %.4f",
        results["isolation_forest"]["rate"],
    )
    logging.info(
        "Low-confidence prediction rate: %.4f",
        results["low_confidence_predictions"]["rate"],
    )
    logging.info(
        "False-negative anomaly coverage: %.4f",
        results["detection_overlap"]["false_negative_anomaly_overlap"]["coverage"],
    )
    print("\n[classification_report]")
    print(results["text_report"])
    print(f"[save] held-out evaluation results -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
