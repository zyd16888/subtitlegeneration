import React, { useState } from 'react';
import { Layout as AntLayout, Menu, Button } from 'antd';
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

const Layout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems = [
    { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
    { key: '/library', icon: <FolderOutlined />, label: '媒体库' },
    { key: '/tasks', icon: <UnorderedListOutlined />, label: '任务管理' },
    { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
  ];

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key);
  };

  return (
    <AntLayout style={{ minHeight: '100vh', background: 'transparent' }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={260}
        style={{
          overflow: 'hidden',
          height: 'calc(100vh - 32px)',
          position: 'fixed',
          left: 16,
          top: 16,
          bottom: 16,
          borderRadius: 'var(--radius-card)',
          background: 'var(--glass-bg)',
          backdropFilter: 'blur(20px)',
          border: '1px solid var(--glass-border)',
          zIndex: 100,
          boxShadow: 'var(--glass-shadow)',
          transition: 'all var(--trans-base)',
        }}
      >
        <div
          style={{
            height: 72,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '0 20px',
            borderBottom: '1px solid var(--glass-border)',
          }}
        >
          <div
            style={{
              width: 36,
              height: 36,
              background: 'linear-gradient(135deg, var(--accent-cyan) 0%, #007bb5 100%)',
              borderRadius: '10px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'white',
              fontWeight: 'bold',
              fontSize: 20,
              marginRight: collapsed ? 0 : 12,
              flexShrink: 0,
              boxShadow: '0 0 16px rgba(0, 212, 255, 0.4)',
            }}
          >
            E
          </div>
          {!collapsed && (
            <div style={{
              color: 'var(--text-primary)',
              fontSize: 18,
              fontWeight: 600,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              letterSpacing: '0.5px'
            }}>
              Emby AI
            </div>
          )}
        </div>
        
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems.map(item => ({
            ...item,
            className: location.pathname === item.key ? 'nav-item-active' : ''
          }))}
          onClick={handleMenuClick}
          style={{
            background: 'transparent',
            padding: '16px 8px',
            border: 'none',
          }}
        />
        
        <div style={{ position: 'absolute', bottom: 16, width: '100%', padding: '0 16px' }}>
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
            style={{
              width: '100%',
              color: 'var(--text-secondary)',
              height: 44,
              background: 'rgba(255,255,255,0.02)',
              border: '1px solid var(--glass-border)',
            }}
          />
        </div>
      </Sider>
      
      <AntLayout style={{
        marginLeft: collapsed ? 80 + 32 : 260 + 32,
        transition: 'all var(--trans-base)',
        background: 'transparent',
        padding: '16px 16px 16px 0',
      }}>
        <Header
          className="glass-card"
          style={{
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 20,
            height: 72,
          }}
        >
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600, color: 'var(--text-primary)' }}>
            {menuItems.find(item => item.key === location.pathname)?.label || 'Dashboard'}
          </h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div className="status-dot active"></div>
            <span style={{ color: 'var(--accent-cyan)', fontSize: 13, fontWeight: 500, letterSpacing: '0.5px' }}>
              System Online
            </span>
          </div>
        </Header>
        
        <Content style={{ position: 'relative' }}>
          {/* Use key to remount and trigger animation on route change */}
          <div key={location.pathname} className="animate-fade-in-up" style={{ height: '100%' }}>
            <Outlet />
          </div>
        </Content>
      </AntLayout>
    </AntLayout>
  );
};

export default Layout;