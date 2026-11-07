import { DatabaseOutlined, MenuOutlined, MoonOutlined, SunOutlined, TeamOutlined } from '@ant-design/icons'
import { Button, Tag, Tooltip } from 'antd'
import { usePipeline } from '@/hooks/usePipeline'
import { useTheme } from '@/hooks/useTheme'
import { TRUST_META } from '@/utils/constants'

export default function AppHeader({ onMenu }: { onMenu: () => void }) {
  const { dataset, scenario } = usePipeline()
  const { mode, toggle } = useTheme()
  return (
    <div className="flex h-full items-center gap-3">
      <Button type="text" icon={<MenuOutlined />} onClick={onMenu} className="lg:!hidden" aria-label="Open menu" />
      <div className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden">
        {dataset ? (
          <Tag icon={<DatabaseOutlined />} className="!m-0 max-w-[45%] truncate">
            {dataset.name} · {dataset.rows.length.toLocaleString()} rows
          </Tag>
        ) : (
          <span className="text-sm text-[var(--app-muted)]">No dataset loaded</span>
        )}
        {scenario && (
          <Tooltip title={scenario.title}>
            <Tag icon={<TeamOutlined />} color={TRUST_META[scenario.trust_level]?.color} className="!m-0 truncate">
              {scenario.id}
            </Tag>
          </Tooltip>
        )}
      </div>
      <Tooltip title={mode === 'dark' ? 'Light mode' : 'Dark mode'}>
        <Button
          type="text"
          icon={mode === 'dark' ? <SunOutlined /> : <MoonOutlined />}
          onClick={toggle}
          aria-label="Toggle theme"
        />
      </Tooltip>
    </div>
  )
}
