import React from 'react';
import { Checkbox, Tag } from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
  PlayCircleOutlined,
} from '@ant-design/icons';
import type { MediaItem } from '../types/api';

interface MediaItemCardProps {
  item: MediaItem;
  selected: boolean;
  onSelect: (itemId: string, checked: boolean) => void;
  index?: number;
}

const MediaItemCard: React.FC<MediaItemCardProps> = ({ item, selected, onSelect, index = 0 }) => {
  return (
    <div
      className="glass-card"
      style={{
        cursor: 'pointer',
        position: 'relative',
        borderRadius: 'var(--radius-card)',
        overflow: 'hidden',
        border: selected ? '2px solid var(--accent-cyan)' : '1px solid var(--glass-border)',
        boxShadow: selected ? '0 0 20px rgba(0, 212, 255, 0.2)' : 'var(--glass-shadow)',
        transform: selected ? 'translateY(-2px)' : 'none',
        transition: 'all var(--trans-base)',
        animation: `fadeInUp 0.5s var(--ease-spring) ${index * 0.05}s both`,
      }}
      onClick={() => onSelect(item.id, !selected)}
    >
      <div style={{ position: 'absolute', top: 12, left: 12, zIndex: 10 }}>
        <Checkbox
          checked={selected}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => onSelect(item.id, e.target.checked)}
          style={{ transform: 'scale(1.2)' }}
        />
      </div>

      <div style={{ position: 'absolute', top: 12, right: 12, zIndex: 10 }}>
        {item.has_subtitles ? (
          <Tag color="success" style={{ margin: 0, borderRadius: 12, background: 'rgba(16, 185, 129, 0.2)', border: '1px solid var(--accent-emerald)' }}>
            <CheckCircleFilled style={{ color: 'var(--accent-emerald)' }} /> 已有
          </Tag>
        ) : (
          <Tag color="error" style={{ margin: 0, borderRadius: 12, background: 'rgba(244, 63, 94, 0.2)', border: '1px solid var(--accent-rose)' }}>
            <CloseCircleFilled style={{ color: 'var(--accent-rose)' }} /> 缺失
          </Tag>
        )}
      </div>

      <div
        style={{
          paddingTop: '150%',
          background: 'linear-gradient(180deg, rgba(255,255,255,0.05) 0%, rgba(0,0,0,0.5) 100%)',
          position: 'relative',
        }}
        className="hover:opacity-80 transition-opacity"
      >
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }}>
          <PlayCircleOutlined style={{ fontSize: 48, color: 'rgba(255,255,255,0.2)' }} />
        </div>
      </div>

      <div style={{ padding: '16px 12px', background: 'rgba(0,0,0,0.4)', borderTop: '1px solid var(--glass-border)' }}>
        <div style={{
          color: 'var(--text-primary)',
          fontSize: 14,
          fontWeight: 600,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          marginBottom: 4,
        }}>
          {item.name}
        </div>
        <div style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
          {item.type}
        </div>
      </div>
    </div>
  );
};

export default MediaItemCard;