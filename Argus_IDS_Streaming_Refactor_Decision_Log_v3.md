# ARGUS-IDS
## Streaming Refactor — Architecture Decision Log (v3)

> **Changelog from v2:** Section 15 is new. Sections 3.1, 5.1, 9, 11.3, and 14 have been amended. All v3 additions are marked **[AMENDED v3]** or **[NEW v3]**. No existing v1 or v2 decisions have been removed or overridden.

---

# 1. Baseline — Current Project State

The following reflects the state of Argus-IDS immediately before the streaming refactor begins. All new development must build on this foundation without breaking it.

## 1.1 Backend

- FastAPI application entry point: `backend/api/main.py`
- All six model artefacts present in `backend/model/`:
  - `ensemble_model.pkl` — calibrated soft-voting ensemble (sole production binary model)
  - `rf_model.pkl` — benchmarking artefact only
  - `xgb_model.pkl` — benchmarking artefact only
  - `iso_forest.pkl` — Isolation Forest trained on benign-only traffic
  - `scaler.pkl` — MinMaxScaler fitted on training data only
  - `rf_features.pkl` — raw feature name list
- All API endpoints operational: `/health`, `/predict`, `/explain`, `/predict/random`, `/simulate`, `/simulations`, `/alerts`, `/model/threshold`, `/model/metadata`
- Binary classification only — BENIGN vs ATTACK, all attack subtypes collapsed
- No Redis, no WebSocket, no streaming consumers exist
- CI passing on GitHub Actions

## 1.2 Frontend

- React / TypeScript / Vite + shadcn/ui
- Pages: Dashboard, Predict, Simulations, Alerts, Metrics, ModelOverview
- Dashboard is poll-based — no live data, no WebSocket connection
- Existing pages are not to be modified (except Dashboard)

## 1.3 Training

- Single `train_model.py` — binary labels, random stratified 80/20 split
- `train_anomaly.py` — Isolation Forest on benign-only data
- CICIDS2017 (7 CSVs, ~2.3M rows) — all in `./Dataset/`
- CICIoT2023 available as secondary dataset

---

# 2. Model Architecture Decisions

## 2.1 Decision: Two-Model Pipeline

**Decision:** Confirmed. Two separate models — binary severity gate and multiclass attack classifier.

The existing binary ensemble is not retrained or modified. A new multiclass model is trained separately and runs only when the binary model returns ATTACK. Severity tier is always derived from the binary model's calibrated confidence score. The multiclass model provides attack type context only.

| Stage | Model | Output |
|---|---|---|
| Step 1 — Threat gate | `ensemble_model.pkl` (binary) | BENIGN / ATTACK + confidence score |
| Step 2 — Severity | `decision.py` (rule-based) | LOW / MEDIUM / HIGH / ANOMALY |
| Step 3 — Attack type (if ATTACK) | `multiclass_model.pkl` | DoS / PortScan / BruteForce / WebAttack / Infiltration |
| Step 4 — Anomaly check (parallel) | `iso_forest.pkl` | Anomaly flag — upgrades BENIGN severity to ANOMALY |

**Rationale:** The calibrated binary ensemble already achieves ~99.99% accuracy on random-split held-out data. Retraining as pure multiclass risks degrading the severity signal for rare attack classes with very few samples (e.g. Heartbleed: ~11 rows). Keeping them separate gives clean separation of concerns: binary model for reliability, multiclass for attribution.

## 2.2 Decision: Multiclass Model Training Approach

**Decision:** Same RF + XGBoost soft-voting + CalibratedClassifierCV (isotonic, cv=5) pattern as binary model.

- `RandomForestClassifier` — n_estimators=100, random_state=42, n_jobs=2
- `XGBClassifier` — n_estimators=100, random_state=42, objective="multi:softprob", num_class=6, eval_metric="mlogloss"
- `VotingClassifier` — voting="soft"
- `CalibratedClassifierCV` — method="isotonic", cv=5
- Saved as: `multiclass_model.pkl`
- Label map saved as: `multiclass_label_map.json`
- Same `scaler.pkl` applied — never refit

## 2.3 Decision: Attack Label Grouping — 6 Classes

**Decision:** 6 classes confirmed. DDoS folded into DoS family.

| Class ID | Label | Raw CICIDS2017 Labels Covered |
|---|---|---|
| 0 | **BENIGN** | BENIGN |
| 1 | **DoS** | DoS Hulk, DoS GoldenEye, DoS slowloris, DoS Slowhttptest, DDoS |
| 2 | **PortScan** | PortScan |
| 3 | **BruteForce** | FTP-Patator, SSH-Patator, Web Attack – Brute Force |
| 4 | **WebAttack** | Web Attack – XSS, Web Attack – Sql Injection |
| 5 | **Infiltration** | Infiltration, Bot, Heartbleed |

**Rationale:** DoS and DDoS are mechanistically the same threat family (volumetric flooding) and require the same response action. Heartbleed (11 rows) and Bot (~2K rows) are too sparse to train reliably as standalone classes. 6 classes render cleanly on the dashboard without overcrowding.

---

# 3. Training Pipeline Decisions

## 3.1 Decision: Time-Based Train/Test Split **[AMENDED v3]**

