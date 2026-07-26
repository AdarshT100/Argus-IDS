# filename: backend/services/shap_explainer.py
# purpose: SHAP explainability — TreeExplainer wrapper, impact DataFrame, explanation text


from __future__ import annotations

import numpy as np
import pandas as pd
import shap


def create_explainer(model: object) -> shap.TreeExplainer:
    """
    Instantiate a SHAP TreeExplainer for the given tree-based model.

    Unwrap chain: CalibratedClassifierCV → VotingClassifier → RF estimator.
    TreeExplainer requires a single tree model — VotingClassifier is not
    supported. We extract the RF named estimator from the voting ensemble
    because RF SHAP values are valid feature attributions for the ensemble
    (both members are tree-based and trained on the same feature space).
    """
    base_model = model

    # Layer 1: unwrap CalibratedClassifierCV
    if hasattr(base_model, "estimator"):
        base_model = base_model.estimator

    # Layer 2: unwrap VotingClassifier — extract the RF named estimator
    if hasattr(base_model, "named_estimators_"):
        base_model = base_model.named_estimators_["rf"]

    return shap.TreeExplainer(base_model)


def generate_shap_analysis(
    explainer: shap.TreeExplainer,
    packet_df: pd.DataFrame,
    feature_names: list[str],
    prediction: int,
    top_n: int = 5,
) -> tuple[np.ndarray, str]:
    """
    Compute SHAP values for a single packet and build a human-readable explanation.

    Args:
        explainer:     fitted TreeExplainer
        packet_df:     single-row DataFrame of packet features
        feature_names: ordered list of feature names
        prediction:    0 = benign, 1 = attack
        top_n:         number of top features to include in explanation

    Returns:
        shap_vector:      1-D array of per-feature SHAP values
        explanation_text: plain-text summary of top drivers
    """
    shap_output = explainer(packet_df)

    if len(shap_output.values.shape) == 3:
        shap_vector: np.ndarray = shap_output.values[0, :, 1]
    else:
        shap_vector = shap_output.values[0]

    impact_df = pd.DataFrame({
        "Feature": feature_names,
        "Impact": shap_vector,
        "Actual Value": packet_df.iloc[0].values,
    })
    impact_df["AbsImpact"] = impact_df["Impact"].abs()
    impact_df = impact_df.sort_values(by="AbsImpact", ascending=False)
    top_impacts = impact_df.head(top_n)

    explanation_text = _build_explanation_text(top_impacts, prediction)
    return shap_vector, explanation_text


def get_top_shap_features(
    feature_names: list[str],
    shap_vector: np.ndarray,
    top_n: int = 3,
) -> list[dict[str, float]]:
    """
    Return the top-n SHAP features as a list of dicts matching the /predict
    response schema (§4).
    """
    impact_df = pd.DataFrame({"feature": feature_names, "impact": shap_vector})
    impact_df["abs"] = impact_df["impact"].abs()
    top = impact_df.nlargest(top_n, "abs")
    return top[["feature", "impact"]].to_dict(orient="records")


def _categorize_feature(feature_name: str) -> str:
    """Map a raw feature name to a human-readable category. Ported from prototype."""
    if "Packets" in feature_name or "Bytes" in feature_name:
        return "Traffic Volume"
    elif "Length" in feature_name or "Segment" in feature_name:
        return "Packet Size Characteristics"
    elif "IAT" in feature_name:
        return "Timing Behavior"
    elif "Flag" in feature_name:
        return "Protocol Flags"
    elif "Win" in feature_name:
        return "TCP Window Behavior"
    return "General Network Behavior"


def _build_explanation_text(top_impacts: pd.DataFrame, prediction: int) -> str:
    """Build plain-text SHAP explanation. Ported from prototype."""
    prediction_label = "ATTACK" if prediction == 1 else "BENIGN"
    grouped: dict[str, list] = {}

    for _, row in top_impacts.iterrows():
        cat = _categorize_feature(row["Feature"])
        grouped.setdefault(cat, []).append(row)

    text = (
        f"The model classified this packet as {prediction_label} "
        f"based on the following behavioral indicators:\n\n"
    )
    for cat, rows in grouped.items():
        text += f"**{cat}:**\n"
        for row in rows:
            direction = "increased" if row["Impact"] > 0 else "decreased"
            text += (
                f"• {row['Feature']} = {row['Actual Value']} "
                f"{direction} attack probability "
                f"(impact score: {row['Impact']:.4f})\n"
            )
        text += "\n"

    text += (
        "Overall, these patterns led to attack classification."
        if prediction == 1
        else "Overall, these patterns led to benign classification."
    )
    return text
