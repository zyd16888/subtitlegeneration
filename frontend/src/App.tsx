import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
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
          colorPrimary: '#1677ff',
          colorBgBase: isDark ? '#000000' : '#f0f2f5',
          colorBgContainer: isDark ? '#141414' : '#ffffff',
          colorBgElevated: isDark ? '#1f1f1f' : '#ffffff',
          borderRadius: 8,
          wireframe: false,
        },
        components: {
          Card: {
            colorBgContainer: isDark ? '#141414' : '#ffffff',
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