**Decision:** Replace random stratified split with temporal file-based split for both binary retraining and multiclass training.

The current random stratified split allows rows from the same network flow to appear in both train and test partitions (temporal autocorrelation). This inflates reported metrics. A time-based split ensures the model is evaluated on traffic it has never seen during training, which is how a real IDS is deployed.

| Partition | Files |
|---|---|
| **Training** | Tuesday-WorkingHours.csv, Wednesday-workingHours.csv, Thursday-WorkingHours-Morning-WebAttacks.csv, Thursday-WorkingHours-Afternoon-Infilteration.csv, Friday-WorkingHours-Morning.csv |
| **Testing** | Mixed held-out CSV (`Dataset/held_out_eval.csv`) — balanced per-class sample drawn from all 7 CICIDS2017 files including Friday afternoon files. See Section 15 for construction details. |

**[AMENDED v3] Role of Friday afternoon files:** `Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv` and `Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv` are no longer a separate held-out test partition. They are part of the source corpus from which the mixed held-out CSV is sampled. Their attack families (DDoS, PortScan) appear in the held-out CSV but not in the training files — this is deliberate and constitutes the "unseen attack family" test condition described in the adaptive evaluation arc (Section 15).

**Expected accuracy range:** 80–88% on the mixed held-out CSV for the binary classifier trained on the temporal split. The lower bound versus the v2 estimate (88–95%) reflects that the held-out set now explicitly includes DDoS and PortScan — attack families entirely absent from the training files. This is honest, defensible, and the accuracy gap is the motivating observation for the Isolation Forest anomaly layer and adaptive retraining arc. See Section 15 for the full evaluation narrative.

**Implementation note:** `train_model.py` is modified to load train files only using `load_multi_csv()`. Evaluation against the held-out CSV is performed by `evaluate_held_out.py` (standalone — does not modify any artefact). `load_multi_csv()` in `data.py` is unchanged.

**[AMENDED] k-fold CV reporting:** In addition to held-out test accuracy, `train_model.py` must also report stratified k-fold (k=5) cross-validation mean ± standard deviation accuracy on the training set. This is required for statistical validation in the paper. Implementation: add a `cross_val_score()` call after model training, before calibration, using the uncalibrated ensemble and the SMOTE-balanced training data.

## 3.2 Decision: Cross-Dataset Evaluation **[AMENDED]**

**Decision:** Add a separate evaluation script against CICIoT2023 after training on CICIDS2017. Results reported as a generalisation finding in the paper.

The same trained model and scaler are used without refitting. Accuracy drop is expected and honest — it demonstrates domain shift between network environments and motivates the transfer learning future work.

**[AMENDED] Feature mismatch handling:** CICIoT2023 and CICIDS2017 do not share an identical feature schema. The evaluation script must:

1. Load `rf_features.pkl` (the training feature list)
2. Load the CICIoT2023 CSV and identify which training features are present
3. Log and report the intersection size (features present in both) and the gap (features expected by the model but absent from CICIoT2023)
4. Fill missing features with zero — never drop packets, as a missing feature on a potentially malicious packet must not create a silent blind spot
5. Apply `scaler.pkl` via `transform()` only — never refit
6. Run inference and report per-class metrics on the intersected feature space

**[AMENDED] Bootstrap confidence intervals:** The evaluation script must report 95% confidence intervals on accuracy and F1-score using bootstrap resampling (1,000 iterations). This provides statistical rigour required for the paper's validation claims and directly addresses the reviewer feedback on statistical validation.

**Paper framing:** "The model achieves X% accuracy (95% CI: [a%, b%]) on held-out CICIDS2017 data under temporal split. When evaluated on CICIoT2023 — an unseen dataset from a different network environment using the Y features common to both schemas — accuracy drops to Z% (95% CI: [c%, d%]), consistent with known domain shift. This degradation is expected for a model trained without transfer learning and is identified as a direction for future work."

---

# 4. Streaming Architecture Decisions

## 4.1 Decision: Message Broker — Redis Streams

**Decision:** Redis Streams selected as the event broker for MVP.

| Option | Decision | Reason |
|---|---|---|
| Apache Kafka | **Deferred** | Requires Docker or ZooKeeper; operational overhead not appropriate for MVP. Identified as production-scale swap in future work. |
| Redis Streams | **Selected ✓** | Lightweight, single pip install (redis-py), native stream semantics (XADD/XREAD/consumer groups), no infrastructure overhead. |

**Paper framing:** "Redis Streams was selected as the message broker for its lightweight deployment profile and native stream semantics. Apache Kafka is identified as the production-scale alternative for organisations requiring higher throughput and multi-consumer group guarantees."

## 4.2 Decision: Stream Topology

Two Redis streams are used:

| Stream | Producer | Consumer(s) |
|---|---|---|
| `argus:flows` | `flow_generator.py` | `prediction_consumer.py` |
| `argus:classified` | `prediction_consumer.py` | `alert_consumer.py`, WebSocket `/ws/stream` |

## 4.3 Decision: Flow Generator Behaviour

**Decision:** Fixed-rate replay — not wall-clock time replay.

