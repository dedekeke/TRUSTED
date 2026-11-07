import { CloudUploadOutlined, TableOutlined } from '@ant-design/icons'
import { App, Card, Tag, Upload } from 'antd'
import { useState } from 'react'
import { api } from '@/services/api'
import { parseCsvFile, parseCsvText } from '@/services/csvService'
import { useFetch } from '@/hooks/useFetch'
import { usePipeline } from '@/hooks/usePipeline'
import { appConfig } from '@/config/appConfig'

export default function DatasetPicker() {
  const { message } = App.useApp()
  const { dataset, loadDataset } = usePipeline()
  const { data: samples } = useFetch(api.samples)
  const [loading, setLoading] = useState<string | null>(null)

  const pickSample = async (id: string) => {
    const s = samples?.find((x) => x.id === id)
    if (!s) return
    setLoading(id)
    try {
      const { columns, rows } = parseCsvText(await api.sampleCsv(id))
      loadDataset({
        id,
        name: `${s.dataset}/${s.table}`,
        dataset: s.dataset === 'unseen' ? undefined : s.dataset,
        table: s.table,
        columns,
        rows,
        source: 'sample',
      })
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {samples?.map((s) => (
          <Card
            key={s.id}
            size="small"
            hoverable
            loading={loading === s.id}
            onClick={() => pickSample(s.id)}
            className={dataset?.id === s.id ? '!border-[var(--app-accent)] !shadow-[0_0_0_1px_var(--app-accent)]' : ''}
          >
            <div className="flex items-start gap-3">
              <TableOutlined className="mt-1 text-lg text-[var(--app-accent)]" />
              <div className="min-w-0">
                <div className="mono truncate text-sm font-semibold">
                  {s.dataset}/{s.table}
                </div>
                <div className="line-clamp-2 text-xs text-[var(--app-muted)]">{s.label}</div>
                <div className="mt-2 flex gap-1">
                  <Tag className="!m-0">{s.rows} rows</Tag>
                  {s.dataset === 'unseen' && (
                    <Tag color="gold" className="!m-0">
                      no labels
                    </Tag>
                  )}
                </div>
              </div>
            </div>
          </Card>
        ))}
      </div>
      <Upload.Dragger
        accept=".csv,text/csv"
        showUploadList={false}
        beforeUpload={async (file) => {
          try {
            const { columns, rows, truncated } = await parseCsvFile(file)
            if (!columns.length) throw new Error('no header row found')
            loadDataset({ id: `upload:${file.name}`, name: file.name, columns, rows, source: 'upload' })
            if (truncated)
              message.info(
                `Only the first ${appConfig.maxUploadRows.toLocaleString()} rows are used in the browser preview`,
              )
          } catch (e) {
            message.error(`Could not read ${file.name}: ${e instanceof Error ? e.message : e}`)
          }
          return false
        }}
      >
        <p className="ant-upload-drag-icon">
          <CloudUploadOutlined />
        </p>
        <p className="ant-upload-text">Drop your own CSV</p>
        <p className="ant-upload-hint px-4">Parsed in your browser, values kept as text. Nothing is uploaded.</p>
      </Upload.Dragger>
    </div>
  )
}
