export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'ANOMALY' | string

export type HealthResponse = {
  status: 'ok'
}

export type PredictRequest = {
  features: Record<string, number>
}

export type ExplainRequest = PredictRequest

export type ShapFeature = {
  feature: string
  impact: number
}

export type PredictResponse = {
  prediction: string
  severity: Severity
  anomaly_score: number
  confidence: number
  explanation_text: string
  shap_top_features: ShapFeature[]
  timestamp: string
}

export type PredictRandomResponse = PredictResponse & {
  raw_features: Record<string, number>
}

export type ExplainResponse = {
  feature_contributions: Record<string, number>
  top_features: ShapFeature[]
  explanation_text: string
}

export type AlertEntry = {
  timestamp: string
  prediction: string
  severity: Severity
  confidence: number
  anomaly_score: number
  shap_top_features: ShapFeature[]
}

export type AlertsResponse = {
  alerts: AlertEntry[]
  total: number
}

export type SimulateRequest = {
  window_size: number
}

export type SimulateResponse = {
  timestamp: string
  window_size: number
  attack_count: number
  anomaly_count: number
  mean_risk_score: number
  severity: Severity
  alert_triggered: boolean
}

export type SimulationsResponse = {
  simulations: SimulateResponse[]
  total: number
}

export type ThresholdMetricsResponse = {
  threshold: number
  confusion_matrix: number[][]
  precision: number
  recall: number
  f1_score: number
  support: number
  total: number
  tn: number
  fp: number
  fn: number
  tp: number
}

export type DatasetFileStats = {
  filename: string
  total_rows: number
  benign: number
  attack: number
}

export type ModelDatasetSource = {
  mode?: string | null
  data_dir?: string | null
  data_file?: string | null
  loaded_files?: DatasetFileStats[]
}

export type ModelMetadataResponse = {
  trained_at: string | null
  calibrated_accuracy: number | null
  raw_accuracy: Record<string, number> | null
  train_count: number | null
  test_count: number | null
  smote_train_count: number | null
  smote_class_counts: Record<string, number> | null
  feature_count: number | null
  use_pca: boolean | null
  dataset_source: ModelDatasetSource | null
  calibration_status: string | null
  hyperparameters: Record<string, unknown> | null
}

export type ApiErrorDetail =
  | string
  | Array<Record<string, unknown>>
  | Record<string, unknown>
  | null

export type BackendErrorResponse = {
  detail?: ApiErrorDetail
}