- Source: CICIDS2017 CSVs from `./Dataset/`
- Rate: configurable via `ARGUS_STREAM_RATE` env var (default: 50 packets/sec)
- Periodic attack injection: configurable intervals for demo scenario
- Mostly benign traffic with burst attack periods — mirrors realistic network behaviour
- Wall-clock replay rejected — original capture was hours long, unsuitable for demo

---

# 5. New Files — Complete List **[AMENDED]**

## 5.1 Training

| File | Purpose |
|---|---|
| `create_held_out_eval.py` | **[NEW v3]** Sample a balanced per-class subset from all 7 CICIDS2017 CSVs. Target: 2,000–5,000 rows per attack class, equal or 2× benign. Save to `Dataset/held_out_eval.csv`. Log exact row counts per class to stdout and to `backend/model/held_out_manifest.json`. Run once and freeze — this file must never be used in any training loop. |
| `evaluate_held_out.py` | **[NEW v3]** Load the trained binary ensemble and scaler, run inference on `Dataset/held_out_eval.csv`, report overall accuracy and per-class precision/recall/F1 with 95% bootstrap CIs (1,000 iterations). Also flag low-confidence predictions (ensemble confidence < 0.6) and Isolation Forest anomaly rate on the same set. Standalone — does not modify any artefact. Output saved to `backend/model/held_out_eval_results.json`. |
| `train_multiclass.py` | Train 6-class RF+XGBoost ensemble. Saves `multiclass_model.pkl` and `multiclass_label_map.json` to `backend/model/` |
| `evaluate_crossdataset.py` | Load trained models, compute feature intersection with CICIoT2023, run inference on intersected feature space, report accuracy/F1 with 95% bootstrap CIs (1,000 iterations), log schema comparison (present vs missing features). Standalone — does not modify any artefact. |

## 5.2 Backend — Streaming Services

| File | Purpose |
|---|---|
| `backend/services/stream_manager.py` | Redis connection singleton, XADD/XREAD helpers, stream key constants |
| `backend/consumers/flow_generator.py` | Reads CICIDS2017 CSVs row by row, publishes raw feature vectors to `argus:flows` at configured rate |
| `backend/consumers/prediction_consumer.py` | Reads `argus:flows`, runs binary + multiclass pipeline, publishes enriched event to `argus:classified` |
| `backend/consumers/alert_consumer.py` | Reads `argus:classified`, fires Discord webhook on HIGH and ANOMALY severity only |
| `backend/consumers/__init__.py` | Empty init file for package |

## 5.3 Backend — Model Artefacts (new outputs from training)

| Artefact | Description |
|---|---|
| `backend/model/multiclass_model.pkl` | Calibrated 6-class RF+XGBoost ensemble |
| `backend/model/multiclass_label_map.json` | Integer → label string mapping: {0: "BENIGN", 1: "DoS", 2: "PortScan", ...} |

---

# 6. Modified Files — Change Specification **[AMENDED]**

## 6.1 train_model.py **[AMENDED]**

| Change |
|---|
| Replace `train_test_split()` random stratified split with file-based temporal split. Train files and test files explicitly designated by filename prefix. |
| `load_multi_csv()` called twice — once for train file set, once for test file set. No changes to `load_multi_csv()` itself. |
| **[NEW]** Add stratified k-fold (k=5) cross-validation reporting using `cross_val_score()` on the uncalibrated ensemble against SMOTE-balanced training data. Report mean ± std accuracy to stdout and persist to `metadata.json` under key `cv_scores`. |
| All existing artefact saves, evaluation, and SMOTE logic unchanged. |

## 6.2 backend/core/model.py

| Addition |
|---|
| Add `load_multiclass()` — loads `multiclass_model.pkl`, returns None if not present |
| Add `load_label_map()` — loads `multiclass_label_map.json`, returns dict |
| All existing `load_*` functions unchanged |

## 6.3 backend/api/schemas.py

| Addition |
|---|
| Add `attack_type: str \| None` field to `PredictResponse` and `PredictRandomResponse` |
| Add `MulticlassPredictResponse` schema for `/predict/multiclass` endpoint |
| Add `StreamEvent` schema — shape of enriched events published to `argus:classified` and pushed via WebSocket |

## 6.4 backend/api/routes.py

| Addition |
|---|
| Add `POST /predict/multiclass` endpoint — takes same `PredictRequest`, returns `MulticlassPredictResponse` with `attack_type` field |
| Add `GET /ws/stream` WebSocket endpoint — subscribes to `argus:classified` Redis stream, pushes `StreamEvent` JSON to all connected frontend clients |
| Add `load_multiclass()` and `load_label_map()` to `_load_resources()` singleton initialisation |
| All existing endpoints unchanged |

## 6.5 backend/api/main.py

| Addition |
|---|
| No structural changes. WebSocket endpoint is registered via existing router include — no new mount needed. |

## 6.6 frontend/src/pages/Dashboard.tsx

