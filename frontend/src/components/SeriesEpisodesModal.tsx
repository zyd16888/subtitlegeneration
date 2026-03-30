import React, { useState, useEffect } from 'react';
import {
  Modal,
  Table,
  Button,
  Select,
  message,
  Space,
  Tag,
  Image,
  Alert,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import { api } from '../services/api';
import type { MediaItem, TaskConfig, SystemConfig } from '../types/api';

const { Option } = Select;

interface SeriesEpisodesModalProps {
  visible: boolean;
  seriesId: string;
  seriesName: string;
  configValid: boolean;
  configMessage: string;
  onClose: () => void;
  onGenerateSubtitles: (tasks: TaskConfig[]) => void;
}

interface EpisodeConfig extends MediaItem {
  asr_engine?: 'sherpa-onnx' | 'cloud';
  translation_service?: 'openai' | 'deepseek' | 'local';
  openai_model?: string;
}

/**
 * 剧集集数详情对话框
 * 
 * 显示剧集下的所有集，支持：
 * - 选择要生成字幕的集
 * - 为每一集单独配置 ASR 引擎和翻译服务
 */
const SeriesEpisodesModal: React.FC<SeriesEpisodesModalProps> = ({
  visible,
  seriesId,
  seriesName,
  configValid,
  configMessage,
  onClose,
  onGenerateSubtitles,
}) => {
  const [episodes, setEpisodes] = useState<EpisodeConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [globalConfig, setGlobalConfig] = useState<SystemConfig | null>(null);

  // 加载剧集集数
  const fetchEpisodes = async () => {
    setLoading(true);
    try {
      const data = await api.media.getSeriesEpisodes(seriesId);
      setEpisodes(data.map(ep => ({ ...ep })));
    } catch (err: any) {
      message.error('获取剧集集数失败');
    } finally {
      setLoading(false);
    }
  };

  // 加载全局配置
  const fetchGlobalConfig = async () => {
    try {
      const config = await api.config.getConfig();
      setGlobalConfig(config);
    } catch (err) {
      console.error('获取全局配置失败:', err);
    }
  };

  useEffect(() => {
    if (visible) {
      fetchEpisodes();
      fetchGlobalConfig();
      setSelectedRowKeys([]);
    }
  }, [visible, seriesId]);

  // 更新单集配置
  const updateEpisodeConfig = (
    episodeId: string,
    field: keyof EpisodeConfig,
    value: any
  ) => {
    setEpisodes(prev =>
      prev.map(ep =>
        ep.id === episodeId ? { ...ep, [field]: value } : ep
      )
    );
  };

  // 处理生成字幕
  const handleGenerate = () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择要生成字幕的集');
      return;
    }

    const tasks: TaskConfig[] = selectedRowKeys.map(id => {
      const episode = episodes.find(ep => ep.id === id);
      return {
        media_item_id: id,
        asr_engine: episode?.asr_engine,
        translation_service: episode?.translation_service,
        openai_model: episode?.openai_model,
      };
    });

    onGenerateSubtitles(tasks);
    onClose();
  };

  const columns = [
    {
      title: '缩略图',
      dataIndex: 'image_url',
      key: 'image_url',
      width: 80,
      render: (url: string, record: MediaItem) => (
        url ? (
          <Image
            src={url}
            alt={record.name}
            width={60}
            height={40}
            style={{ objectFit: 'cover' }}
            fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mN8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
          />
        ) : (
          <div style={{ width: 60, height: 40, background: '#f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <PlayCircleOutlined style={{ fontSize: 20, color: '#ccc' }} />
          </div>
        )
      ),
    },
    {
      title: '集名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
    },
    {
      title: '字幕状态',
      dataIndex: 'has_subtitles',
      key: 'has_subtitles',
      width: 100,
      render: (hasSubtitles: boolean) =>
        hasSubtitles ? (
          <Tag icon={<CheckCircleOutlined />} color="success">
            已有字幕
          </Tag>
        ) : (
          <Tag icon={<CloseCircleOutlined />} color="error">
            无字幕
          </Tag>
        ),
    },
    {
      title: 'ASR 引擎',
      dataIndex: 'asr_engine',
      key: 'asr_engine',
      width: 150,
      render: (_: any, record: EpisodeConfig) => (
        <Select
          size="small"
          style={{ width: '100%' }}
          placeholder="使用全局配置"
          value={record.asr_engine}
          onChange={(value) => updateEpisodeConfig(record.id, 'asr_engine', value)}
          allowClear
        >
          <Option value="sherpa-onnx">Sherpa-ONNX</Option>
          <Option value="cloud">云端 ASR</Option>
        </Select>
      ),
    },
    {
      title: '翻译服务',
      dataIndex: 'translation_service',
      key: 'translation_service',
      width: 150,
      render: (_: any, record: EpisodeConfig) => (
        <Select
          size="small"
          style={{ width: '100%' }}
          placeholder="使用全局配置"
          value={record.translation_service}
          onChange={(value) => updateEpisodeConfig(record.id, 'translation_service', value)}
          allowClear
        >
          <Option value="openai">OpenAI</Option>
          <Option value="deepseek">DeepSeek</Option>
          <Option value="local">本地 LLM</Option>
        </Select>
      ),
    },
    {
      title: '模型',
      dataIndex: 'openai_model',
      key: 'openai_model',
      width: 150,
      render: (_: any, record: EpisodeConfig) => (
        <Select
          size="small"
          style={{ width: '100%' }}
          placeholder="使用全局配置"
          value={record.openai_model}
          onChange={(value) => updateEpisodeConfig(record.id, 'openai_model', value)}
          allowClear
          disabled={record.translation_service !== 'openai' && record.translation_service !== 'deepseek'}
        >
          <Option value="gpt-4">GPT-4</Option>
          <Option value="gpt-3.5-turbo">GPT-3.5 Turbo</Option>
          <Option value="deepseek-chat">DeepSeek Chat</Option>
        </Select>
      ),
    },
  ];

  const rowSelection = {
    selectedRowKeys,
    onChange: (keys: React.Key[]) => {
      setSelectedRowKeys(keys as string[]);
    },
  };

  return (
    <Modal
      title={`${seriesName} - 选择集数`}
      open={visible}
      onCancel={onClose}
      width={1200}
      footer={[
        <Button key="cancel" onClick={onClose}>
          取消
        </Button>,
        <Button
          key="generate"
          type="primary"
          icon={<PlayCircleOutlined />}
          onClick={handleGenerate}
          disabled={selectedRowKeys.length === 0 || !configValid}
        >
          生成字幕 ({selectedRowKeys.length})
        </Button>,
      ]}
    >
      {/* 配置不完整警告 */}
      {!configValid && (
        <Alert
          message="配置不完整"
          description={configMessage}
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      <div style={{ marginBottom: 16 }}>
        <Space>
          <span>当前全局配置：</span>
          <Tag>ASR: {globalConfig?.asr_engine || '未配置'}</Tag>
          <Tag>翻译: {globalConfig?.translation_service || '未配置'}</Tag>
          {globalConfig?.openai_model && <Tag>模型: {globalConfig.openai_model}</Tag>}
        </Space>
      </div>
      <Table
        rowSelection={rowSelection}
        columns={columns}
        dataSource={episodes}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 10 }}
        size="small"
      />
    </Modal>
  );
};

export default SeriesEpisodesModal;
