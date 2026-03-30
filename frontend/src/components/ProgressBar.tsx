import React from 'react';
import { Progress } from 'antd';
import type { TaskStatus } from '../types/api';

interface ProgressBarProps {
  progress: number;
  status: TaskStatus;
  size?: 'small' | 'default';
  showInfo?: boolean;
}

/**
 * 任务进度条组件
 * 
 * 根据任务状态显示不同样式的进度条
 * 
 * @param progress - 进度百分比 (0-100)
 * @param status - 任务状态
 * @param size - 进度条大小
 * @param showInfo - 是否显示进度文字
 */
const ProgressBar: React.FC<ProgressBarProps> = ({
  progress,
  status,
  size = 'small',
  showInfo = true,
}) => {
  // 根据任务状态确定进度条状态
  const getProgressStatus = () => {
    if (status === 'completed') {
      return 'success';
    } else if (status === 'failed' || status === 'cancelled') {
      return 'exception';
    } else if (status === 'processing') {
      return 'active';
    } else {
      return 'normal';
    }
  };

  // 确定显示的进度值
  const displayProgress = status === 'completed' ? 100 : progress;

  return (
    <Progress
      percent={displayProgress}
      size={size}
      status={getProgressStatus()}
      showInfo={showInfo}
    />
  );
};

export default ProgressBar;
