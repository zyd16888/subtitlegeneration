import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import Dashboard from './pages/Dashboard';
import Library from './pages/Library';
import Tasks from './pages/Tasks';
import Settings from './pages/Settings';

const ThemedApp = () => {
  const { isDark } = useTheme();

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          colorPrimary: isDark ? '#00d4ff' : '#0891b2',
          colorBgBase: 'transparent',
          colorBgContainer: 'transparent',
          colorBgElevated: isDark ? '#111827' : '#ffffff',
          borderRadius: 10,
          wireframe: false,
          colorText: isDark ? '#f1f5f9' : '#1e293b',
          colorTextSecondary: isDark ? '#94a3b8' : '#64748b',
        },
        components: {
          Card: {
            colorBgContainer: 'transparent',
          },
          Layout: {
            bodyBg: 'transparent',
            headerBg: 'transparent',
            siderBg: 'transparent',
          },
        },
      }}
    >
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="library" element={<Library />} />
            <Route path="tasks" element={<Tasks />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
};

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <ThemedApp />
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;