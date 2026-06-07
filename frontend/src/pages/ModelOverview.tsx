import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useState } from 'react'
import { Alert } from '../components/ui/alert'
import { Badge } from '../components/ui/badge'
import { Panel } from '../components/shared'
import { Skeleton } from '../components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrap,
} from '../components/ui/table'
import { backendConfig } from '../lib/config'
import { chartColors } from '../lib/constants'
import { useModelMetadataQuery } from '../lib/queries'
import type { DatasetFileStats, ModelMetadataResponse } from '../lib/types'
import { errorMessage } from '../lib/utils'

type HeroStat = {
  label: string
  value: string
}

type DatasetChartRow = {
  name: string
  filename: string
  benign: number
  attack: number
  total: number
}

type PlotCard = {
  title: string
  src: string
  description: string
}

type ModelComparisonRow = {
  model: string
  accuracy: string
  role: string
  active?: boolean
}

const plotBaseUrl = `${backendConfig.baseUrl}/model-plots`

const performancePlots: PlotCard[] = [
  {
    title: 'Confusion Matrix',
    src: `${plotBaseUrl}/confusion_matrix.png`,
    description:
      'Out of 348,368 benign samples, 347,971 were correctly identified. Out of 111,311 attack samples, 111,278 were correctly identified. False positives and false negatives are negligible at this scale.',
  },
  {
    title: 'ROC Curve (AUC = 1.0000)',
    src: `${plotBaseUrl}/roc_curve.png`,
    description:
      'The ROC curve plots the true positive rate against the false positive rate at every decision threshold. An AUC of 1.0 means the model perfectly separates benign from attack traffic on the test set.',
  },
  {
    title: 'Precision-Recall Curve',
    src: `${plotBaseUrl}/precision_recall_curve.png`,
    description:
      'Precision stays at 1.0 across almost the entire recall range, dropping only at the extreme end. This means the model raises very few false alarms while still catching the vast majority of attacks.',
  },
  {
    title: 'Calibration Curve',
    src: `${plotBaseUrl}/calibration_curve.png`,
    description:
      'A perfectly calibrated model sits on the dashed diagonal: when it predicts 70% confidence, it should be right 70% of the time. Isotonic calibration was applied to bring the raw ensemble closer to the ideal line, improving the reliability of the probability scores used for severity thresholding.',
  },
]

const fallbackDatasetFiles: DatasetFileStats[] = [
  {
    filename: 'Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv',
    total_rows: 225711,
    benign: 97686,
    attack: 128025,
  },
  {
    filename: 'Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv',
    total_rows: 286096,
    benign: 127292,
    attack: 158804,
  },
  {
    filename: 'Friday-WorkingHours-Morning.pcap_ISCX.csv',
    total_rows: 190911,
    benign: 188955,
    attack: 1956,
  },
  {
    filename: 'Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv',
    total_rows: 288395,
    benign: 288359,
    attack: 36,
  },
  {
    filename: 'Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv',
    total_rows: 170231,
    benign: 168051,
    attack: 2180,
  },
  {
    filename: 'Tuesday-WorkingHours.pcap_ISCX.csv',
    total_rows: 445645,
    benign: 431813,
    attack: 13832,
  },
  {
    filename: 'Wednesday-workingHours.pcap_ISCX.csv',
    total_rows: 691406,
    benign: 439683,
    attack: 251723,
  },
]

const knownDatasetLabels: Record<string, string> = {
  'Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv': 'Friday PM — DDoS',
  'Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv':
    'Friday PM — PortScan',
  'Friday-WorkingHours-Morning.pcap_ISCX.csv': 'Friday AM',
  'Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv':
    'Thursday PM — Infiltrate',
  'Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv':
    'Thursday AM — WebAttacks',
  'Tuesday-WorkingHours.pcap_ISCX.csv': 'Tuesday',
  'Wednesday-workingHours.pcap_ISCX.csv': 'Wednesday',
}

function formatAccuracy(value: number | null | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'Unknown'
  }

  const percentValue = value <= 1 ? value * 100 : value
  return `${percentValue.toFixed(2)}%`
}

function formatInteger(value: number | null | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'Unknown'
  }

  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 0,
  }).format(value)
}

function formatCount(value: unknown) {
  return typeof value === 'number' ? formatInteger(value) : String(value)
}

