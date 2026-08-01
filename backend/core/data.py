# filename: backend/core/data.py
# purpose: Dataset loading, preprocessing, SMOTE, PCA, train/test split


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

    df = pd.read_csv(filepath)
    df.columns = df.columns.str.strip()
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.dropna(inplace=True)

    for col in _DROP_COLS:
        if col in df.columns:
            df.drop(col, axis=1, inplace=True)

    return df


def load_multi_csv(
    directory: str,
    feature_list_override: list[str] | None = None,
    exclude_filenames: list[str] | None = None,
) -> tuple[pd.DataFrame, list[dict[str, int | str]]]:
    """
    Load and concatenate all .csv files from `directory` in sorted order.
    Args:
        directory: Path to folder containing CSVs (e.g. 'Dataset').
        feature_list_override: If provided, restrict feature columns to this
            exact list instead of computing the intersection. The 'Label'
            column is always included regardless. Useful when retraining must
            match a previously saved rf_features.pkl.

    Returns:
        Tuple of:
        - Concatenated DataFrame. Columns: common feature set + 'Label'.
        Column names are stripped. Inf/NaN rows are dropped. Metadata
        columns (Flow ID, Source IP, Destination IP, Timestamp) are removed.
        Index is reset.
        - Per-file stats with filename, total_rows, benign, and attack counts.

    Raises:
        FileNotFoundError: If `directory` contains no .csv files.
        ValueError: If 'Label' column is missing in any file, or if
            `feature_list_override` contains columns absent from the
            concatenated data.
    """
    import glob

    csv_paths = sorted(glob.glob(os.path.join(directory, "*.csv")))
    if not csv_paths:
        raise FileNotFoundError(f"No .csv files found in directory: {directory!r}")

    # Optionally exclude specific filenames (case-insensitive)
    if exclude_filenames:
        exclude_set = {name.lower() for name in exclude_filenames}
        csv_paths = [p for p in csv_paths if os.path.basename(p).lower() not in exclude_set]
        if not csv_paths:
            raise FileNotFoundError(
                f"No .csv files found in directory after excluding {exclude_filenames!r}"
            )

    print(f"[multi_csv] Found {len(csv_paths)} file(s) in {directory!r}")

    per_file_frames: list[pd.DataFrame] = []
    per_file_row_counts: dict[str, int] = {}
    per_file_stats: list[dict[str, int | str]] = []
    per_file_col_sets: list[set[str]] = []

    for path in csv_paths:
        fname = os.path.basename(path)
        print(f"[multi_csv]   Loading: {fname} ...", end=" ", flush=True)

        # Chunked read to avoid loading entire raw file into memory
        file_chunks: list[pd.DataFrame] = []
        chunk_row_total = 0
        for chunk in pd.read_csv(path, encoding="utf-8", chunksize=50_000):
            chunk.columns = chunk.columns.str.strip()

            # Drop metadata columns that carry no signal
            for col in _DROP_COLS:
                if col in chunk.columns:
                    chunk.drop(col, axis=1, inplace=True)

            # Inf → NaN → drop
            chunk.replace([np.inf, -np.inf], np.nan, inplace=True)
            chunk.dropna(inplace=True)

            # Ensure Label column exists in this chunk (same behaviour as before)
            if _LABEL_COL not in chunk.columns:
                raise ValueError(
                    f"'Label' column not found in {fname}. "
                    "Check the file or the COLS_TO_DROP list."
                )

            file_chunks.append(chunk)
            chunk_row_total += len(chunk)

        # Concatenate cleaned chunks for this file
        if file_chunks:
            df = pd.concat(file_chunks, ignore_index=True)
        else:
            # No valid data after cleaning; create empty frame with no rows
            df = pd.DataFrame()

        row_count = len(df)
        per_file_row_counts[fname] = row_count
        per_file_frames.append(df)

        # Track feature columns (everything except Label) for intersection
        feature_cols = set(df.columns) - {_LABEL_COL}
        per_file_col_sets.append(feature_cols)

        benign = (df[_LABEL_COL].str.strip().str.upper() == "BENIGN").sum()
        attack = row_count - benign
        per_file_stats.append(
            {
                "filename": fname,
                "total_rows": int(row_count),
                "benign": int(benign),
                "attack": int(attack),
            }
        )
        print(f"{row_count:,} rows  (benign={benign:,}  attack={attack:,})")

    # Resolve common feature schema
    common_features: list[str] = sorted(set.intersection(*per_file_col_sets))
    print(f"[multi_csv] Common feature columns: {len(common_features)}")

    # Validate feature_list_override against common schema
    if feature_list_override is not None:
        missing = [f for f in feature_list_override if f not in common_features]
        if missing:
            raise ValueError(
                f"feature_list_override contains columns not present in all files: {missing}"
            )
        selected_features = feature_list_override
        print(f"[multi_csv] Using feature_list_override: {len(selected_features)} columns")
    else:
        selected_features = common_features

    # Restrict each frame to selected features + Label, then concatenate
    aligned_frames = [df[selected_features + [_LABEL_COL]] for df in per_file_frames]
    combined = pd.concat(aligned_frames, ignore_index=True)

    # Summary log
    total = len(combined)
    benign_total = (combined[_LABEL_COL].str.strip().str.upper() == "BENIGN").sum()
    attack_total = total - benign_total

    print("[multi_csv] ── Concatenation complete ──────────────────────────────")
    print(f"[multi_csv]   Files loaded      : {len(csv_paths)}")
    print(f"[multi_csv]   Total rows        : {total:,}")
    print(f"[multi_csv]   Benign rows       : {benign_total:,}")
    print(f"[multi_csv]   Attack rows       : {attack_total:,}")
    print(f"[multi_csv]   Feature columns   : {len(selected_features)}")
    for fname, count in per_file_row_counts.items():
        print(f"[multi_csv]     {fname}: {count:,} rows")
    print("[multi_csv] ────────────────────────────────────────────────────────")

    return combined, per_file_stats


def split_dataset(
    df: pd.DataFrame,
    feature_names: list[str],
    use_pca: bool = False,
    pca_components: int = 30,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """
    Apply §5.2 steps 3-6 in correct order, then return train/test splits.

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
