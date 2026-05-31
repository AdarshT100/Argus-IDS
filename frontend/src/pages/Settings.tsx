import { Panel } from '../components/shared'
import { backendUrl } from '../lib/config'

export default function SettingsPage() {
  return (
    <Panel title="Runtime settings" eyebrow="Frontend configuration">
      <dl className="settings-list">
        <div>
          <dt>Backend base URL</dt>
          <dd>{backendUrl}</dd>
        </div>
        <div>
          <dt>Local frontend origin</dt>
          <dd>http://localhost:5173</dd>
        </div>
        <div>
          <dt>API data layer</dt>
          <dd>TanStack Query with one retry and no window-focus refetch.</dd>
        </div>
      </dl>
    </Panel>
  )
}
