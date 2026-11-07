import { FolderOpenOutlined, InboxOutlined, PlayCircleOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Input,
  InputNumber,
  Progress,
  Segmented,
  Select,
  Switch,
  Tag,
  Upload,
} from 'antd'
import { useMemo, useState } from 'react'
import { useFetch } from '@/hooks/useFetch'
import { api, ApiError, backend, jobs } from '@/services/api'
import type { Job } from '@/types/job.types'

type Source = 'bundled' | 'files'

const specTemplate = (dataset: string) =>
  JSON.stringify(
    {
      dataset,
      trust_level: 'internal',
      targets: { k: 5 },
      required: [{ column: 'table.column', task: 'T-1' }],
    },
    null,
    2,
  )

function folderName(files: File[]) {
  const rel = (files[0] as File & { webkitRelativePath?: string })?.webkitRelativePath ?? ''
  return rel.includes('/') ? rel.split('/')[0] : ''
}

/** Choose the data (bundled dataset or browsed CSV files), the sharing scenario and the options, then run. */
export default function NewRunForm({ onStarted }: { onStarted: (job: Job) => void }) {
  const { data: datasets } = useFetch(backend.datasets)
  const { data: scenarios } = useFetch(api.scenarios)
  const [source, setSource] = useState<Source>('bundled')
  const [dataset, setDataset] = useState<string | null>(null)
  const [files, setFiles] = useState<File[]>([])
  const [uploadName, setUploadName] = useState('')
  const [scenario, setScenario] = useState<string | null>(null)
  const [spec, setSpec] = useState('')
  const [budget, setBudget] = useState(50)
  const [llm, setLlm] = useState(false)
  const [allowUnapproved, setAllowUnapproved] = useState(false)
  const [progress, setProgress] = useState<{ file: string; share: number; done: number } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  const name = source === 'bundled' ? dataset : uploadName || folderName(files)
  const options = useMemo(() => (scenarios ?? []).filter((s) => s.dataset === name), [scenarios, name])
  const chosen = options.find((s) => s.id === scenario) ?? null
  const needsSpec = !!name && !options.length
  const csvs = files.filter((f) => f.name.toLowerCase().endsWith('.csv'))
  const ready = !!name && (source === 'bundled' || csvs.length > 0) && (needsSpec ? !!spec.trim() : !!chosen)

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      let parsedSpec: Record<string, unknown> | undefined
      if (needsSpec) {
        try {
          parsedSpec = JSON.parse(spec)
        } catch {
          throw new ApiError('bad_spec', 'The requirement spec is not valid JSON')
        }
      }
      const job = await jobs.create(source === 'bundled' ? { dataset: name! } : { upload: name! })
      if (source === 'files') {
        for (const [i, f] of csvs.entries()) {
          setProgress({ file: f.name, share: 0, done: i })
          await jobs.upload(job.id, f, (share) => setProgress({ file: f.name, share, done: i }))
        }
        setProgress(null)
      }
      onStarted(
        await jobs.start(job.id, {
          ...(needsSpec ? { spec: parsedSpec } : { scenario: chosen!.id }),
          budget,
          llm,
          allow_unapproved: allowUnapproved,
        }),
      )
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError('network', String(e)))
    } finally {
      setBusy(false)
      setProgress(null)
    }
  }

  const totalMb = csvs.reduce((n, f) => n + f.size, 0) / 2 ** 20

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card size="small" title="1 · Data" className="lg:col-span-1">
        <Segmented
          block
          value={source}
          onChange={(v) => {
            setSource(v as Source)
            setScenario(null)
          }}
          options={[
            { value: 'bundled', label: 'Bundled dataset' },
            { value: 'files', label: 'Browse files', icon: <FolderOpenOutlined /> },
          ]}
        />
        <div className="mt-3">
          {source === 'bundled' ? (
            <Select
              className="w-full"
              placeholder="Choose a dataset"
              value={dataset}
              onChange={(v) => {
                setDataset(v)
                setScenario(null)
              }}
              options={(datasets ?? []).map((d) => ({ value: d, label: d }))}
            />
          ) : (
            <div className="space-y-2">
              <Upload.Dragger
                directory
                multiple
                accept=".csv"
                showUploadList={false}
                beforeUpload={(file, list) => {
                  if (file === list[0]) {
                    setFiles(list as unknown as File[])
                    setScenario(null)
                    setUploadName('')
                  }
                  return false
                }}
              >
                <p className="ant-upload-drag-icon">
                  <InboxOutlined />
                </p>
                <p className="text-sm">Click or drop a folder of CSV files</p>
                <p className="text-xs text-[var(--app-muted)]">
                  One folder = one dataset. Files stay on this machine: they go to the local API only.
                </p>
              </Upload.Dragger>
              {!!csvs.length && (
                <>
                  <div className="text-xs text-[var(--app-muted)]">
                    {csvs.length} CSV file{csvs.length > 1 ? 's' : ''} · {totalMb.toFixed(1)} MB
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {csvs.map((f) => (
                      <Tag key={f.name} className="mono !m-0 text-xs">
                        {f.name}
                      </Tag>
                    ))}
                  </div>
                  <Input
                    addonBefore="Dataset name"
                    value={uploadName || folderName(files)}
                    onChange={(e) => setUploadName(e.target.value.replace(/[^A-Za-z0-9_-]/g, ''))}
                  />
                </>
              )}
            </div>
          )}
        </div>
      </Card>

      <Card size="small" title="2 · Sharing scenario" className="lg:col-span-1">
        {!name && <div className="text-sm text-[var(--app-muted)]">Choose the data first.</div>}
        {!!options.length && (
          <>
            <Select
              className="w-full"
              placeholder="Who receives the data, and why?"
              value={scenario}
              onChange={setScenario}
              options={options.map((s) => ({ value: s.id, label: `${s.id} · ${s.title}` }))}
            />
            {chosen && (
              <Descriptions size="small" column={1} className="mt-3" styles={{ label: { width: 92 } }}>
                <Descriptions.Item label="Recipient">{chosen.recipient}</Descriptions.Item>
                <Descriptions.Item label="Purpose">{chosen.purpose}</Descriptions.Item>
                <Descriptions.Item label="Trust">
                  <Tag className="!m-0">{chosen.trust_level}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Targets">
                  <span className="text-xs">{chosen.suggested_privacy_targets}</span>
                </Descriptions.Item>
              </Descriptions>
            )}
          </>
        )}
        {needsSpec && (
          <div className="space-y-2">
            <Alert
              type="info"
              showIcon
              title="No bundled scenario for this dataset name"
              description="Describe the purpose as a requirement spec: trust level, privacy targets and the columns each task needs."
            />
            <Input.TextArea
              className="mono !text-xs"
              rows={9}
              value={spec || specTemplate(name!)}
              onChange={(e) => setSpec(e.target.value)}
            />
          </div>
        )}
      </Card>

      <Card size="small" title="3 · Options" className="lg:col-span-1">
        <div className="space-y-3 text-sm">
          <div className="flex items-center justify-between gap-2">
            <span>Search budget (evaluations)</span>
            <InputNumber min={1} max={500} value={budget} onChange={(v) => setBudget(v ?? 50)} />
          </div>
          <div className="flex items-center justify-between gap-2">
            <span>Local LLM tier in Detect (Ollama)</span>
            <Switch checked={llm} onChange={setLlm} />
          </div>
          <div className="flex items-center justify-between gap-2">
            <span>Export even if not approved</span>
            <Switch checked={allowUnapproved} onChange={setAllowUnapproved} />
          </div>
          {allowUnapproved && (
            <Alert type="warning" showIcon title="The export is marked NOT_APPROVED and is not a release." />
          )}
          <div className="text-xs text-[var(--app-muted)]">
            Defaults equal the CLI (`python -m server.pipeline`): a run here produces the same files.
          </div>
        </div>
        {progress && (
          <div className="mt-3 text-xs">
            Uploading {progress.file} ({progress.done + 1}/{csvs.length})
            <Progress percent={Math.round(progress.share * 100)} size="small" />
          </div>
        )}
        {error && <Alert className="!mt-3" showIcon type="error" title={error.code} description={error.message} />}
        <Button
          className="!mt-4"
          block
          type="primary"
          size="large"
          icon={<PlayCircleOutlined />}
          disabled={!ready}
          loading={busy}
          onClick={run}
        >
          Run pipeline
        </Button>
      </Card>
    </div>
  )
}
