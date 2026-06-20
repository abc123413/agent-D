import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { ProLayout } from '@ant-design/pro-components'
import { Button, Space, Dropdown } from 'antd'
import {
  DashboardOutlined,
  RobotOutlined,
  PlusCircleOutlined,
  SettingOutlined,
  UserOutlined,
  LogoutOutlined,
  AuditOutlined,
} from '@ant-design/icons'

const menuRoutes = {
  routes: [
    { path: '/dashboard', name: '监控总览', icon: <DashboardOutlined /> },
    { path: '/agents', name: 'Agent管理', icon: <RobotOutlined /> },
    { path: '/agents/create', name: '创建Agent', icon: <PlusCircleOutlined /> },
    { path: '/approvals', name: '审批中心', icon: <AuditOutlined /> },
    { path: '/settings', name: '系统设置', icon: <SettingOutlined /> },
  ],
}

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()

  const user = JSON.parse(localStorage.getItem('user') || '{}')

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    navigate('/login')
  }

  return (
    <ProLayout
      title="Agent Factory"
      logo={false}
      layout="mix"
      fixSiderbar
      route={menuRoutes}
      location={{ pathname: location.pathname }}
      menuItemRender={(item, dom) => (
        <div onClick={() => item.path && navigate(item.path)}>{dom}</div>
      )}
      contentStyle={{ padding: 24, minHeight: 'calc(100vh - 56px)' }}
      actionsRender={() => [
        <Dropdown
          key="user"
          menu={{
            items: [
              { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout },
            ],
          }}
        >
          <Button type="text" icon={<UserOutlined />}>
            {user.username || '用户'}
          </Button>
        </Dropdown>,
      ]}
    >
      <Outlet />
    </ProLayout>
  )
}
