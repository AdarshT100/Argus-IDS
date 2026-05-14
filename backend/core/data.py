# filename: backend/core/data.py
# purpose: Dataset loading, preprocessing, SMOTE, PCA, train/test split
# governed by: §5.1, §5.2 (preprocessing pipeline — fixed order)

from __future__ import annotations

import os
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
from sklearn.decomposition import PCA
from imblearn.over_sampling import SMOTE

_DROP_COLS: list[str] = ["Flow ID", "Source IP", "Destination IP", "Timestamp"]
_LABEL_COL: str = "Label"
_MODEL_DIR: str = os.environ.get("ARGUS_MODEL_DIR", "backend/model")


def load_dataset(filepath: str) -> pd.DataFrame:
    """
    Load a CICIDS2017-format CSV, strip column names, drop non-informative columns,
    and handle infinite / NaN values. Steps 1–2 of §5.2.
    """
    df = pd.read_csv(filepath)
    df.columns = df.columns.str.strip()
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.dropna(inplace=True)

    for col in _DROP_COLS:
        if col in df.columns:
            df.drop(col, axis=1, inplace=True)

    return df


def split_dataset(
    df: pd.DataFrame,
    feature_names: list[str],
    use_pca: bool = False,
    pca_components: int = 30,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """
    Apply §5.2 steps 3–6 in correct order, then return train/test splits.

    Step 3: label encode
    Step 4: 80/20 stratified split (fit scaler on train only — §5.1)
    Step 5: SMOTE on train only
    Step 6: optional PCA (default off)

    DEVIATION NOTE: prototype applied MinMaxScaler before splitting (wrong).
    Fixed here — scaler is fit on X_train only, then applied to both splits.
    """
    y: pd.Series = df[_LABEL_COL].apply(lambda x: 0 if x == "BENIGN" else 1)
    X: pd.DataFrame = df[feature_names]

    # Step 4a — split first, before any fitting
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Step 4b — fit scaler on train only, transform both
    scaler = MinMaxScaler()
    X_train_scaled = pd.DataFrame(
        scaler.fit_transform(X_train), columns=feature_names, index=X_train.index
    )
    X_test_scaled = pd.DataFrame(
        scaler.transform(X_test), columns=feature_names, index=X_test.index
    )

    # Persist scaler for inference use
    import joblib
    import os
    os.makedirs(_MODEL_DIR, exist_ok=True)
    joblib.dump(scaler, os.path.join(_MODEL_DIR, "scaler.pkl"))

    # Step 5 — SMOTE on train only
    sm = SMOTE(random_state=42)
    X_res, y_res = sm.fit_resample(X_train_scaled, y_train)
    X_train_final = pd.DataFrame(X_res, columns=feature_names)
    y_train_final = pd.Series(y_res)

    # Step 6 — optional PCA (default off)
    if use_pca:
        pca = PCA(n_components=pca_components, random_state=42)
        X_train_final = pd.DataFrame(
            pca.fit_transform(X_train_final),
            columns=[f"PC{i + 1}" for i in range(pca_components)],
        )
        X_test_scaled = pd.DataFrame(
            pca.transform(X_test_scaled),
            columns=[f"PC{i + 1}" for i in range(pca_components)],
        )

    return X_train_final, X_test_scaled, y_train_final, y_test
