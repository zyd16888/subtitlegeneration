import React, { useState } from 'react';
import { Layout as AntLayout, Menu, theme } from 'antd';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import {
  DashboardOutlined,
  FolderOutlined,
  UnorderedListOutlined,
  SettingOutlined,
} from '@ant-design/icons';

const { Header, Sider, Content } = AntLayout;

/**
 * 应用主布局组件
 * 
 * 使用 Ant Design Layout 组件实现侧边栏导航和顶部导航栏
 */
const Layout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  // 菜单项配置
  const menuItems = [
    {
      key: '/',
      icon: <DashboardOutlined />,
      label: 'Dashboard',
    },
    {
      key: '/library',
      icon: <FolderOutlined />,
      label: 'Library',
    },
    {
      key: '/tasks',
      icon: <UnorderedListOutlined />,
      label: 'Tasks',
    },
    {
      key: '/settings',
      icon: <SettingOutlined />,
      label: 'Settings',
    },
  ];

  // 处理菜单点击
  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key);
  };

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed}>
        <div
          style={{
            height: 32,
            margin: 16,
            color: 'white',
            fontSize: collapsed ? 16 : 20,
            fontWeight: 'bold',
            textAlign: 'center',
            transition: 'all 0.2s',
          }}
        >
          {collapsed ? 'ES' : 'Emby Subtitle'}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={handleMenuClick}
        />
      </Sider>
      <AntLayout>
        <Header
          style={{
            padding: '0 24px',
            background: colorBgContainer,
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <h2 style={{ margin: 0 }}>Emby AI 中文字幕生成服务</h2>
        </Header>
        <Content
          style={{
            margin: '24px 16px',
            padding: 24,
            minHeight: 280,
            background: colorBgContainer,
            borderRadius: borderRadiusLG,
          }}
        >
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  );
};

export default Layout;
