import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Typography, Space, Progress, Spin, Tag, Empty } from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
  SyncOutlined,
  ClockCircleOutlined,
  ApiOutlined,
  TranslationOutlined,
  AudioOutlined,
  HistoryOutlined,
  ThunderboltFilled,
} from '@ant-design/icons';
import { api } from '../services/api';
import type { Statistics, Task, TaskStatus } from '../types/api';

const { Text } = Typography;

// Custom hook for rolling numbers
const useRollingNumber = (endValue: number, duration: number = 800) => {
  const [value, setValue] = useState(0);
  const startTime = useRef<number | null>(null);
  const startValue = useRef(0);

  useEffect(() => {
    startValue.current = value;
    startTime.current = null;
    let animationFrame: number;

    const animate = (timestamp: number) => {
      if (!startTime.current) startTime.current = timestamp;
      const progress = timestamp - startTime.current;
      const percentage = Math.min(progress / duration, 1);
      
      // Easing function (easeOutExpo)
      const easePercentage = percentage === 1 ? 1 : 1 - Math.pow(2, -10 * percentage);
      
      setValue(Math.floor(startValue.current + (endValue - startValue.current) * easePercentage));

      if (percentage < 1) {
        animationFrame = requestAnimationFrame(animate);
      } else {
        setValue(endValue);
      }
    };

    animationFrame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationFrame);
  }, [endValue, duration]);

  return value;
};

const StatCard: React.FC<{
  title: string;
  value: number;
  icon: React.ReactNode;
  color: string;
  delayClass: string;
}> = ({ title, value, icon, color, delayClass }) => {
  const animatedValue = useRollingNumber(value);
  
  return (
    <div className={`glass-card animate-fade-in-up ${delayClass}`} style={{ height: '100%', padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 8, fontWeight: 500 }}>
            {title}
          </div>
          <div className="number-font" style={{ color: 'var(--text-primary)', fontSize: 32, fontWeight: 700 }}>
            {animatedValue.toLocaleString()}
          </div>
        </div>
        <div style={{
          width: 48,
          height: 48,
          borderRadius: 12,
          background: `${color}15`,
          color: color,
          fontSize: 24,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: `0 0 16px ${color}20 inset`
        }}>
          {icon}
        </div>
      </div>
      <div style={{ marginTop: 20, display: 'flex', alignItems: 'center', gap: 6 }}>
        <span className="status-dot success" />
        <span style={{ 
          color: 'var(--accent-emerald)', 
          fontSize: 12, 
          fontWeight: 500,
          animation: 'pulseGlowGreen 2s infinite',
          opacity: 0.8 
        }}>
          实时更新中
        </span>
      </div>
    </div>
  );
};

const StatusNode: React.FC<{
  icon: React.ReactNode;
  label: string;
  status: boolean;
  message: string;
  isLast?: boolean;
}> = ({ icon, label, status, message, isLast }) => (
  <div style={{ position: 'relative' }}>
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      padding: '16px',
      borderRadius: 'var(--radius-inner)',
      background: 'var(--bg-subtle)',
      border: '1px solid var(--glass-border)',
      marginBottom: isLast ? 0 : 24,
      transition: 'all var(--trans-base)',
      position: 'relative',
      zIndex: 2,
    }}
    className="hover:border-var(--accent-cyan)"
    >
      <div style={{
        fontSize: 24,
        color: status ? 'var(--accent-emerald)' : 'var(--accent-rose)',
        background: status ? 'var(--accent-emerald-bg)' : 'var(--accent-rose-bg)',
        padding: 12,
        borderRadius: 10,
        display: 'flex',
        boxShadow: status ? 'var(--accent-emerald-glow)' : 'var(--accent-rose-glow)',
      }}>
        {icon}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>{label}</div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>{message}</div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        {status ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'var(--accent-emerald-bg)', padding: '4px 10px', borderRadius: 20, border: '1px solid var(--accent-emerald-border)' }}>
            <span className="status-dot success" style={{ margin: 0, width: 6, height: 6 }} />
            <span style={{ color: 'var(--accent-emerald)', fontSize: 12, fontWeight: 500 }}>在线</span>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'var(--accent-rose-bg)', padding: '4px 10px', borderRadius: 20, border: '1px solid var(--accent-rose-border)' }}>
            <span className="status-dot error" style={{ margin: 0, width: 6, height: 6 }} />
            <span style={{ color: 'var(--accent-rose)', fontSize: 12, fontWeight: 500 }}>离线</span>
          </div>
        )}
      </div>
    </div>
    
    {!isLast && (
      <div style={{
        position: 'absolute',
        left: 36,
        top: 64,
        width: 2,
        height: 24,
        background: 'var(--glass-border)',
        zIndex: 1,
      }}>
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '50%',
          background: status ? 'linear-gradient(180deg, transparent, var(--accent-emerald))' : 'linear-gradient(180deg, transparent, var(--accent-rose))',
          animation: 'dataFlow 1.5s linear infinite',
          opacity: 0.6,
        }} />
      </div>
    )}
  </div>
);

