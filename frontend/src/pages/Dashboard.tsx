import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Progress, Alert, Spin, Typography, Space } from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
  SyncOutlined,
  ClockCircleOutlined,
  ApiOutlined,
  TranslationOutlined,
  AudioOutlined,
  ArrowUpOutlined,
  HistoryOutlined,
  ThunderboltFilled,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { api } from '../services/api';
import type { Statistics, Task, TaskStatus } from '../types/api';

const { Text } = Typography;

const StatCard: React.FC<{
  title: string;
  value: number;
  icon: React.ReactNode;
  color: string;
  loading?: boolean;
}> = ({ title, value, icon, color, loading }) => (
  <Card className="glass-card" bordered={false} style={{ height: '100%' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
      <Statistic
        title={<Text type="secondary" style={{ fontSize: 14 }}>{title}</Text>}
        value={value}
        valueStyle={{ color: 'var(--text-primary)', fontSize: 28, fontWeight: 'bold' }}
        loading={loading}
      />
      <div style={{
        padding: 12,
        borderRadius: 12,
        background: `${color}20`,
        color: color,
        fontSize: 24,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        {icon}
      </div>
    </div>
    <div style={{ marginTop: 12 }}>
      <Text type="secondary" style={{ fontSize: 12 }}>
        <ArrowUpOutlined /> <Text style={{ color: '#52c41a', fontWeight: '500' }}>实时更新中</Text>
      </Text>
    </div>
  </Card>
);

const StatusNode: React.FC<{
  icon: React.ReactNode;
  label: string;
  status: boolean;
  message: string;
}> = ({ icon, label, status, message }) => (
  <div style={{
    display: 'flex',
    alignItems: 'center',
    gap: 16,
    padding: '16px',
    borderRadius: 12,
    background: 'var(--bg-spotlight)',
    border: '1px solid var(--border-color-subtle)',
    marginBottom: 12,
    transition: 'background 0.3s, border-color 0.3s',
  }}>
    <div style={{
      fontSize: 24,
      color: status ? '#52c41a' : '#ff4d4f',
      background: status ? '#52c41a10' : '#ff4d4f10',
      padding: 10,
      borderRadius: 10,
      display: 'flex',
    }}>
      {icon}
    </div>
    <div style={{ flex: 1 }}>
      <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>{label}</div>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{message}</div>
    </div>
    <div style={{ display: 'flex', alignItems: 'center' }}>
      {status ? (
        <Tag color="success" icon={<CheckCircleFilled />} style={{ borderRadius: 10 }}>在线</Tag>
      ) : (
        <Tag color="error" icon={<CloseCircleFilled />} style={{ borderRadius: 10 }}>离线</Tag>
      )}
    </div>
  </div>
);

const Dashboard: React.FC = () => {
  const [statistics, setStatistics] = useState<Statistics | null>(null);
  const [processingTasks, setProcessingTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [statsData, processingData] = await Promise.all([
        api.stats.getStatistics(),
        api.tasks.getTasks({ status: 'processing' as TaskStatus, limit: 10 })
      ]);
      setStatistics(statsData);
      setProcessingTasks(processingData.items);
      setError(null);
    } catch (err: any) {
      setError(err.message || '获取数据失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
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
    return <Tag color={config.color} icon={config.icon} style={{ borderRadius: 6 }}>{config.text}</Tag>;
  };

  const recentTaskColumns: ColumnsType<any> = [
    {
      title: '媒体项',
      dataIndex: 'media_item_title',
      key: 'media_item_title',
      ellipsis: true,
      render: (text) => <Text strong style={{ color: 'var(--text-primary)' }}>{text}</Text>
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (status: TaskStatus) => getStatusTag(status),
    },
    {
      title: '完成时间',
      dataIndex: 'completed_at',
      key: 'completed_at',
      width: 160,
      render: (time: string) => <Text type="secondary" style={{ fontSize: 12 }}>{time ? new Date(time).toLocaleString('zh-CN', { hour12: false }).split(' ')[1] : '-'}</Text>,
    },
  ];

  if (loading && !statistics) {
    return <div style={{ textAlign: 'center', padding: '100px' }}><Spin size="large" tip="正在初始化控制面板..." /></div>;
  }

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto' }}>
      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 24, borderRadius: 12 }} />}

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <StatCard title="任务总数" value={statistics?.task_statistics.total || 0} icon={<HistoryOutlined />} color="#1677ff" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard title="成功生成" value={statistics?.task_statistics.completed || 0} icon={<CheckCircleFilled />} color="#52c41a" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard title="正在处理" value={statistics?.task_statistics.processing || 0} icon={<SyncOutlined />} color="#faad14" />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard title="异常任务" value={statistics?.task_statistics.failed || 0} icon={<ThunderboltFilled />} color="#ff4d4f" />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={10}>
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card className="glass-card" title={<Space><ApiOutlined />系统连接状态</Space>} bordered={false}>
              <StatusNode
                icon={<ApiOutlined />}
                label="Emby 服务器"
                status={statistics?.system_status.emby_connected || false}
                message={statistics?.system_status.emby_message || '等待连接...'}
              />
              <StatusNode
                icon={<AudioOutlined />}
                label="ASR 识别引擎"
                status={statistics?.system_status.asr_configured || false}
                message={statistics?.system_status.asr_message || '引擎就绪'}
              />
              <StatusNode
                icon={<TranslationOutlined />}
                label="翻译服务"
                status={statistics?.system_status.translation_configured || false}
                message={statistics?.system_status.translation_message || '服务正常'}
              />
            </Card>

            {processingTasks.length > 0 && (
              <Card className="glass-card" title={<Space><SyncOutlined spin />实时处理进度</Space>} bordered={false}>
                {processingTasks.map(task => (
                  <div key={task.id} style={{ marginBottom: 16 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                      <Text ellipsis style={{ maxWidth: '70%', fontSize: 13 }}>{task.media_item_title}</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>{task.progress}%</Text>
                    </div>
                    <Progress
                      percent={task.progress}
                      size="small"
                      strokeColor={{ '0%': '#1677ff', '100%': '#722ed1' }}
                      trailColor="var(--progress-trail)"
                      showInfo={false}
                    />
                  </div>
                ))}
              </Card>
            )}
          </Space>
        </Col>

        <Col xs={24} lg={14}>
          <Card
            className="glass-card"
            title={<Space><HistoryOutlined />最近活动历史</Space>}
            bordered={false}
            bodyStyle={{ padding: 0 }}
          >
            <Table
              columns={recentTaskColumns}
              dataSource={statistics?.recent_tasks || []}
              rowKey="id"
              pagination={false}
              size="middle"
              className="custom-table"
              style={{ background: 'transparent' }}
              locale={{ emptyText: <div style={{ padding: 40 }}><Text type="secondary">暂无最近活动记录</Text></div> }}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default Dashboard;
