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
  Divider,
  Statistic,
  Row,
  Col,
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
  SoundOutlined,
  FileTextOutlined,
  SettingOutlined,
  FieldTimeOutlined,
  PlayCircleOutlined,
  MinusCircleOutlined,
  ProfileOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { api } from '../services/api';
import type { Task, TaskDetail, TaskStatus } from '../types/api';
import { LANGUAGE_NAMES, TRANSLATION_SERVICE_NAMES, ASR_ENGINE_NAMES } from '../types/api';

const { Option } = Select;
const { Text, Title, Paragraph } = Typography;

const Tasks: React.FC = () => {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState<TaskStatus | undefined>(undefined);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [detailsVisible, setDetailsVisible] = useState(false);
  const [selectedTask, setSelectedTask] = useState<TaskDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

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

  const fetchTaskDetail = async (taskId: string) => {
    setDetailLoading(true);
    try {
      const detail = await api.tasks.getTask(taskId);
      setSelectedTask(detail);
    } catch (err: any) {
      message.error(err.message || '获取任务详情失败');
    } finally {
      setDetailLoading(false);
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

  const handleViewDetail = (taskId: string) => {
    setDetailsVisible(true);
    fetchTaskDetail(taskId);
  };

  const getTaskStages = (task: Task | TaskDetail) => {
    const stages = [
      { name: '音频提取', range: [0, 20], key: 'audio', icon: <SoundOutlined /> },
      { name: '语音识别', range: [20, 60], key: 'asr', icon: <PlayCircleOutlined /> },
      { name: '翻译文本', range: [60, 90], key: 'translation', icon: <FileTextOutlined /> },
      { name: '字幕生成', range: [90, 95], key: 'subtitle', icon: <FileTextOutlined /> },
      { name: 'Emby 回写', range: [95, 100], key: 'emby', icon: <CheckCircleFilled /> },
    ];

    return stages.map((stage) => {
      let status: 'wait' | 'process' | 'finish' | 'error' = 'wait';
      if (task.status === 'failed' || task.status === 'cancelled') {
        if (task.progress >= stage.range[1]) {
          status = 'finish';
        } else if (task.progress >= stage.range[0]) {
          status = 'error';
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
        progress: Math.min(100, Math.max(0, ((task.progress - stage.range[0]) / (stage.range[1] - stage.range[0])) * 100)) 
      };
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

  const formatDuration = (seconds?: number) => {
    if (!seconds) return '-';
    if (seconds < 60) return `${seconds.toFixed(1)} 秒`;
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(0);
    return `${mins} 分 ${secs} 秒`;
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
            <Button type="text" icon={<EyeOutlined />} onClick={() => handleViewDetail(record.id)} />
          </Tooltip>
          {(record.status === 'pending' || record.status === 'processing') && (
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
            <div style={{ background: 'var(--accent-cyan)', padding: 8, borderRadius: 8, color: 'white', display: 'flex' }}>
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
              <div style={{ padding: '16px 24px', background: 'var(--error-bg)', borderLeft: '4px solid var(--accent-rose)' }}>
                <Text type="danger" strong>错误详情：</Text>
                <div style={{ marginTop: 8, color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{record.error_message}</div>
                {record.error_stage && <div style={{ marginTop: 4, color: 'var(--text-secondary)', fontSize: 12 }}>错误阶段：{record.error_stage}</div>}
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
        width={720}
        onClose={() => setDetailsVisible(false)}
        open={detailsVisible}
        loading={detailLoading}
      >
        {selectedTask && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            {/* 错误提示 */}
            {selectedTask.error_message && (
              <Alert 
                message="任务处理异常" 
                description={
                  <div>
                    <div>{selectedTask.error_message}</div>
                    {selectedTask.error_stage && <div style={{ marginTop: 8, fontSize: 12 }}>错误阶段：{selectedTask.error_stage}</div>}
                  </div>
                } 
                type="error" 
                showIcon 
                style={{ borderRadius: 12 }} 
              />
            )}

            {/* 基本信息卡片 */}
            <Card size="small" title={<Space><FileTextOutlined /> 基本信息</Space>} style={{ borderRadius: 12 }}>
              <Descriptions column={2} size="small">
                <Descriptions.Item label="媒体标题" span={2}>{selectedTask.media_item_title || '未知媒体'}</Descriptions.Item>
                <Descriptions.Item label="当前状态">{getStatusTag(selectedTask.status)}</Descriptions.Item>
                <Descriptions.Item label="总进度">
                  <Progress percent={selectedTask.progress} size="small" style={{ width: 120 }} />
                </Descriptions.Item>
                <Descriptions.Item label="任务 ID" span={2}>
                  <Text copyable style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{selectedTask.id}</Text>
                </Descriptions.Item>
              </Descriptions>
            </Card>

            {/* 统计信息 */}
            {(selectedTask.audio_duration || selectedTask.segment_count || selectedTask.processing_time) && (
              <Card size="small" title={<Space><FieldTimeOutlined /> 处理统计</Space>} style={{ borderRadius: 12 }}>
                <Row gutter={16}>
                  {selectedTask.audio_duration && (
                    <Col span={8}>
                      <Statistic 
                        title="音频时长" 
                        value={formatDuration(selectedTask.audio_duration)} 
                        prefix={<SoundOutlined />}
                      />
                    </Col>
                  )}
                  {selectedTask.segment_count && (
                    <Col span={8}>
                      <Statistic 
                        title="字幕段落数" 
                        value={selectedTask.segment_count} 
                        prefix={<FileTextOutlined />}
                      />
                    </Col>
                  )}
                  {selectedTask.processing_time && (
                    <Col span={8}>
                      <Statistic 
                        title="处理耗时" 
                        value={formatDuration(selectedTask.processing_time)} 
                        prefix={<FieldTimeOutlined />}
                      />
                    </Col>
                  )}
                </Row>
              </Card>
            )}

            {/* 时间信息 */}
            <Card size="small" title={<Space><ClockCircleOutlined /> 时间信息</Space>} style={{ borderRadius: 12 }}>
              <Descriptions column={2} size="small">
                <Descriptions.Item label="创建时间">
                  {new Date(selectedTask.created_at).toLocaleString('zh-CN', { hour12: false })}
                </Descriptions.Item>
                {selectedTask.started_at && (
                  <Descriptions.Item label="开始处理">
                    {new Date(selectedTask.started_at).toLocaleString('zh-CN', { hour12: false })}
                  </Descriptions.Item>
                )}
                {selectedTask.completed_at && (
                  <Descriptions.Item label="完成时间">
                    {new Date(selectedTask.completed_at).toLocaleString('zh-CN', { hour12: false })}
                  </Descriptions.Item>
                )}
                {selectedTask.wait_time && (
                  <Descriptions.Item label="等待时长">
                    {formatDuration(selectedTask.wait_time)}
                  </Descriptions.Item>
                )}
              </Descriptions>
            </Card>

            {/* 配置信息 */}
            <Card size="small" title={<Space><SettingOutlined /> 任务配置</Space>} style={{ borderRadius: 12 }}>
              <Descriptions column={2} size="small">
                <Descriptions.Item label="ASR 引擎">
                  {ASR_ENGINE_NAMES[selectedTask.asr_engine || ''] || selectedTask.asr_engine || '-'}
                </Descriptions.Item>
                <Descriptions.Item label="ASR 模型">
                  {selectedTask.asr_model_id || '-'}
                </Descriptions.Item>
                <Descriptions.Item label="翻译服务">
                  {TRANSLATION_SERVICE_NAMES[selectedTask.translation_service || ''] || selectedTask.translation_service || '-'}
                </Descriptions.Item>
                <Descriptions.Item label="语言方向">
                  {LANGUAGE_NAMES[selectedTask.source_language || ''] || selectedTask.source_language || '自动'} → {LANGUAGE_NAMES[selectedTask.target_language || ''] || selectedTask.target_language || '中文'}
                </Descriptions.Item>
              </Descriptions>
            </Card>

            {/* 处理流程 */}
            <Card size="small" title={<Space><PlayCircleOutlined /> 处理流程</Space>} style={{ borderRadius: 12 }}>
              <Steps
                direction="vertical"
                size="small"
                current={getTaskStages(selectedTask).findIndex(s => s.status === 'process')}
                items={getTaskStages(selectedTask).map(stage => {
                  const stepLog = selectedTask.extra_info?.step_logs?.[stage.key] as string | undefined;
                  const skippedSteps = (selectedTask.extra_info?.skipped_steps ?? []) as string[];
                  const isSkipped = skippedSteps.includes(stage.key);
                  let description: React.ReactNode = null;
                  if (stage.status === 'process') {
                    // 处理中：显示进度条，如果有日志也显示
                    description = (
                      <>
                        <Progress percent={Math.round(stage.progress)} size="small" />
                        {stepLog && (
                          <Text type="secondary" style={{ fontSize: 12, whiteSpace: 'pre-line', marginTop: 8, display: 'block' }}>
                            {stepLog}
                          </Text>
                        )}
                      </>
                    );
                  } else if (stepLog) {
                    // 完成、失败、跳过：只要有日志就显示
                    description = (
                      <Text type="secondary" style={{ fontSize: 12, whiteSpace: 'pre-line' }}>
                        {stepLog}
                      </Text>
                    );
                  }

                  let icon: React.ReactNode;
                  if (isSkipped && stage.status === 'finish') {
                    icon = <MinusCircleOutlined style={{ color: '#d9d9d9' }} />;
                  } else if (stage.status === 'process') {
                    icon = <LoadingOutlined />;
                  } else if (stage.status === 'finish') {
                    icon = <CheckCircleFilled style={{ color: '#52c41a' }} />;
                  } else if (stage.status === 'error') {
                    icon = <CloseCircleFilled style={{ color: '#ff4d4f' }} />;
                  } else {
                    icon = stage.icon;
                  }

                  return {
                    title: isSkipped && stage.status === 'finish'
                      ? <Text type="secondary">{stage.name}<Tag color="default" style={{ marginLeft: 8, fontSize: 11 }}>已跳过</Tag></Text>
                      : stage.name,
                    status: stage.status,
                    icon,
                    description,
                  };
                })}
              />
            </Card>

            {/* 处理日志 */}
            {Array.isArray(selectedTask.extra_info?.logs) && selectedTask.extra_info!.logs.length > 0 && (
              <Card
                size="small"
                title={
                  <Space>
                    <ProfileOutlined /> 处理日志
                    <Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal' }}>
                      共 {selectedTask.extra_info!.logs.length} 条
                    </Text>
                  </Space>
                }
                extra={
                  <Button
                    size="small"
                    onClick={() => fetchTaskDetail(selectedTask.id)}
                    icon={<ReloadOutlined />}
                  >
                    刷新
                  </Button>
                }
                style={{ borderRadius: 12 }}
              >
                <div
                  style={{
                    maxHeight: 360,
                    overflow: 'auto',
                    background: 'var(--code-bg, #1e1e1e)',
                    color: '#d4d4d4',
                    padding: 12,
                    borderRadius: 8,
                    fontFamily: 'Consolas, Menlo, monospace',
                    fontSize: 12,
                    lineHeight: 1.6,
                  }}
                >
                  {(selectedTask.extra_info!.logs as Array<{ timestamp: string; level: string; logger?: string; message: string }>).map((log, idx) => {
                    const levelColor: Record<string, string> = {
                      DEBUG: '#9e9e9e',
                      INFO: '#4ec9b0',
                      WARNING: '#dcdcaa',
                      ERROR: '#f48771',
                      CRITICAL: '#f48771',
                    };
                    const color = levelColor[log.level] || '#d4d4d4';
                    const ts = log.timestamp ? log.timestamp.replace('T', ' ').slice(0, 23) : '';
                    return (
                      <div key={idx} style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                        <span style={{ color: '#808080' }}>{ts}</span>{' '}
                        <span style={{ color, fontWeight: 600 }}>[{log.level}]</span>{' '}
                        <span style={{ color }}>{log.message}</span>
                      </div>
                    );
                  })}
                </div>
              </Card>
            )}

            {/* 结果信息 */}
            {selectedTask.status === 'completed' && selectedTask.subtitle_path && (
              <Card size="small" title={<Space><CheckCircleFilled style={{ color: '#52c41a' }} /> 生成结果</Space>} style={{ borderRadius: 12 }}>
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="字幕文件">
                    <Text copyable style={{ fontSize: 12 }}>{selectedTask.subtitle_path}</Text>
                  </Descriptions.Item>
                </Descriptions>
              </Card>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default Tasks;
