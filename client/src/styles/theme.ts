import { theme, type ThemeConfig } from 'antd'
import type { ThemeMode } from '@/context/ThemeContext'

export function antdTheme(mode: ThemeMode): ThemeConfig {
  return {
    algorithm: mode === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: '#2f54eb',
      borderRadius: 8,
      fontFamily: "'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    },
    components: {
      Layout: {
        headerBg: mode === 'dark' ? '#161a21' : '#ffffff',
        siderBg: mode === 'dark' ? '#161a21' : '#ffffff',
        bodyBg: 'transparent',
      },
      Menu: { itemBg: 'transparent' },
      Table: { cellPaddingBlockSM: 6 },
    },
  }
}