| Panel | Change |
|---|---|
| Top metric cards | Replace Simulations count card with "Packets classified this session" counter |
| Recent alerts panel | Convert from polling `/alerts` to WebSocket subscription. Add `attack_type` label alongside ATTACK/BENIGN. Updates in real-time. |
| Simulation summary panel | Replace with Stream Status panel — packets/sec, stream health indicator (LIVE/STOPPED), last HIGH alert timestamp |
| Alert severity mix donut | Stays. Now updates in real-time from WebSocket event stream instead of polling |
| Simulation risk trend chart | Replace with 60-second rolling attack rate chart — x-axis real time, y-axis packets/sec, lines by attack type (DoS, PortScan, etc.) |
| NEW — Attack type breakdown donut | New panel. Distribution of detected attack types in current session. Updates from WebSocket stream. |
| NEW — SHAP explanation panel | New panel. Auto-appears when HIGH or ANOMALY event received via WebSocket. Shows top 5 SHAP features with impact direction. Auto-updates on next HIGH event. |

## 6.7 frontend/src/lib/types.ts

| Addition |
|---|
| Add `attack_type: string \| null` to `PredictResponse` type |
| Add `StreamEvent` type matching the WebSocket message shape |

## 6.8 frontend/src/lib/api.ts

| Addition |
|---|
| Add `predictMulticlass()` function — POST `/predict/multiclass` |
| Add `createStreamWebSocket()` helper — returns a WebSocket connection to `/ws/stream` with typed onmessage handler |

---

# 7. Files That Must Not Be Modified

The following files are complete and correct. No changes are to be made to them during the streaming refactor.

| File | Reason frozen |
|---|---|
| `backend/core/decision.py` | Severity logic is correct and tested. Two-model decision adds `attack_type` upstream, not in this file. |
| `backend/core/evaluation.py` | Evaluation utilities are model-agnostic. Used by both binary and multiclass training scripts. |
| `backend/core/data.py` | `load_multi_csv()` is unchanged. Time-based split logic lives in `train_model.py` only. |
| `backend/core/simulation.py` | Manual simulation endpoints remain on the Simulations page. No changes needed. |
| `backend/services/SHAP_explainer.py` | SHAP works the same for binary and multiclass. No changes needed. |
| `backend/services/alert_dispatcher.py` | Discord webhook logic is unchanged. `alert_consumer.py` calls it directly. |
| `train_anomaly.py` | Isolation Forest training is unchanged. `iso_forest.pkl` is already correct. |
| `frontend/src/pages/Predict.tsx` | Manual prediction page is unchanged. |
| `frontend/src/pages/Simulations.tsx` | Manual simulation page is unchanged. |
| `frontend/src/pages/Alerts.tsx` | Alert log page is unchanged. |
| `frontend/src/pages/Metrics.tsx` | Threshold metrics page is unchanged. |
| `frontend/src/pages/ModelOverview.tsx` | Model overview page is unchanged. |
| All files in `backend/model/` | Existing artefacts are not deleted. New artefacts are added alongside. |

---

# 8. Explicitly Out of Scope — MVP **[AMENDED]**

The following were discussed and deferred. They must not be implemented during the streaming refactor MVP.

| Feature | Status | Notes |
|---|---|---|
| Attacker profiling layer (AUTOMATED_BOT / TARGETED_HUMAN / AI_DRIVEN) | **Post-MVP** | Requires secondary rule-based classifier on flow timing features. Deferred. |
| Honeypot simulation | **Post-MVP** | Depends on the attacker profiling layer. Deferred. |
| Historical replay controls from UI | **Post-MVP** | Pause/speed up flow generator from dashboard. Adds WebSocket protocol complexity. |
| Geographic IP mapping | **Excluded** | CICIDS2017 has no real IPs. Synthetic mapping would be misleading. |
| CNN / LSTM in ensemble | **Excluded** | Out of architectural scope. May appear in literature review only. |
| SVM in ensemble | **Excluded** | Out of architectural scope permanently. |
| Live packet capture (Scapy/PyShark) | **Excluded** | Out of scope. Flow generator replays CICIDS2017 as synthetic stream. |
| Email alerts | **Excluded** | Discord webhook is the only alert channel. |
| Docker (for MVP) | **Deferred** | Not used during development. May be added for final deployment/submission packaging. |
| **[NEW]** Feature drift monitoring (`schema_validator.py`) | **Post-MVP / Future Work** | See Section 13. Architectural pattern documented for paper. Not implemented in MVP. |
| **[NEW]** Drift store and review pipeline | **Post-MVP / Future Work** | See Section 13. Future work only. |
| **[NEW]** Blue-green / shadow model deployment | **Post-MVP / Future Work** | See Section 13. Future work only. |
| **[NEW]** Online retraining pipeline | **Post-MVP / Future Work** | See Section 13. Future work only. |

---

# 9. Recommended Implementation Order

Each phase must be complete and verified before the next begins. Do not start a phase if the previous phase has failing tests or broken endpoints.

