import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import Dashboard from './pages/Dashboard';
import Library from './pages/Library';
import Tasks from './pages/Tasks';
import Settings from './pages/Settings';

/**
 * 应用主组件
 * 
 * 配置路由和全局设置
 * 使用 ErrorBoundary 捕获渲染错误
 * 采用暗黑模式和自定义主题色
 */
function App() {
  return (
    <ErrorBoundary>
      <ConfigProvider 
        locale={zhCN}
        theme={{
          algorithm: theme.darkAlgorithm,
          token: {
            colorPrimary: '#1677ff', // 科技蓝
            colorBgBase: '#000000', // 更深的背景
            colorBgContainer: '#141414', // 卡片背景
            colorBgElevated: '#1f1f1f', // 浮层背景
            borderRadius: 8, // 更圆润的边角
            wireframe: false,
          },
          components: {
            Card: {
              colorBgContainer: '#141414',
            },
            Layout: {
              bodyBg: '#000000',
              headerBg: 'transparent',
              siderBg: 'transparent',
            }
          }
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
    </ErrorBoundary>
  );
}

export default App;
