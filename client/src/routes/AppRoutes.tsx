import { Route, Routes } from 'react-router-dom'
import AppLayout from '@/components/layout/AppLayout'
import Benchmark from '@/pages/Benchmark'
import Detect from '@/pages/Detect'
import Evaluate from '@/pages/Evaluate'
import Home from '@/pages/Home'
import NotFound from '@/pages/NotFound'
import Protect from '@/pages/Protect'
import Scenarios from '@/pages/Scenarios'

export default function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Home />} />
        <Route path="detect" element={<Detect />} />
        <Route path="protect" element={<Protect />} />
        <Route path="evaluate" element={<Evaluate />} />
        <Route path="scenarios" element={<Scenarios />} />
        <Route path="benchmark" element={<Benchmark />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
