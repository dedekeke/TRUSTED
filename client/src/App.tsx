import { StyleProvider } from '@ant-design/cssinjs'
import { App as AntApp, ConfigProvider } from 'antd'
import { PipelineProvider } from '@/context/PipelineContext'
import { ThemeProvider } from '@/context/ThemeContext'
import { useTheme } from '@/hooks/useTheme'
import AppRoutes from '@/routes/AppRoutes'
import { antdTheme } from '@/styles/theme'

function Themed() {
  const { mode } = useTheme()
  return (
    <ConfigProvider theme={antdTheme(mode)}>
      <AntApp>
        <PipelineProvider>
          <AppRoutes />
        </PipelineProvider>
      </AntApp>
    </ConfigProvider>
  )
}

export default function App() {
  return (
    // `layer` puts Ant Design's CSS in @layer antd so Tailwind utilities can override it
    <StyleProvider layer>
      <ThemeProvider>
        <Themed />
      </ThemeProvider>
    </StyleProvider>
  )
}
