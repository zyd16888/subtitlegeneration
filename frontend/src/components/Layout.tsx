import React, { useState } from 'react';
import { Layout as AntLayout, Menu, theme, Button } from 'antd';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import {
  DashboardOutlined,
  FolderOutlined,
  UnorderedListOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons';

const { Header, Sider, Content } = AntLayout;

/**
 * 应用主布局组件
 * 
 * 采用悬浮侧边栏和毛玻璃设计
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
      label: '仪表盘',
    },
    {
      key: '/library',
      icon: <FolderOutlined />,
      label: '媒体库',
    },
    {
      key: '/tasks',
      icon: <UnorderedListOutlined />,
      label: '任务管理',
    },
    {
      key: '/settings',
      icon: <SettingOutlined />,
      label: '系统设置',
    },
  ];

  // 处理菜单点击
  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key);
  };

  return (
    <AntLayout style={{ minHeight: '100vh', background: 'transparent' }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={240}
        style={{
          overflow: 'auto',
          height: 'calc(100vh - 32px)',
          position: 'fixed',
          left: 16,
          top: 16,
          bottom: 16,
          borderRadius: borderRadiusLG,
          background: 'rgba(20, 20, 20, 0.7)',
          backdropFilter: 'blur(16px)',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          zIndex: 100,
          boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.4)',
        }}
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '0 16px',
            borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
          }}
        >
          <div
            style={{
              width: 32,
              height: 32,
              background: 'linear-gradient(135deg, #1677ff 0%, #722ed1 100%)',
              borderRadius: 8,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'white',
              fontWeight: 'bold',
              fontSize: 18,
              marginRight: collapsed ? 0 : 12,
              flexShrink: 0,
            }}
          >
            E
          </div>
          {!collapsed && (
            <div style={{ 
              color: 'white', 
              fontSize: 16, 
              fontWeight: 600, 
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis'
            }}>
              Emby Subtitle
            </div>
          )}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={handleMenuClick}
          style={{ 
            background: 'transparent', 
            padding: '8px', 
            border: 'none' 
          }}
        />
        <div style={{ position: 'absolute', bottom: 16, width: '100%', padding: '0 8px' }}>
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
            style={{
              width: '100%',
              color: 'rgba(255, 255, 255, 0.45)',
              height: 40,
            }}
          />
        </div>
      </Sider>
      <AntLayout style={{ 
        marginLeft: collapsed ? 80 + 32 : 240 + 32, 
        transition: 'all 0.2s',
        background: 'transparent',
        padding: '16px 16px 16px 0'
      }}>
        <Header
          style={{
            padding: '0 24px',
            background: 'rgba(20, 20, 20, 0.5)',
            backdropFilter: 'blur(16px)',
            borderRadius: borderRadiusLG,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            marginBottom: 16,
            height: 64,
          }}
        >
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 500 }}>
            {menuItems.find(item => item.key === location.pathname)?.label || 'Dashboard'}
          </h2>
          <div style={{ color: 'rgba(255, 255, 255, 0.45)', fontSize: 12 }}>
            Emby AI 中文字幕生成服务
          </div>
        </Header>
        <Content
          style={{
            minHeight: 280,
            transition: 'all 0.2s',
          }}
        >
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  );
};

export default Layout;
