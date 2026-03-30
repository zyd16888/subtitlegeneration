import React from 'react';
import { Tag } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import type { TaskStatus } from '../types/api';

interface TaskStatusBadgeProps {
  status: TaskStatus;
}

/**
 * 任务状态徽章组件
 * 
 * 显示任务状态的彩色标签，带有对应的图标
 * 
 * @param status - 任务状态
 */
const TaskStatusBadge: React.FC<TaskStatusBadgeProps> = ({ status }) => {
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

export default TaskStatusBadge;
