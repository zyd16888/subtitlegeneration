import React, { useState } from 'react';
import { Card, Space, Row, Col } from 'antd';
import TaskStatusBadge from './TaskStatusBadge';
import ProgressBar from './ProgressBar';
import MediaItemCard from './MediaItemCard';
import { TaskStatus } from '../types/api';
import type { MediaItem } from '../types/api';

/**
 * 组件演示页面
 * 
 * 用于展示和测试新创建的可复用组件
 * 仅用于开发和测试目的
 */
const ComponentsDemo: React.FC = () => {
  const [selectedItems, setSelectedItems] = useState<string[]>([]);

  // 测试数据
  const taskStatuses: TaskStatus[] = [
    TaskStatus.PENDING,
    TaskStatus.PROCESSING,
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
  ];
  
  const testMediaItems: MediaItem[] = [
    {
      id: '1',
      name: '测试电影 1',
      type: 'Movie',
      has_subtitles: true,
    },
    {
      id: '2',
      name: '测试剧集 2',
      type: 'Series',
      has_subtitles: false,
    },
    {
      id: '3',
      name: '测试单集 3',
      type: 'Episode',
      has_subtitles: true,
    },
  ];

  const handleItemSelect = (itemId: string, checked: boolean) => {
    if (checked) {
      setSelectedItems([...selectedItems, itemId]);
    } else {
      setSelectedItems(selectedItems.filter((id) => id !== itemId));
    }
  };

  return (
    <div style={{ padding: '24px' }}>
      <h1>组件演示</h1>

      {/* TaskStatusBadge 演示 */}
      <Card title="TaskStatusBadge 组件" style={{ marginBottom: 24 }}>
        <Space size="large">
          {taskStatuses.map((status) => (
            <div key={status}>
              <div style={{ marginBottom: 8, fontSize: 12, color: '#999' }}>
                {status}
              </div>
              <TaskStatusBadge status={status} />
            </div>
          ))}
        </Space>
      </Card>

      {/* ProgressBar 演示 */}
      <Card title="ProgressBar 组件" style={{ marginBottom: 24 }}>
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          <div>
            <div style={{ marginBottom: 8 }}>待处理 (0%)</div>
            <ProgressBar progress={0} status={TaskStatus.PENDING} />
          </div>
          <div>
            <div style={{ marginBottom: 8 }}>处理中 (50%)</div>
            <ProgressBar progress={50} status={TaskStatus.PROCESSING} />
          </div>
          <div>
            <div style={{ marginBottom: 8 }}>已完成 (100%)</div>
            <ProgressBar progress={100} status={TaskStatus.COMPLETED} />
          </div>
          <div>
            <div style={{ marginBottom: 8 }}>失败 (30%)</div>
            <ProgressBar progress={30} status={TaskStatus.FAILED} />
          </div>
          <div>
            <div style={{ marginBottom: 8 }}>已取消 (20%)</div>
            <ProgressBar progress={20} status={TaskStatus.CANCELLED} />
          </div>
        </Space>
      </Card>

      {/* MediaItemCard 演示 */}
      <Card title="MediaItemCard 组件" style={{ marginBottom: 24 }}>
        <Row gutter={[16, 16]}>
          {testMediaItems.map((item) => (
            <Col key={item.id} xs={24} sm={12} md={8} lg={6}>
              <MediaItemCard
                item={item}
                selected={selectedItems.includes(item.id)}
                onSelect={handleItemSelect}
              />
            </Col>
          ))}
        </Row>
        <div style={{ marginTop: 16 }}>
          已选择: {selectedItems.length} 项
        </div>
      </Card>
    </div>
  );
};

export default ComponentsDemo;
