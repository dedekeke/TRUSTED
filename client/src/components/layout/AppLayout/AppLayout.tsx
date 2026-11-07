import { useState } from 'react'
import { Drawer, Layout } from 'antd'
import { Outlet } from 'react-router-dom'
import AppHeader from '@/components/layout/AppHeader'
import Sidebar from '@/components/layout/Sidebar'

const { Sider, Header, Content } = Layout

export default function AppLayout() {
  const [drawer, setDrawer] = useState(false)
  return (
    <Layout className="min-h-screen">
      <Sider
        width={248}
        trigger={null}
        className="!fixed inset-y-0 left-0 z-20 hidden border-e border-[var(--app-border)] lg:!block"
      >
        <Sidebar />
      </Sider>
      <Drawer
        open={drawer}
        onClose={() => setDrawer(false)}
        placement="left"
        size={260}
        styles={{ body: { padding: 0 } }}
        closable={false}
      >
        <Sidebar onNavigate={() => setDrawer(false)} />
      </Drawer>
      <Layout className="lg:ms-[248px]">
        <Header className="sticky top-0 z-10 border-b border-[var(--app-border)] !px-4 sm:!px-6">
          <AppHeader onMenu={() => setDrawer(true)} />
        </Header>
        <Content className="mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-6">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