| Phase | Task | Files touched |
|---|---|---|
| **1a** | **[AMENDED v3]** Create mixed held-out evaluation CSV from all 7 CICIDS2017 files | `create_held_out_eval.py` (new) |
| **1b** | Retrain binary model with temporal file-based split (train files only) + k-fold CV reporting | `train_model.py` only |
| **1c** | **[NEW v3]** Evaluate retrained binary model + Isolation Forest on held-out CSV; record baseline accuracy and anomaly rate | `evaluate_held_out.py` (new) |
| **2** | Train multiclass model | `train_multiclass.py` (new) |
| **3** | Cross-dataset evaluation with feature schema comparison and bootstrap CIs | `evaluate_crossdataset.py` (new) |
| **4** | Extend model loader and schemas | `backend/core/model.py`, `backend/api/schemas.py` |
| **5** | Add `/predict/multiclass` endpoint | `backend/api/routes.py` |
| **6** | Build Redis stream manager and flow generator | `backend/services/stream_manager.py`, `backend/consumers/flow_generator.py` |
| **7** | Build prediction consumer | `backend/consumers/prediction_consumer.py` |
| **8** | Build alert consumer | `backend/consumers/alert_consumer.py` |
| **9** | Add WebSocket `/ws/stream` endpoint | `backend/api/routes.py` |
| **10** | Update frontend types and API client | `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts` |
| **11** | Rebuild Dashboard page with live panels | `frontend/src/pages/Dashboard.tsx` |

---

# 10. Hard Constraints — Never Violate **[AMENDED]**

These constraints apply to every implementation decision in the project, including during the streaming refactor. Any code that violates these must be rejected and rewritten.

- `ensemble_model.pkl` is the sole production binary model. `rf_model.pkl` and `xgb_model.pkl` are benchmarking artefacts only and must never be loaded at inference time.
- `scaler.pkl` must never be refit during inference. It is fitted once on training data in `train_model.py` and applied read-only everywhere else — including in `evaluate_crossdataset.py`.
- SMOTE must be applied on the training partition only, after the train/test split. Never before.
- `iso_forest.pkl` was trained on benign-only data using the already-fitted scaler. It must never be retrained using attack data.
- All model artefacts must load from `backend/model/` only. No hardcoded paths — use `ARGUS_MODEL_DIR` env var.
- The existing `/predict`, `/alerts`, `/simulate`, `/simulations`, `/predict/random`, `/explain`, `/model/threshold`, and `/model/metadata` endpoints must remain functional and unchanged after the refactor.
- **[NEW]** Missing features encountered during cross-dataset evaluation or inference must never cause a packet to be silently dropped. Fill with zero and classify — the anomaly layer provides the safety net for low-confidence or unusual inputs.
- **[NEW]** Bootstrap CI computation in `evaluate_crossdataset.py` must use the intersected feature set only — never impute features from a different distribution.

---

# 11. Research Documentation Decisions **[NEW]**

These decisions govern the academic paper and dossier changes required to address the reviewer feedback (score: 6/10). They have no direct code impact but must be completed alongside the implementation phases.

## 11.1 Novelty Matrix

**Decision:** Add a novelty comparison matrix to the paper as a dedicated figure.

The matrix rows are prior systems from the literature review (minimum 6 papers). The columns are the capability dimensions along which Argus differentiates itself:

| Dimension | Description |
|---|---|
| Calibrated ensemble | Isotonic-calibrated soft-voting, not raw predict_proba |
| Anomaly layer | Unsupervised zero-day detection path |
| SHAP explainability | Per-prediction feature attribution |
| Temporal evaluation | Time-based train/test split, not random |
| Multi-file ingestion | Full 7-file CICIDS2017 corpus, not single-file subset |
| Severity tiering | Four-tier operational output (LOW/ANOMALY/MEDIUM/HIGH) |
| Multiclass attribution | Attack type identification beyond binary ATTACK/BENIGN |
| Cross-dataset validation | Evaluated on a second independent dataset |

Each cell is marked ✓ (fully present), ✗ (absent), or ~ (partially addressed). Argus must have ✓ across all columns. No prior work reviewed should have ✓ across all columns — if one does, the literature review needs to be extended with additional papers.

**Deliverable:** A table in the paper (Section 6 or Section 14) and a matching PNG figure generated for the dossier.

## 11.2 Literature Review Strengthening

**Decision:** Rewrite Section 5 of the dossier with the following changes:

- Minimum 8 cited references (currently 6)
- Each paper cited with a numbered reference (e.g. [1], [2]) not described generically
- Each entry must include: what the paper did, what metric it achieved, and specifically why it is insufficient relative to Argus's design goals
- Add a closing comparative synthesis paragraph that explicitly maps each gap to a specific Argus design decision
- The temporal split (Section 3.1) and cross-dataset evaluation (Section 3.2) should be cited as differentiators absent from all reviewed works

## 11.3 Updated Hypothesis H2

**Decision:** Replace the existing H2 accuracy target of ≥99.5% with the following: **[AMENDED v3]**

> **H2 (revised):** Under a temporal file-based train/test split — which prevents temporal autocorrelation between train and test partitions — the calibrated RF+XGBoost ensemble will achieve binary classification accuracy in the range of 80–88% on the mixed held-out evaluation set (`Dataset/held_out_eval.csv`), with a 95% bootstrap confidence interval width of no more than ±3 percentage points. The held-out set includes DDoS and PortScan attack families present only in the Friday afternoon files, which are entirely absent from the training corpus. The accuracy gap relative to random-split figures (99%+) is expected, interpretable, and constitutes the motivating observation for the Isolation Forest anomaly layer and the adaptive retraining arc (Section 15). Following oracle-labelled adaptive retraining on the misclassified flows, accuracy on the same frozen held-out set is expected to recover to 90–96%.

