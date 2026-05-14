# filename: backend/core/evaluation.py
# purpose: Model benchmarking utilities — confusion matrix, ROC, AUC,
#          precision/recall/F1, calibration curve data
# governed by: §3.1, §10 (charts: confusion matrix, ROC, precision-recall,
#              calibration curve before/after)

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    confusion_matrix,
    roc_curve,
    auc,
    precision_recall_curve,
    classification_report,
)
from sklearn.calibration import calibration_curve


def evaluate(
    model: object,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """
    Compute confusion matrix and ROC-AUC for a fitted model.
    Supports any model with predict() and predict_proba() — including
    CalibratedClassifierCV wrapper (§6.3).

    Returns:
        cm:      confusion matrix (ndarray)
        fpr:     false positive rates (ndarray)
        tpr:     true positive rates (ndarray)
        roc_auc: AUC scalar (float)
    """
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    cm = confusion_matrix(y_test, y_pred)
    fpr, tpr, _ = roc_curve(y_test, y_prob)
    roc_auc = auc(fpr, tpr)

    return cm, fpr, tpr, roc_auc


def evaluate_full(
    model: object,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> dict:
    """
    Extended evaluation — returns all metrics needed for §10 report charts.

    Returns a dict with:
        cm:               confusion matrix
        fpr / tpr:        ROC curve arrays
        roc_auc:          AUC scalar
        precision_curve:  precision array (for precision-recall chart)
        recall_curve:     recall array (for precision-recall chart)
        pr_auc:           area under precision-recall curve
        report:           per-class precision, recall, F1 as dict
        prob_true:        calibration curve — fraction of positives per bin
        prob_pred:        calibration curve — mean predicted probability per bin
    """
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    cm = confusion_matrix(y_test, y_pred)

    fpr, tpr, _ = roc_curve(y_test, y_prob)
    roc_auc = auc(fpr, tpr)

    precision_curve, recall_curve, _ = precision_recall_curve(y_test, y_prob)
    pr_auc = auc(recall_curve, precision_curve)

    report = classification_report(
        y_test, y_pred,
        target_names=["BENIGN", "ATTACK"],
        output_dict=True,
    )

    prob_true, prob_pred = calibration_curve(y_test, y_prob, n_bins=10)

    return {
        "cm": cm,
        "fpr": fpr,
        "tpr": tpr,
        "roc_auc": round(float(roc_auc), 4),
        "precision_curve": precision_curve,
        "recall_curve": recall_curve,
        "pr_auc": round(float(pr_auc), 4),
        "report": report,
        "prob_true": prob_true,
        "prob_pred": prob_pred,
    }
