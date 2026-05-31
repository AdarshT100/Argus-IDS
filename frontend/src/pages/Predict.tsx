import { useState, type SubmitEvent } from 'react'
import { Alert } from '../components/ui/alert'
import { Button } from '../components/ui/button'
import { Textarea } from '../components/ui/textarea'
import {
  EmptyState,
  Panel,
  SeverityBadge,
  ShapImpactChart,
} from '../components/shared'
import { usePredictMutation, usePredictRandomMutation } from '../lib/queries'
import type {
  PredictRandomResponse,
  PredictResponse,
  ShapFeature,
} from '../lib/types'
import {
  errorMessage,
  formatDate,
  formatExplanationText,
  formatNumber,
  formatPercent,
  isPlainObject,
} from '../lib/utils'

type ParsedFeatures =
  | { ok: true; value: Record<string, number> }
  | { ok: false; error: string }

const sampleFeatureJson = JSON.stringify(
  {
    'Flow Duration': 123456,
    'Total Fwd Packets': 10,
    'Total Backward Packets': 8,
    'Flow Bytes/s': 2345.7,
    'Flow Packets/s': 14.8,
  },
  null,
  2,
)

export default function PredictPage() {
  const [featureJson, setFeatureJson] = useState(sampleFeatureJson)
  const [validationError, setValidationError] = useState('')
  const [result, setResult] = useState<
    PredictResponse | PredictRandomResponse | null
  >(null)
  const predictMutation = usePredictMutation()
  const randomMutation = usePredictRandomMutation()

  function submitPrediction(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const parsed = parseFeatureJson(featureJson)

    if (!parsed.ok) {
      setValidationError(parsed.error)
      return
    }

    setValidationError('')
    predictMutation.mutate(
      { features: parsed.value },
      {
        onSuccess: setResult,
      },
    )
  }

  function runRandomPrediction() {
    setValidationError('')
    randomMutation.mutate(undefined, {
      onSuccess: (response) => {
        setResult(response)
        setFeatureJson(JSON.stringify(response.raw_features, null, 2))
      },
    })
  }

  const activeError =
    validationError ||
    errorMessage(predictMutation.error) ||
    errorMessage(randomMutation.error)

  return (
    <section className="content-grid predict-layout">
      <Panel title="Feature JSON" eyebrow="Request body">
        <form className="form-stack" onSubmit={submitPrediction}>
          <Textarea
            aria-label="Feature JSON"
            className="json-input"
            value={featureJson}
            onChange={(event) => setFeatureJson(event.target.value)}
            spellCheck={false}
          />
          {activeError && <Alert variant="error">{activeError}</Alert>}
          <div className="button-row">
            <Button disabled={predictMutation.isPending} type="submit">
              {predictMutation.isPending ? 'Predicting...' : 'Run prediction'}
            </Button>
            <Button
              disabled={randomMutation.isPending}
              type="button"
              variant="secondary"
              onClick={runRandomPrediction}
            >
              {randomMutation.isPending ? 'Sampling...' : 'Random sample'}
            </Button>
          </div>
        </form>
      </Panel>

      <Panel title="Prediction result" eyebrow="Model output">
        {result ? (
          <PredictionDetails result={result} />
        ) : (
          <EmptyState text="Run a manual or random prediction to inspect severity, confidence, anomaly score, and top SHAP features." />
        )}
      </Panel>
    </section>
  )
}

function PredictionDetails({
  result,
}: {
  result: PredictResponse | PredictRandomResponse
}) {
  return (
    <div className="prediction-report">
      <div className="prediction-hero">
        <div>
          <p className="metric-label">Prediction</p>
          <strong>{result.prediction}</strong>
        </div>
        <SeverityBadge severity={result.severity} />
      </div>
      <dl className="prediction-metrics">
        <div className="prediction-metric">
          <dt>Confidence</dt>
          <dd>{formatPercent(result.confidence)}</dd>
        </div>
        <div className="prediction-metric">
          <dt>Anomaly score</dt>
          <dd>{formatNumber(result.anomaly_score)}</dd>
        </div>
        <div className="prediction-metric">
          <dt>Timestamp</dt>
          <dd>{formatDate(result.timestamp)}</dd>
        </div>
      </dl>
      <ExplanationText text={result.explanation_text} />
      <TopFeatures features={result.shap_top_features} />
    </div>
  )
}

function ExplanationText({ text }: { text: string }) {
  if (!text.trim()) {
    return <EmptyState text="No SHAP explanation returned." />
  }

  return (
    <section className="explanation-block">
      <div>
        <p className="metric-label">Model explanation</p>
        <h3>Decision rationale</h3>
      </div>
      <div className="explanation-copy">
        {formatExplanationText(text).map((item) => {
          if (item.kind === 'spacer') {
            return <span aria-hidden="true" className="explanation-spacer" key={item.key} />
          }

          if (item.kind === 'heading') {
            return <h4 key={item.key}>{item.text}</h4>
          }

          return (
            <p className={item.kind === 'bullet' ? 'explanation-bullet' : undefined} key={item.key}>
              {item.text}
            </p>
          )
        })}
      </div>
    </section>
  )
}

function TopFeatures({ features }: { features: ShapFeature[] }) {
  if (!features.length) {
    return <EmptyState text="No SHAP features returned." />
  }

  return (
    <div className="feature-list">
      <h3>Top SHAP features</h3>
      <ShapImpactChart features={features} />
      {features.map((feature, index) => (
        <div className="feature-row" key={feature.feature}>
          <span>
            <mark>{index + 1}</mark>
            {feature.feature}
          </span>
          <strong>{formatNumber(feature.impact)}</strong>
        </div>
      ))}
    </div>
  )
}

function parseFeatureJson(featureJson: string): ParsedFeatures {
  let parsed: unknown

  try {
    parsed = JSON.parse(featureJson)
  } catch {
    return { ok: false, error: 'Feature input must be valid JSON.' }
  }

  if (!isPlainObject(parsed)) {
    return { ok: false, error: 'Feature input must be a JSON object.' }
  }

  const features: Record<string, number> = {}

  for (const [key, value] of Object.entries(parsed)) {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      return {
        ok: false,
        error: `Feature "${key}" must be a finite number.`,
      }
    }

    features[key] = value
  }

  if (!Object.keys(features).length) {
    return { ok: false, error: 'Feature input must include at least one field.' }
  }

  return { ok: true, value: features }
}