const Dashboard: React.FC = () => {
  const [statistics, setStatistics] = useState<Statistics | null>(null);
  const [processingTasks, setProcessingTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    try {
      const statsData = await api.stats.getStatistics();
      const processingData = await api.tasks.getTasks({ status: 'processing' as TaskStatus, limit: 10 });
      setStatistics(statsData);
      setProcessingTasks(processingData.items);
    } catch (err: any) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 3000);
    return () => clearInterval(interval);
  }, []);

  const getStatusTag = (status: TaskStatus) => {
    const configs = {
      pending: { color: 'default', text: '待处理', icon: <ClockCircleOutlined /> },
      processing: { color: 'processing', text: '处理中', icon: <SyncOutlined spin /> },
      completed: { color: 'success', text: '已完成', icon: <CheckCircleFilled /> },
      failed: { color: 'error', text: '失败', icon: <CloseCircleFilled /> },
      cancelled: { color: 'default', text: '已取消', icon: <CloseCircleFilled /> },
    };
    const config = configs[status];
    return <Tag color={config.color} icon={config.icon} style={{ borderRadius: 6, border: 'none', background: 'var(--bg-tag)' }}>{config.text}</Tag>;
  };

  if (loading && !statistics) {
    return (
      <div style={{ height: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 16 }}>
        <Spin size="large" />
        <Text style={{ color: 'var(--text-secondary)' }}>正在初始化神经中枢...</Text>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto' }}>
      <Row gutter={[20, 20]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <StatCard delayClass="delay-1" title="任务总数" value={statistics?.task_statistics.total || 0} icon={<HistoryOutlined />} color="var(--accent-cyan)" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard delayClass="delay-2" title="成功生成" value={statistics?.task_statistics.completed || 0} icon={<CheckCircleFilled />} color="var(--accent-emerald)" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard delayClass="delay-3" title="正在处理" value={statistics?.task_statistics.processing || 0} icon={<SyncOutlined />} color="var(--accent-amber)" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard delayClass="delay-4" title="异常任务" value={statistics?.task_statistics.failed || 0} icon={<ThunderboltFilled />} color="var(--accent-rose)" />
        </Col>
      </Row>

      <Row gutter={[20, 20]}>
        <Col xs={24} lg={10}>
          <Space direction="vertical" size={20} style={{ width: '100%' }}>
            <div className="glass-card animate-fade-in-up delay-4" style={{ padding: 20 }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8 }}>
                <ApiOutlined style={{ color: 'var(--accent-cyan)' }} /> 节点连接拓扑
              </div>
              <StatusNode
                icon={<ApiOutlined />}
                label="Emby 服务器节点"
                status={statistics?.system_status.emby_connected || false}
                message={statistics?.system_status.emby_message || '持续同步数据流'}
              />
              <StatusNode
                icon={<AudioOutlined />}
                label="ASR 推理引擎"
                status={statistics?.system_status.asr_configured || false}
                message={statistics?.system_status.asr_message || '模型已加载并就绪'}
              />
              <StatusNode
                icon={<TranslationOutlined />}
                label="神经翻译服务"
                status={statistics?.system_status.translation_configured || false}
                message={statistics?.system_status.translation_message || 'API通道活跃'}
                isLast
              />
            </div>

            {processingTasks.length > 0 && (
              <div className="glass-card animate-fade-in-up delay-5" style={{ padding: 20 }}>
                <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <SyncOutlined spin style={{ color: 'var(--accent-amber)' }} /> 实时任务流
                </div>
                {processingTasks.map(task => (
                  <div key={task.id} style={{ marginBottom: 16, background: 'var(--bg-subtle)', padding: 12, borderRadius: 8, border: '1px solid var(--glass-border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                      <Text ellipsis style={{ maxWidth: '80%', fontSize: 13, color: 'var(--text-primary)' }}>{task.media_item_title}</Text>
                      <Text className="number-font" style={{ fontSize: 12, color: 'var(--accent-cyan)' }}>{task.progress}%</Text>
                    </div>
                    <Progress
                      percent={task.progress}
                      size="small"
                      strokeColor={{ '0%': 'var(--accent-cyan)', '100%': '#007bb5' }}
                      trailColor="var(--progress-trail)"
                      showInfo={false}
                      status="active"
                    />
                  </div>
                ))}
              </div>
            )}
          </Space>
        </Col>

        <Col xs={24} lg={14}>
          <div className="glass-card animate-fade-in-up delay-5" style={{ height: '100%', padding: 20 }}>
            <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8 }}>
              <HistoryOutlined style={{ color: 'var(--accent-cyan)' }} /> 活动审计日志
            </div>
            
            {(!statistics?.recent_tasks || statistics.recent_tasks.length === 0) ? (
              <Empty 
                image={Empty.PRESENTED_IMAGE_SIMPLE} 
                description={<span style={{ color: 'var(--text-weak)' }}>暂无活动数据流</span>}
                style={{ margin: '60px 0' }}
              />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {statistics.recent_tasks.map((task: any, index: number) => (
                  <div key={task.id} style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'space-between',
                    padding: '12px 16px',
                    background: 'var(--bg-subtle)',
                    border: '1px solid var(--glass-border)',
                    borderRadius: 8,
                    transition: 'all var(--trans-fast)',
                    animation: `fadeInUp 0.4s var(--ease-spring) ${index * 0.1}s both`
                  }} className="hover:bg-opacity-5">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 16, flex: 1, minWidth: 0 }}>
                      {getStatusTag(task.status)}
                      <Text ellipsis style={{ color: 'var(--text-primary)', fontSize: 14 }}>{task.media_item_title}</Text>
                    </div>
                    <div className="number-font" style={{ color: 'var(--text-secondary)', fontSize: 13, paddingLeft: 16 }}>
                      {task.completed_at ? new Date(task.completed_at).toLocaleString('zh-CN', { hour12: false }).split(' ')[1] : '-'}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Col>
      </Row>
    </div>
  );
};

export default Dashboard;