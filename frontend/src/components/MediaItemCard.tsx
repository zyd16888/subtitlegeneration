import React from 'react';
import { Card, Checkbox } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import type { MediaItem } from '../types/api';

interface MediaItemCardProps {
  item: MediaItem;
  selected: boolean;
  onSelect: (itemId: string, checked: boolean) => void;
}

/**
 * 媒体项卡片组件
 * 
 * 显示媒体项的缩略图、标题、类型和字幕状态
 * 支持选择功能
 * 
 * @param item - 媒体项数据
 * @param selected - 是否被选中
 * @param onSelect - 选择状态改变回调
 */
const MediaItemCard: React.FC<MediaItemCardProps> = ({ item, selected, onSelect }) => {
  return (
    <Card
      hoverable
      style={{
        border: selected ? '2px solid #1890ff' : '1px solid #f0f0f0',
      }}
      cover={
        <div
          style={{
            position: 'relative',
            paddingTop: '150%',
            background: '#f0f0f0',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <PlayCircleOutlined style={{ fontSize: 48, color: '#ccc' }} />
          </div>
          <Checkbox
            checked={selected}
            onChange={(e) => onSelect(item.id, e.target.checked)}
            style={{
              position: 'absolute',
              top: 8,
              left: 8,
              zIndex: 1,
            }}
          />
          <div
            style={{
              position: 'absolute',
              top: 8,
              right: 8,
              zIndex: 1,
            }}
          >
            {item.has_subtitles ? (
              <CheckCircleOutlined
                style={{ fontSize: 24, color: '#52c41a' }}
                title="已有字幕"
              />
            ) : (
              <CloseCircleOutlined
                style={{ fontSize: 24, color: '#ff4d4f' }}
                title="无字幕"
              />
            )}
          </div>
        </div>
      }
    >
      <Card.Meta
        title={
          <div
            style={{
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={item.name}
          >
            {item.name}
          </div>
        }
        description={
          <div style={{ fontSize: 12, color: '#999' }}>{item.type}</div>
        }
      />
    </Card>
  );
};

export default MediaItemCard;
