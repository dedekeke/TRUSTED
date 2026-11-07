import { Button, Result } from 'antd'
import { useNavigate } from 'react-router-dom'

export default function NotFound() {
  const navigate = useNavigate()
  return (
    <Result
      status="404"
      title="Page not found"
      extra={
        <Button type="primary" onClick={() => navigate('/')}>
          Back to overview
        </Button>
      }
    />
  )
}