**Rationale:** The 99.99% figure from random split is not defensible as a generalisation claim. The held-out set is now explicitly designed to expose the binary model's blind spot on unseen attack families, giving the paper a clean result arc: initial gap → anomaly detection → retraining → recovery. This is more publishable than a flat high-accuracy result with no narrative.

## 11.4 Deployment Lifecycle Diagram

**Decision:** Add a deployment lifecycle diagram to the paper as a dedicated figure (separate from Fig. M1).

The diagram must show the full operational cycle:

```
Detection (live inference)
        ↓
Drift Monitoring (future work — schema_validator.py)
        ↓
Drift Store accumulation (future work)
        ↓
Human / automated review
        ↓
Retrain on updated corpus
        ↓
Validate against accuracy gate (≥ threshold)
        ↓
Blue-Green / Shadow deployment (future work)
        ↓
Back to Detection
```

Components marked "future work" must be visually distinguished (e.g. dashed border) from components currently implemented. This diagram responds directly to the reviewer feedback requesting "complete architecture/deployment diagrams."

## 11.5 Streaming Architecture Diagram

**Decision:** Add a second architecture diagram showing the Redis Streams topology introduced by the streaming refactor. This is distinct from Fig. M1 (the detection pipeline) and must show:

```
CICIDS2017 CSVs
      ↓
flow_generator.py (fixed-rate replay)
      ↓
argus:flows (Redis Stream)
      ↓
prediction_consumer.py
  → binary ensemble → multiclass model → SHAP → decision.py
      ↓
argus:classified (Redis Stream)
      ↙              ↘
alert_consumer.py    WebSocket /ws/stream
(Discord webhook)         ↓
                    Dashboard (React)
                    live panels
```

**Deliverable:** A PNG or draw.io diagram included in the paper and dossier.

---

# 12. Statistical Validation Decisions **[NEW]**

## 12.1 k-fold Cross-Validation Reporting

**Decision:** `train_model.py` must report stratified 5-fold CV results in addition to held-out test accuracy.

- Use `cross_val_score()` from sklearn on the uncalibrated `VotingClassifier`
- Data: SMOTE-balanced training partition only
- Metric: accuracy
- Output: mean ± std printed to stdout and stored in `metadata.json` under `cv_scores: { mean: float, std: float, folds: list[float] }`
- This value is what gets cited in the paper as the training-time performance estimate

## 12.2 Bootstrap Confidence Intervals

**Decision:** `evaluate_crossdataset.py` must compute 95% bootstrap CIs on both accuracy and macro F1-score.

- 1,000 bootstrap iterations
- Sampling with replacement from the evaluation set
- Report: point estimate, lower bound, upper bound
- Both CICIDS2017 temporal test set and CICIoT2023 evaluation must report CIs
- Results stored to `backend/model/crossdataset_eval.json`

## 12.3 Schema Comparison Step

**Decision:** `evaluate_crossdataset.py` must perform and log a feature schema comparison before inference.

The comparison report must include:

- Total features expected by model (from `rf_features.pkl`)
- Total features present in CICIoT2023
- Features in both (intersection) — these are used for inference
- Features expected but missing from CICIoT2023 — filled with zero, logged
- Features in CICIoT2023 not expected by model — ignored, logged
- Intersection ratio: `len(intersection) / len(rf_features)` — reported as a data quality metric in the paper

**Constraint:** Missing features are filled with zero. Packets are never dropped regardless of how many features are missing. This maintains the fail-secure principle — a malicious packet with an unusual feature profile must still be processed, not silently discarded.

**Output:** Schema comparison report printed to stdout and saved to `backend/model/schema_comparison.json`.

---

# 13. Future Work Scope — Operational Lifecycle **[NEW]**

The following items are confirmed as **future work only**. They must not be implemented during the current evaluation phase. They must be documented in the paper's future work section (Section 11 of the ICICN paper) with sufficient architectural detail to demonstrate that the research team has thought through the operational implications.

## 13.1 Feature Drift Monitoring

**Architectural pattern to document:**

When Argus is deployed in a production IoT gateway environment, the feature distribution of incoming traffic will gradually shift as new device types are added, firmware updates change packet behaviour, or new attack variants emerge. A production deployment requires continuous monitoring of this drift.

The proposed architecture for future implementation:

```
Incoming packet at /predict
        ↓
schema_validator.py
  - Compare feature vector against rf_features.pkl
  - Flag features with values outside [min, max] seen during training
  - Flag feature vectors with unusually high missing-feature count
        ↓
drift_log/ store
  - Append flagged packets with timestamp, feature deltas, prediction outcome
  - Structured as append-only JSONL for auditability
        ↓
Periodic drift aggregation (e.g. daily cron)
  - Compute distribution shift metrics (e.g. Population Stability Index per feature)
  - Trigger retraining recommendation when PSI > threshold on >10% of features
```

**Paper framing:** "A production deployment of Argus would require continuous feature drift monitoring to detect distributional shift between the training corpus and live gateway traffic. We propose a schema validation layer that flags incoming feature vectors deviating from training-time distributions and accumulates them in an auditable drift store for periodic review. This extends the current static evaluation framework toward a continuously adaptive detection system."

## 13.2 Online Retraining Pipeline

**Architectural pattern to document:**