function formatDatasetLabel(filename: string) {
  if (knownDatasetLabels[filename]) {
    return knownDatasetLabels[filename]
  }

  return filename
    .replace(/\.pcap_ISCX\.csv$/i, '')
    .replace(/-WorkingHours/gi, '')
    .replace(/workingHours/gi, '')
    .replace(/-/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function getDatasetFiles(metadata: ModelMetadataResponse | undefined) {
  const loadedFiles = metadata?.dataset_source?.loaded_files

  if (Array.isArray(loadedFiles) && loadedFiles.length > 0) {
    return loadedFiles
  }

  return fallbackDatasetFiles
}

function buildDatasetRows(metadata: ModelMetadataResponse | undefined) {
  return getDatasetFiles(metadata).map((file) => ({
    name: formatDatasetLabel(file.filename),
    filename: file.filename,
    benign: file.benign,
    attack: file.attack,
    total: file.total_rows,
  }))
}

function sumDatasetRows(rows: DatasetChartRow[], key: 'benign' | 'attack' | 'total') {
  return rows.reduce((sum, row) => sum + row[key], 0)
}

function formatUtcDate(value: string | null | undefined) {
  if (!value) {
    return 'Unknown'
  }

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  const day = date.toLocaleString('en-GB', {
    day: '2-digit',
    timeZone: 'UTC',
  })
  const month = date.toLocaleString('en-GB', {
    month: 'short',
    timeZone: 'UTC',
  })
  const year = date.toLocaleString('en-GB', {
    year: 'numeric',
    timeZone: 'UTC',
  })
  const time = date.toLocaleString('en-GB', {
    hour: '2-digit',
    hour12: false,
    minute: '2-digit',
    timeZone: 'UTC',
  })

  return `${day} ${month} ${year}, ${time} UTC`
}

function ModelOverviewSkeleton() {
  return (
    <>
      <section className="model-hero page-panel" aria-label="Model overview loading">
        <div className="model-hero-copy">
          <Skeleton className="short" />
          <Skeleton className="medium" />
          <Skeleton />
          <Skeleton className="medium" />
        </div>
        <div className="model-stat-grid">
          {Array.from({ length: 4 }).map((_, index) => (
            <div className="model-stat-chip" key={index}>
              <Skeleton className="medium" />
              <Skeleton />
            </div>
          ))}
        </div>
      </section>
      <Panel eyebrow="Loading" title="Dataset breakdown">
        <div className="loading-stack">
          <Skeleton />
          <Skeleton />
          <Skeleton className="medium" />
        </div>
      </Panel>
    </>
  )
}

function ModelHeroStats({ stats }: { stats: HeroStat[] }) {
  return (
    <dl className="model-stat-grid">
      {stats.map((stat) => (
        <div className="model-stat-chip" key={stat.label}>
          <dt>{stat.label}</dt>
          <dd>{stat.value}</dd>
        </div>
      ))}
    </dl>
  )
}

function DatasetBreakdown({ metadata }: { metadata: ModelMetadataResponse | undefined }) {
  const datasetRows = buildDatasetRows(metadata)
  const totalRows = sumDatasetRows(datasetRows, 'total')
  const benignRows = sumDatasetRows(datasetRows, 'benign')
  const attackRows = sumDatasetRows(datasetRows, 'attack')
  const smoteBenign = metadata?.smote_class_counts?.benign
  const smoteAttack = metadata?.smote_class_counts?.attack

  return (
    <Panel
      bodyClassName="model-dataset-layout"
      eyebrow="Training Dataset"
      title="CICIDS2017 — Per-file Breakdown"
    >
        <div className="model-dataset-chart-block">
          <div className="model-dataset-chart">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart
                data={datasetRows}
                layout="vertical"
                margin={{ top: 4, right: 22, bottom: 4, left: 118 }}
              >
                <CartesianGrid stroke="#e4e7ec" strokeDasharray="3 3" />
                <XAxis
                  tick={{ fontSize: 12 }}
                  tickFormatter={formatCount}
                  type="number"
                />
                <YAxis
                  dataKey="name"
                  interval={0}
                  tick={{ fontSize: 12 }}
                  type="category"
                  width={154}
                />
                <Tooltip
                  formatter={(value, name) => [
                    formatCount(value),
                    name === 'benign' ? 'Benign' : 'Attack',
                  ]}
                />
                <Bar
                  dataKey="benign"
                  fill={chartColors.teal}
                  name="Benign"
                  stackId="rows"
                />
                <Bar
                  dataKey="attack"
                  fill={chartColors.amber}
                  name="Attack"
                  radius={[0, 6, 6, 0]}
                  stackId="rows"
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="model-muted-note">
            Thursday Infiltration contained only 36 attack samples out of
            288,395 rows, the most imbalanced file in the dataset.
          </p>
        </div>

        <aside className="model-dataset-summary" aria-label="Dataset summary">
          <dl className="model-summary-list">
            <div>
              <dt>Total rows</dt>
              <dd>{formatInteger(totalRows)}</dd>
            </div>
            <div>
              <dt>Benign</dt>
              <dd>{formatInteger(benignRows)}</dd>
            </div>
            <div>
              <dt>Attack</dt>
              <dd>{formatInteger(attackRows)}</dd>
            </div>
          </dl>
          <p>
            SMOTE was applied to the training split only, balancing benign and
            attack classes to {formatInteger(smoteBenign)} each before model
            training.
          </p>
          {smoteBenign !== smoteAttack && (
            <p className="model-muted-note">
              Latest metadata reports attack resampling at{' '}
              {formatInteger(smoteAttack)}.
            </p>
          )}
        </aside>
    </Panel>
  )
}

function PerformancePlotCard({ plot }: { plot: PlotCard }) {
  const [imageState, setImageState] = useState<'loading' | 'loaded' | 'error'>(
    'loading',
  )

  return (
    <article className="model-plot-card">
      <h3>{plot.title}</h3>
      <div className="model-plot-frame">
        {imageState === 'loading' && (
          <Skeleton className="model-plot-skeleton" aria-label={`${plot.title} loading`} />
        )}
        {imageState === 'error' && (
          <div className="model-plot-error" role="status">
            Plot not available — run train_model.py to generate.
          </div>
        )}
        <img
          alt={plot.title}
          className={imageState === 'loaded' ? 'is-loaded' : ''}
          onError={() => setImageState('error')}
          onLoad={() => setImageState('loaded')}
          src={plot.src}
        />
      </div>
      <p>{plot.description}</p>
    </article>
  )
}

function PerformancePlots() {
  return (
    <Panel
      bodyClassName="model-plot-grid"
      description="Evaluated on 459,679 samples (20% stratified split, never seen during training)"
      eyebrow="Model Evaluation"
      title="Performance on Held-Out Test Set"
    >
        {performancePlots.map((plot) => (
          <PerformancePlotCard key={plot.title} plot={plot} />
        ))}
    </Panel>
  )
}

function buildModelComparisonRows(
  metadata: ModelMetadataResponse | undefined,
): ModelComparisonRow[] {
  const rawAccuracy = metadata?.raw_accuracy

  return [
    {
      model: 'Random Forest',
      accuracy: formatAccuracy(rawAccuracy?.random_forest),
      role: 'Ensemble member',
    },
    {
      model: 'XGBoost',
      accuracy: formatAccuracy(rawAccuracy?.xgboost),
      role: 'Ensemble member',
    },
    {
      model: 'Ensemble (raw)',
      accuracy: formatAccuracy(rawAccuracy?.ensemble),
      role: 'Soft-voting combination',
    },
    {
      model: 'Ensemble (calibrated)',
      accuracy: formatAccuracy(metadata?.calibrated_accuracy),
      role: 'Used for predictions',
      active: true,
    },
  ]
}

function ModelComparison({ metadata }: { metadata: ModelMetadataResponse | undefined }) {
  const rows = buildModelComparisonRows(metadata)

  return (
    <Panel
      bodyClassName="model-comparison-body"
      eyebrow="Benchmarking"
      title="Individual Model Accuracy"
    >
        <TableWrap>
          <Table className="model-comparison-table">
            <TableHead>
              <TableRow>
                <TableHeader>Model</TableHeader>
                <TableHeader>Accuracy</TableHeader>
                <TableHeader>Role</TableHeader>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow
                  className={row.active ? 'model-active-row' : undefined}
                  key={row.model}
                >
                  <TableCell>
                    <span className="model-table-name">
                      {row.model}
                      {row.active && <Badge variant="success">Active</Badge>}
                    </span>
                  </TableCell>
                  <TableCell>
                    <strong>{row.accuracy}</strong>
                  </TableCell>
                  <TableCell>{row.role}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableWrap>
        <p className="model-muted-note">
          RF and XGBoost models are saved for benchmarking only. All predictions
          are made by the calibrated ensemble (CalibratedClassifierCV, isotonic,
          cv=5).
        </p>
    </Panel>
  )
}

export default function ModelOverviewPage() {
  const metadataQuery = useModelMetadataQuery()
  const metadata = metadataQuery.data

  if (metadataQuery.isLoading) {
    return <ModelOverviewSkeleton />
  }

  if (metadataQuery.isError) {
    return (
      <Alert variant="error">
        {errorMessage(metadataQuery.error) || 'Model metadata could not be loaded.'}
      </Alert>
    )
  }

  const stats: HeroStat[] = [
    {
      label: 'Calibrated Accuracy',
      value: formatAccuracy(metadata?.calibrated_accuracy),
    },
    {
      label: 'Training Rows',
      value: formatInteger(metadata?.train_count),
    },
    {
      label: 'Features',
      value: formatInteger(metadata?.feature_count),
    },
    {
      label: 'Trained At',
      value: formatUtcDate(metadata?.trained_at),
    },
  ]

  return (
    <>
      <section className="model-hero page-panel" aria-labelledby="model-overview-title">
        <div className="model-hero-copy">
          <p className="eyebrow">Purpose</p>
          <h2 id="model-overview-title">Argus-IDS Model Overview</h2>
          <p>
            Argus-IDS is a network intrusion detection system trained on the
            CICIDS2017 dataset. It combines a supervised ensemble classifier with
            an unsupervised anomaly detector to identify and severity-score
            malicious network traffic in real time.
          </p>
        </div>
        <ModelHeroStats stats={stats} />
      </section>
      <DatasetBreakdown metadata={metadata} />
      <PerformancePlots />
      <ModelComparison metadata={metadata} />
    </>
  )
}
