import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect, createContext, useContext } from 'react';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import Dashboard from './pages/Dashboard';
import Library from './pages/Library';
import Tasks from './pages/Tasks';
import Settings from './pages/Settings';
import Login from './pages/Login';
import { apiGet } from './utils/api';

interface AuthContextType {
  loggedIn: boolean;
  loading: boolean;
  checkAuth: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  loggedIn: false,
  loading: true,
  checkAuth: async () => {},
  logout: () => {},
});

export const useAuth = () => useContext(AuthContext);

const ThemedApp = () => {
  const { isDark } = useTheme();
  const { loggedIn, loading, checkAuth, logout } = useAuth();

  useEffect(() => {
    checkAuth();
  }, []);

  if (loading) {
    return null; // 或显示加载中
  }

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
          <Route path="/login" element={loggedIn ? <Navigate to="/" /> : <Login />} />
          <Route path="/" element={loggedIn ? <Layout onLogout={logout} /> : <Navigate to="/login" />}>
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
  const [authState, setAuthState] = useState({
    loggedIn: false,
    loading: true,
  });

  const checkAuth = async () => {
    try {
      const data = await apiGet<{ auth_enabled: boolean; logged_in: boolean }>('/api/auth/status');
      setAuthState({
        loggedIn: data.auth_enabled && data.logged_in,
        loading: false,
      });
    } catch {
      // 认证失败或未启用
      setAuthState({
        loggedIn: false,
        loading: false,
      });
    }
  };

  const logout = () => {
    localStorage.removeItem('token');
    setAuthState({
      loggedIn: false,
      loading: false,
    });
  };

  return (
    <ErrorBoundary>
      <ThemeProvider>
        <AuthContext.Provider value={{ ...authState, checkAuth, logout }}>
          <ThemedApp />
        </AuthContext.Provider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;