Retraining should be triggered by drift monitoring threshold breaches or on a scheduled cadence (e.g. monthly). The pipeline must:

1. Augment the original CICIDS2017 training corpus with verified new samples from the drift store
2. Re-run `train_model.py` with the temporal split preserved
3. Validate the new model against the accuracy gate (≥88% on temporal test set)
4. Only promote the new model if it passes validation

## 13.3 Zero-Downtime Model Deployment

**Architectural pattern to document:**

Argus currently loads model artefacts once at FastAPI startup. A zero-downtime update requires one of two patterns:

**Blue-Green:** Two Uvicorn worker processes run behind a process manager (gunicorn). The new model is loaded by the idle worker. Traffic is atomically switched. The old worker is kept for rollback.

**Shadow deployment:** The candidate model runs in parallel with the production model, processing copies of live traffic. Predictions are logged but not served. When the candidate matches or exceeds production on real traffic for a configurable observation window, it is promoted.

Shadow deployment is preferred for security-critical systems because it never serves unvalidated predictions to real analysts.

**Paper framing:** "We identify zero-downtime model replacement as a critical operational requirement for production IDS deployments. The current Argus architecture supports blue-green deployment via Uvicorn worker rotation without structural changes to the FastAPI application. Shadow deployment — where a candidate model processes live traffic silently before promotion — is identified as the preferred pattern for security-critical environments, as it prevents unvalidated models from generating analyst-facing alerts."

---

# 14. Hard Constraints Addendum **[NEW]**

The following constraints are specific to the new evaluation and documentation decisions and apply in addition to Section 10.

- The novelty matrix (Section 11.1) must be grounded in the actual literature reviewed. No paper may be misrepresented — if a paper partially addresses a dimension, it gets ~ not ✗.
- Hypothesis H2 (Section 11.3) must use the temporal split accuracy range in all paper and dossier submissions. The 99.99% figure from random split may only be cited as a comparison point, not as the primary result.
- Bootstrap CI computation must use numpy's `np.random.choice` with `replace=True` and `random_state=42` for reproducibility.
- The schema comparison report must be generated and saved before any inference is run on CICIoT2023 — it is a prerequisite step, not an optional log.
- All future work items in Section 13 must appear in the paper with a diagram or architectural sketch. They must not be described as vague aspirations — the operational pattern must be specified clearly enough that a future implementer could build from the description.
- **[NEW v3]** `Dataset/held_out_eval.csv` must be created by `create_held_out_eval.py` before any model training begins. It must never be modified, resampled, or used as a training source at any point in the pipeline. Its manifest (`backend/model/held_out_manifest.json`) must be committed alongside the file so the exact composition is auditable.
- **[NEW v3]** Adaptive retraining (Section 15, Step 5) uses oracle labels from CICIDS2017 ground truth only — not model predictions, not unsupervised cluster assignments. This must be stated explicitly in the paper as supervised retraining on analyst-confirmed labels, not autonomous self-adaptation.
- **[NEW v3]** The before/after retraining comparison in Section 15 must use the same frozen `Dataset/held_out_eval.csv` for both evaluations. Any result that uses a different evaluation set for before vs after is invalid.

---

# 15. Adaptive Evaluation Arc **[NEW v3]**

This section documents the full evaluation narrative for the binary classifier under temporal split. It governs what `create_held_out_eval.py`, `evaluate_held_out.py`, and the Phase 2 adaptive retraining steps must demonstrate. This is a research result arc, not a deployment pipeline — the "retraining" here is a controlled experiment performed once to demonstrate the principle, not an automated production loop.

## 15.1 Mixed Held-Out CSV Construction

**Decision:** Create `Dataset/held_out_eval.csv` by stratified per-class sampling from all 7 CICIDS2017 files before any training begins.

**Sampling targets:**

| Attack class | Source files | Target rows |
|---|---|---|
| BENIGN | All 7 files | 2× the largest attack class sample (capped at 10,000) |
| DoS | Wednesday, Friday-Morning | 2,000–5,000 |
| PortScan | Friday-Afternoon-PortScan | 2,000–5,000 |
| BruteForce | Tuesday | 2,000–5,000 |
| WebAttack | Thursday-Morning | 2,000 (or all available if fewer) |
| Infiltration | Thursday-Afternoon | 2,000 (or all available if fewer) |
| DDoS | Friday-Afternoon-DDoS | 2,000–5,000 |

**Implementation constraints:**
- Random sampling with `random_state=42` for reproducibility
- If a class has fewer rows than the target after cleaning, take all available rows — do not oversample
- Save exact row counts per class (before and after cleaning) to `backend/model/held_out_manifest.json`
- The CSV is saved once and never modified — treat it as a fixture

**Script:** `create_held_out_eval.py` — standalone, no model loading, no training side-effects

## 15.2 Step-by-Step Evaluation Arc

The following steps define the before/after retraining experiment. Each step produces a logged result. Steps 1–4 are implemented in Phase 1c. Step 5 is implemented in Phase 2 (after multiclass model exists). Step 6 closes the arc.

**Step 1 — Baseline binary evaluation (before retraining)**

Run `evaluate_held_out.py` immediately after Phase 1b training completes.

