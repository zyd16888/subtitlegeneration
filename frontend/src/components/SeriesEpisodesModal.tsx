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
  Typography,
  Tooltip,
  Switch,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  PlayCircleOutlined,
  GlobalOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { api, getImageUrl } from '../services/api';
import type { MediaItem, TaskConfig, SystemConfig } from '../types/api';

const { Text } = Typography;

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
  path_mapping_index?: number;
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
  const [sharedPathMappingIndex, setSharedPathMappingIndex] = useState<number | undefined>(undefined);
  const [sharedSourceLanguage, setSharedSourceLanguage] = useState<string | undefined>(undefined);
  const [sharedTargetLanguages, setSharedTargetLanguages] = useState<string[]>([]);
  const [sharedKeepSourceSubtitle, setSharedKeepSourceSubtitle] = useState<boolean | undefined>(undefined);

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
        path_mapping_index: sharedPathMappingIndex,
        source_language: sharedSourceLanguage,
        target_languages: sharedTargetLanguages.length > 0 ? sharedTargetLanguages : undefined,
        keep_source_subtitle: sharedKeepSourceSubtitle,
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
            src={getImageUrl(url)}
            alt={record.name}
            width={60}
            height={40}
            style={{ objectFit: 'cover' }}
            fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mN8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
          />
        ) : (
          <div style={{ width: 60, height: 40, background: 'var(--bg-spotlight)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <PlayCircleOutlined style={{ fontSize: 20, color: 'var(--placeholder-icon)' }} />
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
        <Space wrap>
          <span>当前全局配置：</span>
          <Tag>ASR: {globalConfig?.asr_engine || '未配置'}</Tag>
          <Tag>识别语言: {globalConfig?.source_language || 'ja'}</Tag>
          <Tag>
            目标语言: {
              globalConfig?.target_languages && globalConfig.target_languages.length > 0
                ? globalConfig.target_languages.join(', ')
                : (globalConfig?.target_language || 'zh')
            }
          </Tag>
          {globalConfig?.keep_source_subtitle && <Tag color="cyan">保留源字幕</Tag>}
          <Tag>翻译: {globalConfig?.translation_service || '未配置'}</Tag>
          {globalConfig?.openai_model && <Tag>模型: {globalConfig.openai_model}</Tag>}
          <Tag>
            路径映射: {globalConfig?.path_mappings?.length || 0} 条
            {globalConfig?.path_mappings && globalConfig.path_mappings.length > 0 && (
              <Tooltip title={
                <div>
                  {globalConfig.path_mappings.map((m, i) => (
                    <div key={i}>{m.name || `规则${i + 1}`}: {m.emby_prefix} → {m.local_prefix}</div>
                  ))}
                </div>
              }>
                <InfoCircleOutlined style={{ marginLeft: 4 }} />
              </Tooltip>
            )}
          </Tag>
        </Space>
      </div>

      <div style={{ marginBottom: 16, padding: '12px 16px', background: 'var(--info-bg)', borderRadius: 8 }}>
        <Space size="large" wrap>
          <div>
            <Text strong>批量识别语言：</Text>
            <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
              Whisper 模型生效，Online/Transducer 模型忽略
            </Text>
          </div>
          <Select
            style={{ minWidth: 200 }}
            placeholder={`使用全局配置 (${globalConfig?.source_language || 'ja'})`}
            value={sharedSourceLanguage}
            onChange={setSharedSourceLanguage}
            allowClear
          >
            <Option value="ja">日语 (ja)</Option>
            <Option value="zh">中文 (zh)</Option>
            <Option value="en">英语 (en)</Option>
            <Option value="ko">韩语 (ko)</Option>
            <Option value="fr">法语 (fr)</Option>
            <Option value="de">德语 (de)</Option>
            <Option value="es">西班牙语 (es)</Option>
            <Option value="ru">俄语 (ru)</Option>
          </Select>
        </Space>
      </div>

      <div style={{ marginBottom: 16, padding: '12px 16px', background: 'var(--info-bg)', borderRadius: 8 }}>
        <Space size="large" wrap>
          <div>
            <Text strong>批量目标语言：</Text>
            <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
              可多选；留空使用全局配置
            </Text>
          </div>
          <Select
            mode="multiple"
            style={{ minWidth: 260 }}
            placeholder={`使用全局配置 (${
              globalConfig?.target_languages && globalConfig.target_languages.length > 0
                ? globalConfig.target_languages.join(', ')
                : (globalConfig?.target_language || 'zh')
            })`}
            value={sharedTargetLanguages}
            onChange={setSharedTargetLanguages}
            allowClear
          >
            <Option value="zh">中文 (zh)</Option>
            <Option value="ja">日语 (ja)</Option>
            <Option value="en">英语 (en)</Option>
            <Option value="ko">韩语 (ko)</Option>
            <Option value="fr">法语 (fr)</Option>
            <Option value="de">德语 (de)</Option>
            <Option value="es">西班牙语 (es)</Option>
            <Option value="ru">俄语 (ru)</Option>
          </Select>
          <div>
            <Text strong>保留源语言字幕：</Text>
            <Tooltip title="除目标语言字幕外额外输出一份源语言字幕（ASR 原文）。不设置则跟随全局配置。">
              <InfoCircleOutlined style={{ marginLeft: 4 }} />
            </Tooltip>
          </div>
          <Switch
            checked={sharedKeepSourceSubtitle === true}
            onChange={(checked) => setSharedKeepSourceSubtitle(checked ? true : undefined)}
          />
          {sharedKeepSourceSubtitle !== undefined && (
            <Button size="small" type="link" onClick={() => setSharedKeepSourceSubtitle(undefined)}>
              跟随全局
            </Button>
          )}
        </Space>
      </div>

      <div style={{ marginBottom: 16, padding: '12px 16px', background: 'var(--info-bg)', borderRadius: 8 }}>
        <Space size="large" wrap>
          <div>
            <Text strong>批量路径映射规则：</Text>
            <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
              所有选中集将使用相同规则
            </Text>
          </div>
          <Select
            style={{ minWidth: 300 }}
            placeholder="使用媒体库默认规则"
            value={sharedPathMappingIndex}
            onChange={setSharedPathMappingIndex}
            allowClear
            disabled={!globalConfig?.path_mappings || globalConfig.path_mappings.length === 0}
          >
            {globalConfig?.path_mappings?.map((mapping, idx) => (
              <Option key={idx} value={idx}>
                <Space>
                  <GlobalOutlined />
                  <Text strong>{mapping.name || `规则 ${idx + 1}`}</Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {mapping.emby_prefix} → {mapping.local_prefix}
                  </Text>
                </Space>
              </Option>
            ))}
          </Select>
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
