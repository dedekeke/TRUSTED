import { useEffect } from 'react'
import { App } from 'antd'
import { useBlocker } from 'react-router-dom'
import { jobs } from '@/services/api'

export function useLeaveGuard(id: string, running: boolean) {
  const { modal } = App.useApp()
  const blocker = useBlocker(
    ({ currentLocation: a, nextLocation: b }) => running && (a.pathname !== b.pathname || a.search !== b.search),
  )

  useEffect(() => {
    if (blocker.state !== 'blocked') return
    modal.confirm({
      title: 'Leave this page?',
      content: 'The pipeline is still running. Leaving stops it and its progress will not be saved.',
      okText: 'Leave and stop',
      okButtonProps: { danger: true },
      cancelText: 'Stay',
      onOk: async () => {
        await jobs.cancel(id).catch(() => undefined)
        blocker.proceed()
      },
      onCancel: () => blocker.reset(),
    })
  }, [blocker, id, modal])

  useEffect(() => {
    if (!running) return

    const warn = (e: BeforeUnloadEvent) => e.preventDefault()
    const stop = () => void jobs.cancel(id, true).catch(() => undefined)
    window.addEventListener('beforeunload', warn)
    window.addEventListener('pagehide', stop)
    return () => {
      window.removeEventListener('beforeunload', warn)
      window.removeEventListener('pagehide', stop)
    }
  }, [id, running])
}