Expected result: Overall accuracy 80–88%. PortScan and DDoS recall will be poor (likely <50%) because neither appears in the training files. BruteForce, DoS, WebAttack, Infiltration recall will be moderate-to-good. This gap is the key finding — document it in the paper as the cost of honest temporal evaluation.

**Step 2 — Isolation Forest anomaly coverage**

As part of `evaluate_held_out.py`, run each held-out packet through `iso_forest.pkl` in parallel with the binary ensemble.

Log:
- Anomaly rate on correctly classified packets (expected: low)
- Anomaly rate on misclassified packets (expected: higher — the anomaly layer should catch a portion of the PortScan/DDoS flows the binary model misses)
- Anomaly rate on BENIGN packets (false positive rate on the iso_forest path — expected: ~5%, matching the contamination parameter)

**Paper framing:** "Of the N flows misclassified by the binary ensemble under temporal evaluation, X% were flagged as anomalies by the Isolation Forest layer, demonstrating that the unsupervised anomaly path provides partial compensatory coverage for novel attack families absent from the training corpus."

**Step 3 — Multiclass attribution on anomaly-flagged flows (Phase 2)**

After `multiclass_model.pkl` exists, route all Isolation-Forest-flagged flows from Step 2 through the multiclass classifier. Log per-class attribution accuracy on the flagged subset.

This step demonstrates the full three-stage pipeline in action: binary miss → anomaly flag → multiclass attribution.

**Step 4 — Log missed flows with oracle labels**

From the held-out CSV evaluation (Step 1), extract all rows where:
- Binary model predicted BENIGN but ground-truth label is ATTACK (false negatives), **or**
- Binary model confidence < 0.6 on any prediction (low-confidence, regardless of label)

Attach the CICIDS2017 ground-truth label to each row. Save to `backend/model/missed_flows.csv`.

This is the oracle-labelled drift store that feeds the retraining step. Must be stated in the paper as: "Missed flows were labelled using CICIDS2017 ground truth, simulating analyst-confirmed labelling in a production drift-store pipeline."

**Step 5 — Adaptive retraining (Phase 2)**

Retrain the binary ensemble by appending `missed_flows.csv` to the original training corpus (the temporal-split training files). Apply the full pipeline: SMOTE on the augmented training set, calibrate with CalibratedClassifierCV (isotonic, cv=5), save as `ensemble_model_retrained.pkl` (separate from the production `ensemble_model.pkl` — do not overwrite).

**Constraint:** `scaler.pkl` is not refit — the original scaler is applied read-only to the augmented training data before SMOTE.

**Step 6 — After-retraining evaluation**

Run `evaluate_held_out.py` again against the same frozen `Dataset/held_out_eval.csv`, using `ensemble_model_retrained.pkl` instead of `ensemble_model.pkl`.

Expected result: Overall accuracy 90–96%. PortScan and DDoS recall should improve materially. Document the delta (accuracy before vs after, per-class recall delta) as the primary experimental result in the paper.

**Output:** `backend/model/held_out_eval_retrained_results.json`

## 15.3 Paper Framing for Section 3.1 (Updated)

> "Following the temporal evaluation protocol, the binary classifier is trained on Monday–Thursday traffic files and evaluated on a balanced mixed held-out set (`held_out_eval.csv`) sampled from all attack families across all 7 CICIDS2017 files. The day-segregated structure of CICIDS2017 means PortScan and DDoS — captured exclusively on Friday afternoon — represent genuinely unseen attack families at inference time. This deliberate design allows us to demonstrate three things in sequence: (1) the binary classifier's performance gap on unseen attack families under honest temporal evaluation; (2) the role of the Isolation Forest anomaly layer in surfacing attacks the binary classifier cannot detect; and (3) the recovery in detection capability achieved by oracle-labelled adaptive retraining on the missed flows. Retraining uses CICIDS2017 ground-truth labels, simulating analyst-confirmed labelling in a production drift-store pipeline."

## 15.4 New Artefacts Produced by This Arc

| Artefact | Producer | Description |
|---|---|---|
| `Dataset/held_out_eval.csv` | `create_held_out_eval.py` | Frozen balanced evaluation set — never modified after creation |
| `backend/model/held_out_manifest.json` | `create_held_out_eval.py` | Row counts per class; source files; sampling parameters |
| `backend/model/held_out_eval_results.json` | `evaluate_held_out.py` | Before-retraining accuracy, per-class metrics, bootstrap CIs, anomaly rates |
| `backend/model/missed_flows.csv` | `evaluate_held_out.py` | Oracle-labelled false negatives and low-confidence flows |
| `backend/model/ensemble_model_retrained.pkl` | Retraining step (Phase 2) | Retrained binary ensemble — benchmarking only, not loaded at inference |
| `backend/model/held_out_eval_retrained_results.json` | `evaluate_held_out.py` (Phase 2) | After-retraining accuracy, per-class metrics, bootstrap CIs |

---

*End of Argus-IDS Streaming Refactor Architecture Decision Log v3*
*Original decisions: Sections 1–10 (v1)*
*New decisions in v2: Sections 11–14, and amendments within Sections 3, 5, 6, 8, 10*
*New decisions in v3: Section 15, and amendments within Sections 3.1, 5.1, 9, 11.3, 14*
