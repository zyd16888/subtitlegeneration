import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Progress, Alert, Spin } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  ClockCircleOutlined,
  ApiOutlined,
  TranslationOutlined,
  AudioOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { api } from '../services/api';
import type { Statistics, Task, TaskStatus } from '../types/api';

/**
 * Dashboard 页面
 * 
 * 显示系统状态和任务统计
 * - 任务统计卡片（总数、成功、失败、进行中）
 * - 最近完成的任务列表
 * - 系统状态（Emby、ASR、翻译服务连接状态）
 * - 当前正在处理的任务实时进度
 * - 每 5 秒自动刷新数据
 */
const Dashboard: React.FC = () => {
  const [statistics, setStatistics] = useState<Statistics | null>(null);
  const [processingTasks, setProcessingTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 获取统计数据
  const fetchStatistics = async () => {
    try {
      const data = await api.stats.getStatistics();
      setStatistics(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || '获取统计数据失败');
    }
  };

  // 获取正在处理的任务
  const fetchProcessingTasks = async () => {
    try {
      const response = await api.tasks.getTasks({ status: 'processing' as TaskStatus, limit: 10 });
      setProcessingTasks(response.items);
    } catch (err: any) {
      console.error('获取处理中任务失败:', err);
    }
  };

  // 加载所有数据
  const loadData = async () => {
    setLoading(true);
    await Promise.all([fetchStatistics(), fetchProcessingTasks()]);
    setLoading(false);
  };

  // 初始加载和自动刷新
  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000); // 每 5 秒刷新
    return () => clearInterval(interval);
  }, []);

  // 任务状态标签
  const getStatusTag = (status: TaskStatus) => {
    const statusConfig = {
      pending: { color: 'default', icon: <ClockCircleOutlined />, text: '待处理' },
      processing: { color: 'processing', icon: <SyncOutlined spin />, text: '处理中' },
      completed: { color: 'success', icon: <CheckCircleOutlined />, text: '已完成' },
      failed: { color: 'error', icon: <CloseCircleOutlined />, text: '失败' },
      cancelled: { color: 'default', icon: <CloseCircleOutlined />, text: '已取消' },
    };
    const config = statusConfig[status];
    return (
      <Tag color={config.color} icon={config.icon}>
        {config.text}
      </Tag>
    );
  };

  // 最近任务表格列定义
  const recentTaskColumns: ColumnsType<any> = [
    {
      title: '媒体项',
      dataIndex: 'media_item_title',
      key: 'media_item_title',
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: TaskStatus) => getStatusTag(status),
    },
    {
      title: '完成时间',
      dataIndex: 'completed_at',
      key: 'completed_at',
      width: 180,
      render: (time: string) => time ? new Date(time).toLocaleString('zh-CN') : '-',
    },
  ];

  // 正在处理任务表格列定义
  const processingTaskColumns: ColumnsType<Task> = [
    {
      title: '媒体项',
      dataIndex: 'media_item_title',
      key: 'media_item_title',
      ellipsis: true,
    },
    {
      title: '进度',
      dataIndex: 'progress',
      key: 'progress',
      width: 200,
      render: (progress: number) => (
        <Progress percent={progress} size="small" status="active" />
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: TaskStatus) => getStatusTag(status),
    },
  ];

  if (loading && !statistics) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  return (
    <div>
      <h1>Dashboard</h1>

      {error && (
        <Alert
          message="错误"
          description={error}
          type="error"
          closable
          style={{ marginBottom: 24 }}
        />
      )}

      {/* 任务统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="任务总数"
              value={statistics?.task_statistics.total || 0}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="成功"
              value={statistics?.task_statistics.completed || 0}
              valueStyle={{ color: '#52c41a' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="失败"
              value={statistics?.task_statistics.failed || 0}
              valueStyle={{ color: '#ff4d4f' }}
              prefix={<CloseCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="进行中"
              value={statistics?.task_statistics.processing || 0}
              valueStyle={{ color: '#faad14' }}
              prefix={<SyncOutlined spin />}
            />
          </Card>
        </Col>
      </Row>

      {/* 系统状态 */}
      <Card title="系统状态" style={{ marginBottom: 24 }}>
        <Row gutter={16}>
          <Col xs={24} md={8}>
            <Card
              size="small"
              style={{
                borderLeft: `4px solid ${
                  statistics?.system_status.emby_connected ? '#52c41a' : '#ff4d4f'
                }`,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <ApiOutlined style={{ fontSize: 24 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 'bold' }}>Emby 服务</div>
                  <div style={{ fontSize: 12, color: '#666' }}>
                    {statistics?.system_status.emby_message || '未知'}
                  </div>
                </div>
                {statistics?.system_status.emby_connected ? (
                  <CheckCircleOutlined style={{ fontSize: 24, color: '#52c41a' }} />
                ) : (
                  <CloseCircleOutlined style={{ fontSize: 24, color: '#ff4d4f' }} />
                )}
              </div>
            </Card>
          </Col>
          <Col xs={24} md={8}>
            <Card
              size="small"
              style={{
                borderLeft: `4px solid ${
                  statistics?.system_status.asr_configured ? '#52c41a' : '#ff4d4f'
                }`,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <AudioOutlined style={{ fontSize: 24 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 'bold' }}>ASR 引擎</div>
                  <div style={{ fontSize: 12, color: '#666' }}>
                    {statistics?.system_status.asr_message || '未知'}
                  </div>
                </div>
                {statistics?.system_status.asr_configured ? (
                  <CheckCircleOutlined style={{ fontSize: 24, color: '#52c41a' }} />
                ) : (
                  <CloseCircleOutlined style={{ fontSize: 24, color: '#ff4d4f' }} />
                )}
              </div>
            </Card>
          </Col>
          <Col xs={24} md={8}>
            <Card
              size="small"
              style={{
                borderLeft: `4px solid ${
                  statistics?.system_status.translation_configured ? '#52c41a' : '#ff4d4f'
                }`,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <TranslationOutlined style={{ fontSize: 24 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 'bold' }}>翻译服务</div>
                  <div style={{ fontSize: 12, color: '#666' }}>
                    {statistics?.system_status.translation_message || '未知'}
                  </div>
                </div>
                {statistics?.system_status.translation_configured ? (
                  <CheckCircleOutlined style={{ fontSize: 24, color: '#52c41a' }} />
                ) : (
                  <CloseCircleOutlined style={{ fontSize: 24, color: '#ff4d4f' }} />
                )}
              </div>
            </Card>
          </Col>
        </Row>
      </Card>

      {/* 当前正在处理的任务 */}
      {processingTasks.length > 0 && (
        <Card title="正在处理的任务" style={{ marginBottom: 24 }}>
          <Table
            columns={processingTaskColumns}
            dataSource={processingTasks}
            rowKey="id"
            pagination={false}
            size="small"
          />
        </Card>
      )}

      {/* 最近完成的任务 */}
      <Card title="最近完成的任务">
        <Table
          columns={recentTaskColumns}
          dataSource={statistics?.recent_tasks || []}
          rowKey="id"
          pagination={false}
          size="small"
          locale={{ emptyText: '暂无最近完成的任务' }}
        />
      </Card>
    </div>
  );
};

export default Dashboard;
