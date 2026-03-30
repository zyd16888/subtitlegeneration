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
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  ClockCircleOutlined,
  ReloadOutlined,
  StopOutlined,
  ExclamationCircleOutlined,
  EyeOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { api } from '../services/api';
import type { Task, TaskStatus } from '../types/api';

const { Option } = Select;

/**
 * Tasks 页面
 * 
 * 查看和管理字幕生成任务
 * - 使用 Ant Design Table 组件显示任务列表
 * - 显示任务状态、进度、创建时间、完成时间
 * - 实现状态筛选功能
 * - 支持取消和重试任务
 * - 自动刷新任务列表
 * 
 * 需求: 8.1
 */
const Tasks: React.FC = () => {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState<TaskStatus | undefined>(undefined);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [detailsVisible, setDetailsVisible] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);

  // 获取任务列表
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

  // 初始加载和自动刷新
  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 5000); // 每 5 秒刷新
    return () => clearInterval(interval);
  }, [selectedStatus, currentPage, pageSize]);

  // 处理状态筛选
  const handleStatusChange = (value: TaskStatus | undefined) => {
    setSelectedStatus(value);
    setCurrentPage(1); // 重置到第一页
  };

  // 处理取消任务
  const handleCancelTask = (taskId: string, mediaTitle?: string) => {
    Modal.confirm({
      title: '确认取消任务',
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <p>确定要取消以下任务吗？</p>
          {mediaTitle && <p style={{ fontWeight: 'bold' }}>{mediaTitle}</p>}
          <p style={{ color: '#999', fontSize: '12px' }}>取消后任务将停止处理，无法恢复。</p>
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

  // 处理重试任务
  const handleRetryTask = (taskId: string, mediaTitle?: string) => {
    Modal.confirm({
      title: '确认重试任务',
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <p>确定要重试以下任务吗？</p>
          {mediaTitle && <p style={{ fontWeight: 'bold' }}>{mediaTitle}</p>}
          <p style={{ color: '#999', fontSize: '12px' }}>将创建新的任务并重新开始处理。</p>
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

  // 处理分页改变
  const handlePageChange = (page: number, pageSize: number) => {
    setCurrentPage(page);
    setPageSize(pageSize);
  };

  // 显示任务详情
  const showTaskDetails = (task: Task) => {
    setSelectedTask(task);
    setDetailsVisible(true);
  };

  // 关闭任务详情
  const closeTaskDetails = () => {
    setDetailsVisible(false);
    setSelectedTask(null);
  };

  // 根据进度推断任务阶段
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
        if (task.progress >= stage.range[0]) {
          status = 'error';
        } else {
          status = 'wait';
        }
      } else if (task.status === 'completed') {
        status = 'finish';
      } else if (task.progress >= stage.range[1]) {
        status = 'finish';
      } else if (task.progress >= stage.range[0]) {
        status = 'process';
      }

      return {
        ...stage,
        status,
        progress: Math.min(100, Math.max(0, ((task.progress - stage.range[0]) / (stage.range[1] - stage.range[0])) * 100)),
      };
    });
  };

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

  // 表格列定义
  const columns: ColumnsType<Task> = [
    {
      title: '媒体项',
      dataIndex: 'media_item_title',
      key: 'media_item_title',
      ellipsis: true,
      render: (title: string) => (
        <Tooltip title={title}>
          {title || '未知'}
        </Tooltip>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: TaskStatus) => getStatusTag(status),
    },
    {
      title: '进度',
      dataIndex: 'progress',
      key: 'progress',
      width: 150,
      render: (progress: number, record: Task) => {
        if (record.status === 'completed') {
          return <Progress percent={100} size="small" status="success" />;
        } else if (record.status === 'failed' || record.status === 'cancelled') {
          return <Progress percent={progress} size="small" status="exception" />;
        } else if (record.status === 'processing') {
          return <Progress percent={progress} size="small" status="active" />;
        } else {
          return <Progress percent={0} size="small" />;
        }
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (time: string) => new Date(time).toLocaleString('zh-CN'),
    },
    {
      title: '完成时间',
      dataIndex: 'completed_at',
      key: 'completed_at',
      width: 180,
      render: (time: string) => time ? new Date(time).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_, record: Task) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => showTaskDetails(record)}
          >
            详情
          </Button>
          {record.status === 'processing' && (
            <Button
              type="link"
              size="small"
              icon={<StopOutlined />}
              onClick={() => handleCancelTask(record.id, record.media_item_title)}
            >
              取消
            </Button>
          )}
          {record.status === 'failed' && (
            <Button
              type="link"
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => handleRetryTask(record.id, record.media_item_title)}
            >
              重试
            </Button>
          )}
        </Space>
      ),
    },
  ];

  // 状态筛选选项
  const statusOptions = [
    { label: '全部', value: undefined },
    { label: '待处理', value: 'pending' as TaskStatus },
    { label: '处理中', value: 'processing' as TaskStatus },
    { label: '已完成', value: 'completed' as TaskStatus },
    { label: '失败', value: 'failed' as TaskStatus },
    { label: '已取消', value: 'cancelled' as TaskStatus },
  ];

  return (
    <div>
      <h1>Tasks</h1>

      {/* 筛选器 */}
      <Card style={{ marginBottom: 24 }}>
        <Space>
          <span style={{ fontWeight: 'bold' }}>状态筛选:</span>
          <Select
            style={{ width: 150 }}
            value={selectedStatus}
            onChange={handleStatusChange}
          >
            {statusOptions.map((option) => (
              <Option key={option.value || 'all'} value={option.value}>
                {option.label}
              </Option>
            ))}
          </Select>
          <Button icon={<ReloadOutlined />} onClick={fetchTasks}>
            刷新
          </Button>
        </Space>
      </Card>

      {/* 任务列表表格 */}
      <Card>
        <Table
          columns={columns}
          dataSource={tasks}
          rowKey="id"
          loading={loading}
          pagination={false}
          expandable={{
            expandedRowRender: (record: Task) => (
              record.error_message ? (
                <div style={{ padding: '8px 0' }}>
                  <strong>错误信息:</strong>
                  <div style={{ color: '#ff4d4f', marginTop: 4 }}>
                    {record.error_message}
                  </div>
                </div>
              ) : null
            ),
            rowExpandable: (record: Task) => !!record.error_message,
          }}
        />

        {/* 分页 */}
        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <Pagination
            current={currentPage}
            pageSize={pageSize}
            total={total}
            onChange={handlePageChange}
            showSizeChanger
            showQuickJumper
            showTotal={(total) => `共 ${total} 个任务`}
            pageSizeOptions={['10', '20', '50', '100']}
          />
        </div>
      </Card>

      {/* 任务详情抽屉 */}
      <Drawer
        title="任务详情"
        placement="right"
        width={720}
        onClose={closeTaskDetails}
        open={detailsVisible}
      >
        {selectedTask && (
          <div>
            {/* 错误信息提示 */}
            {selectedTask.error_message && (
              <Alert
                message="任务失败"
                description={selectedTask.error_message}
                type="error"
                showIcon
                style={{ marginBottom: 24 }}
              />
            )}

            {/* 基本信息 */}
            <Descriptions title="基本信息" bordered column={1} style={{ marginBottom: 24 }}>
              <Descriptions.Item label="任务 ID">{selectedTask.id}</Descriptions.Item>
              <Descriptions.Item label="媒体项">
                {selectedTask.media_item_title || '未知'}
              </Descriptions.Item>
              <Descriptions.Item label="媒体项 ID">
                {selectedTask.media_item_id}
              </Descriptions.Item>
              {selectedTask.video_path && (
                <Descriptions.Item label="视频路径">
                  <Tooltip title={selectedTask.video_path}>
                    <div style={{ 
                      maxWidth: '100%', 
                      overflow: 'hidden', 
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap' 
                    }}>
                      {selectedTask.video_path}
                    </div>
                  </Tooltip>
                </Descriptions.Item>
              )}
              <Descriptions.Item label="状态">
                {getStatusTag(selectedTask.status)}
              </Descriptions.Item>
              <Descriptions.Item label="进度">
                <Progress 
                  percent={selectedTask.progress} 
                  status={
                    selectedTask.status === 'completed' ? 'success' :
                    selectedTask.status === 'failed' || selectedTask.status === 'cancelled' ? 'exception' :
                    selectedTask.status === 'processing' ? 'active' : 'normal'
                  }
                />
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {new Date(selectedTask.created_at).toLocaleString('zh-CN')}
              </Descriptions.Item>
              {selectedTask.completed_at && (
                <Descriptions.Item label="完成时间">
                  {new Date(selectedTask.completed_at).toLocaleString('zh-CN')}
                </Descriptions.Item>
              )}
            </Descriptions>

            {/* 处理阶段 */}
            <div style={{ marginBottom: 24 }}>
              <h3 style={{ marginBottom: 16 }}>处理阶段</h3>
              <Steps
                direction="vertical"
                current={getTaskStages(selectedTask).findIndex(s => s.status === 'process')}
                status={
                  selectedTask.status === 'failed' || selectedTask.status === 'cancelled' ? 'error' :
                  selectedTask.status === 'completed' ? 'finish' : 'process'
                }
              >
                {getTaskStages(selectedTask).map((stage) => (
                  <Steps.Step
                    key={stage.key}
                    title={stage.name}
                    status={stage.status}
                    icon={
                      stage.status === 'process' ? <LoadingOutlined /> :
                      stage.status === 'finish' ? <CheckCircleOutlined /> :
                      stage.status === 'error' ? <CloseCircleOutlined /> :
                      undefined
                    }
                    description={
                      stage.status === 'process' ? (
                        <Progress 
                          percent={Math.round(stage.progress)} 
                          size="small" 
                          status="active"
                        />
                      ) : stage.status === 'finish' ? (
                        <span style={{ color: '#52c41a' }}>已完成</span>
                      ) : stage.status === 'error' ? (
                        <span style={{ color: '#ff4d4f' }}>失败</span>
                      ) : (
                        <span style={{ color: '#999' }}>等待中</span>
                      )
                    }
                  />
                ))}
              </Steps>
            </div>

            {/* 操作按钮 */}
            <div style={{ textAlign: 'right' }}>
              <Space>
                {selectedTask.status === 'processing' && (
                  <Button
                    danger
                    icon={<StopOutlined />}
                    onClick={() => {
                      handleCancelTask(selectedTask.id, selectedTask.media_item_title);
                      closeTaskDetails();
                    }}
                  >
                    取消任务
                  </Button>
                )}
                {selectedTask.status === 'failed' && (
                  <Button
                    type="primary"
                    icon={<ReloadOutlined />}
                    onClick={() => {
                      handleRetryTask(selectedTask.id, selectedTask.media_item_title);
                      closeTaskDetails();
                    }}
                  >
                    重试任务
                  </Button>
                )}
                <Button onClick={closeTaskDetails}>关闭</Button>
              </Space>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default Tasks;
