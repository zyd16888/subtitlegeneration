import React, { useState, useEffect } from 'react';
import {
  Card,
  Table,
  Tag,
  Progress,
  Button,
  Space,
  Select,
  message,
  Pagination,
  Tooltip,
  Modal,
  Drawer,
  Descriptions,
  Steps,
  Alert,
  Typography,
} from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
  SyncOutlined,
  ClockCircleOutlined,
  ReloadOutlined,
  StopOutlined,
  ExclamationCircleOutlined,
  EyeOutlined,
  LoadingOutlined,
  FilterOutlined,
  HistoryOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { api } from '../services/api';
import type { Task, TaskStatus } from '../types/api';

const { Option } = Select;
const { Text, Title } = Typography;

const Tasks: React.FC = () => {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState<TaskStatus | undefined>(undefined);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [detailsVisible, setDetailsVisible] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);

  const fetchTasks = async () => {
    setLoading(true);
    try {
      const response = await api.tasks.getTasks({
        status: selectedStatus,
        limit: pageSize,
        offset: (currentPage - 1) * pageSize,
      });
      setTasks(response.items);
      setTotal(response.total);
    } catch (err: any) {
      message.error(err.message || '获取任务列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 5000);
    return () => clearInterval(interval);
  }, [selectedStatus, currentPage, pageSize]);

  const handleStatusChange = (value: TaskStatus | undefined) => {
    setSelectedStatus(value);
    setCurrentPage(1);
  };

  const handleCancelTask = (taskId: string, mediaTitle?: string) => {
    Modal.confirm({
      title: '确认取消任务',
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <p>确定要取消以下任务吗？</p>
          {mediaTitle && <p style={{ fontWeight: 'bold' }}>{mediaTitle}</p>}
          <p style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>取消后任务将停止处理，无法恢复。</p>
        </div>
      ),
      okText: '确认取消',
      okType: 'danger',
      cancelText: '返回',
      onOk: async () => {
        try {
          await api.tasks.cancelTask(taskId);
          message.success('任务已取消');
          fetchTasks();
        } catch (err: any) {
          message.error(err.message || '取消任务失败');
        }
      },
    });
  };

  const handleRetryTask = (taskId: string, mediaTitle?: string) => {
    Modal.confirm({
      title: '确认重试任务',
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <p>确定要重试以下任务吗？</p>
          {mediaTitle && <p style={{ fontWeight: 'bold' }}>{mediaTitle}</p>}
          <p style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>将创建新的任务并重新开始处理。</p>
        </div>
      ),
      okText: '确认重试',
      cancelText: '取消',
      onOk: async () => {
        try {
          await api.tasks.retryTask(taskId);
          message.success('任务已重新提交');
          fetchTasks();
        } catch (err: any) {
          message.error(err.message || '重试任务失败');
        }
      },
    });
  };

  const getTaskStages = (task: Task) => {
    const stages = [
      { name: '音频提取', range: [0, 20], key: 'audio' },
      { name: '语音识别', range: [20, 60], key: 'asr' },
      { name: '翻译', range: [60, 90], key: 'translation' },
      { name: '字幕生成', range: [90, 95], key: 'subtitle' },
      { name: 'Emby 回写', range: [95, 100], key: 'emby' },
    ];

    return stages.map((stage) => {
      let status: 'wait' | 'process' | 'finish' | 'error' = 'wait';
      if (task.status === 'failed' || task.status === 'cancelled') {
        status = task.progress >= stage.range[0] ? 'error' : 'wait';
      } else if (task.status === 'completed') {
        status = 'finish';
      } else if (task.progress >= stage.range[1]) {
        status = 'finish';
      } else if (task.progress >= stage.range[0]) {
        status = 'process';
      }
      return { ...stage, status, progress: Math.min(100, Math.max(0, ((task.progress - stage.range[0]) / (stage.range[1] - stage.range[0])) * 100)) };
    });
  };

  const getStatusTag = (status: TaskStatus) => {
    const configs = {
      pending: { color: 'default', icon: <ClockCircleOutlined />, text: '待处理' },
      processing: { color: 'processing', icon: <SyncOutlined spin style={{ color: 'var(--accent-amber)' }} />, text: '处理中' },
      completed: { color: 'success', icon: <CheckCircleFilled style={{ color: 'var(--accent-emerald)' }} />, text: '已完成' },
      failed: { color: 'error', icon: <CloseCircleFilled style={{ color: 'var(--accent-rose)' }} />, text: '失败' },
      cancelled: { color: 'default', icon: <CloseCircleFilled />, text: '已取消' },
    };
    const config = configs[status];
    return <Tag color={config.color} icon={config.icon} style={{ borderRadius: 6 }}>{config.text}</Tag>;
  };

  const columns: ColumnsType<Task> = [
    {
      title: '媒体项目',
      dataIndex: 'media_item_title',
      key: 'media_item_title',
      ellipsis: true,
      render: (title: string) => <Text strong style={{ color: 'var(--text-primary)' }}>{title || '未知媒体'}</Text>,
    },
    {
      title: '当前状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: TaskStatus) => getStatusTag(status),
    },
    {
      title: '实时进度',
      dataIndex: 'progress',
      key: 'progress',
      width: 180,
      render: (progress: number, record: Task) => (
        <Progress
          percent={progress}
          size="small"
          status={record.status === 'failed' ? 'exception' : (record.status === 'completed' ? 'success' : 'active')}
          strokeColor={record.status === 'completed' ? 'var(--accent-emerald)' : { '0%': 'var(--accent-cyan)', '100%': '#007bb5' }}
        />
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (time: string) => <Text type="secondary" style={{ fontSize: 12 }}>{new Date(time).toLocaleString('zh-CN', { hour12: false })}</Text>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      align: 'right',
      render: (_, record: Task) => (
        <Space size="middle">
          <Tooltip title="查看详情">
            <Button type="text" icon={<EyeOutlined />} onClick={() => { setSelectedTask(record); setDetailsVisible(true); }} />
          </Tooltip>
          {record.status === 'processing' && (
            <Tooltip title="取消任务">
              <Button type="text" danger icon={<StopOutlined />} onClick={() => handleCancelTask(record.id, record.media_item_title)} />
            </Tooltip>
          )}
          {record.status === 'failed' && (
            <Tooltip title="重试任务">
              <Button type="text" style={{ color: '#1677ff' }} icon={<ReloadOutlined />} onClick={() => handleRetryTask(record.id, record.media_item_title)} />
            </Tooltip>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto' }}>
      <div className="glass-card animate-fade-in-up delay-1" style={{ marginBottom: 24, borderRadius: 16, padding: '16px 24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
          <Space size={12}>
            <div style={{ background: '#1677ff', padding: 8, borderRadius: 8, color: 'white', display: 'flex' }}>
              <HistoryOutlined />
            </div>
            <Title level={5} style={{ margin: 0 }}>任务队列管理</Title>
          </Space>

          <Space size="middle">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <FilterOutlined style={{ color: 'var(--text-secondary)' }} />
              <Select
                style={{ width: 140 }}
                placeholder="筛选状态"
                value={selectedStatus}
                onChange={handleStatusChange}
                allowClear
              >
                <Option value="pending">待处理</Option>
                <Option value="processing">进行中</Option>
                <Option value="completed">已完成</Option>
                <Option value="failed">失败</Option>
                <Option value="cancelled">已取消</Option>
              </Select>
            </div>
            <Button icon={<ReloadOutlined />} onClick={fetchTasks}>刷新列表</Button>
          </Space>
        </div>
      </div>

      <div className="glass-card animate-fade-in-up delay-2" style={{ padding: 0, borderRadius: 16, overflow: 'hidden' }}>
        <Table
          columns={columns}
          dataSource={tasks}
          rowKey="id"
          loading={loading}
          pagination={false}
          className="custom-table"
          expandable={{
            expandedRowRender: (record) => record.error_message && (
              <div style={{ padding: '16px 24px', background: 'var(--error-bg)', borderLeft: '4px solid #ff4d4f' }}>
                <Text type="danger" strong>错误详情：</Text>
                <div style={{ marginTop: 8, color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{record.error_message}</div>
              </div>
            ),
            rowExpandable: (record) => !!record.error_message,
          }}
        />

        <div style={{ padding: '24px', textAlign: 'center' }}>
          <Pagination
            current={currentPage}
            pageSize={pageSize}
            total={total}
            onChange={(p, s) => { setCurrentPage(p); setPageSize(s); }}
            showSizeChanger
            showTotal={(total) => <Text type="secondary">共 {total} 个生成任务</Text>}
          />
        </div>
      </div>

      <Drawer
        title={<Space><EyeOutlined /> 任务详细信息</Space>}
        placement="right"
        width={640}
        onClose={() => setDetailsVisible(false)}
        open={detailsVisible}
      >
        {selectedTask && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
            {selectedTask.error_message && (
              <Alert message="任务处理异常" description={selectedTask.error_message} type="error" showIcon style={{ borderRadius: 12 }} />
            )}

            <Descriptions title="基本概览" bordered column={1} size="small" className="custom-descriptions">
              <Descriptions.Item label="媒体标题">{selectedTask.media_item_title}</Descriptions.Item>
              <Descriptions.Item label="当前状态">{getStatusTag(selectedTask.status)}</Descriptions.Item>
              <Descriptions.Item label="当前总进度">
                <Progress percent={selectedTask.progress} size="small" strokeColor={{ '0%': '#1677ff', '100%': '#722ed1' }} />
              </Descriptions.Item>
              <Descriptions.Item label="任务 ID"><Text copyable style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{selectedTask.id}</Text></Descriptions.Item>
            </Descriptions>

            <div>
              <Title level={5} style={{ marginBottom: 20 }}>处理流程分析</Title>
              <Steps
                direction="vertical"
                size="small"
                current={getTaskStages(selectedTask).findIndex(s => s.status === 'process')}
                items={getTaskStages(selectedTask).map(stage => ({
                  title: stage.name,
                  status: stage.status,
                  icon: stage.status === 'process' ? <LoadingOutlined /> : (stage.status === 'finish' ? <CheckCircleFilled style={{ color: '#52c41a' }} /> : (stage.status === 'error' ? <CloseCircleFilled style={{ color: '#ff4d4f' }} /> : undefined)),
                  description: stage.status === 'process' ? <Progress percent={Math.round(stage.progress)} size="small" /> : null
                }))}
              />
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default Tasks;
