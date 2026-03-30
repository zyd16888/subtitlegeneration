import React, { useState } from 'react';
import { Layout as AntLayout, Menu, theme, Button, Tooltip } from 'antd';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import {
  DashboardOutlined,
  FolderOutlined,
  UnorderedListOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SunOutlined,
  MoonOutlined,
} from '@ant-design/icons';
import { useTheme } from '../contexts/ThemeContext';

const { Header, Sider, Content } = AntLayout;

const Layout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { isDark, toggleTheme } = useTheme();
  const {
    token: { borderRadiusLG },
  } = theme.useToken();

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
        width={240}
        style={{
          overflow: 'auto',
          height: 'calc(100vh - 32px)',
          position: 'fixed',
          left: 16,
          top: 16,
          bottom: 16,
          borderRadius: borderRadiusLG,
          background: 'var(--glass-bg)',
          backdropFilter: 'blur(16px)',
          border: '1px solid var(--glass-border)',
          zIndex: 100,
          boxShadow: 'var(--glass-shadow)',
          transition: 'background 0.3s, border-color 0.3s, box-shadow 0.3s',
        }}
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '0 16px',
            borderBottom: '1px solid var(--border-color-subtle)',
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
              color: 'var(--text-primary)',
              fontSize: 16,
              fontWeight: 600,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}>
              Emby Subtitle
            </div>
          )}
        </div>
        <Menu
          theme={isDark ? 'dark' : 'light'}
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={handleMenuClick}
          style={{
            background: 'transparent',
            padding: '8px',
            border: 'none',
          }}
        />
        <div style={{ position: 'absolute', bottom: 16, width: '100%', padding: '0 8px' }}>
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
            style={{
              width: '100%',
              color: 'var(--text-secondary)',
              height: 40,
            }}
          />
        </div>
      </Sider>
      <AntLayout style={{
        marginLeft: collapsed ? 80 + 32 : 240 + 32,
        transition: 'all 0.2s',
        background: 'transparent',
        padding: '16px 16px 16px 0',
      }}>
        <Header
          style={{
            padding: '0 24px',
            background: 'var(--glass-bg-light)',
            backdropFilter: 'blur(16px)',
            borderRadius: borderRadiusLG,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            border: '1px solid var(--glass-border)',
            marginBottom: 16,
            height: 64,
            transition: 'background 0.3s, border-color 0.3s',
          }}
        >
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 500, color: 'var(--text-primary)' }}>
            {menuItems.find(item => item.key === location.pathname)?.label || 'Dashboard'}
          </h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
              Emby AI 中文字幕生成服务
            </span>
            <Tooltip title={isDark ? '切换到亮色模式' : '切换到暗色模式'}>
              <Button
                type="text"
                icon={isDark ? <SunOutlined /> : <MoonOutlined />}
                onClick={toggleTheme}
                style={{
                  color: 'var(--text-secondary)',
                  fontSize: 18,
                  width: 36,
                  height: 36,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              />
            </Tooltip>
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
