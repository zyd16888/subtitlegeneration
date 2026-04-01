import React, { useState, useEffect } from 'react';
import {
  Modal,
  Form,
  Select,
  Button,
  Space,
  Tag,
  Image,
  Divider,
  Alert,
  Typography,
  Tooltip,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  PlayCircleOutlined,
  GlobalOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { api } from '../services/api';
import type { MediaItem, TaskConfig, SystemConfig } from '../types/api';

const { Text } = Typography;

const { Option } = Select;

interface MediaConfigModalProps {
  visible: boolean;
  mediaItem: MediaItem;
  configValid: boolean;
  configMessage: string;
  onClose: () => void;
  onGenerateSubtitle: (task: TaskConfig) => void;
}

/**
 * 单个媒体项配置对话框
 * 
 * 用于电影等单个媒体项，支持：
 * - 显示媒体项信息
 * - 配置 ASR 引擎
 * - 配置翻译服务
 * - 配置模型
 */
const MediaConfigModal: React.FC<MediaConfigModalProps> = ({
  visible,
  mediaItem,
  configValid,
  configMessage,
  onClose,
  onGenerateSubtitle,
}) => {
  const [form] = Form.useForm();
  const [globalConfig, setGlobalConfig] = useState<SystemConfig | null>(null);
  const [loading, setLoading] = useState(false);

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
      fetchGlobalConfig();
      form.resetFields();
    }
  }, [visible, form]);

  // 处理生成字幕
  const handleGenerate = async () => {
    setLoading(true);
    try {
      const values = await form.validateFields();
      
      const task: TaskConfig = {
        media_item_id: mediaItem.id,
        asr_engine: values.asr_engine,
        translation_service: values.translation_service,
        openai_model: values.openai_model,
        path_mapping_index: values.path_mapping_index,
        source_language: values.source_language,
      };

      onGenerateSubtitle(task);
      onClose();
    } catch (err) {
      console.error('表单验证失败:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title="配置字幕生成"
      open={visible}
      onCancel={onClose}
      width={600}
      footer={[
        <Button key="cancel" onClick={onClose}>
          取消
        </Button>,
        <Button
          key="generate"
          type="primary"
          icon={<PlayCircleOutlined />}
          onClick={handleGenerate}
          loading={loading}
          disabled={!configValid}
        >
          生成字幕
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

      {/* 媒体项信息 */}
      <div style={{ marginBottom: 24 }}>
        <Space size="middle" align="start">
          {mediaItem.image_url ? (
            <Image
              src={mediaItem.image_url}
              alt={mediaItem.name}
              width={120}
              height={180}
              style={{ objectFit: 'cover', borderRadius: 4 }}
              fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mN8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
            />
          ) : (
            <div
              style={{
                width: 120,
                height: 180,
                background: 'var(--bg-spotlight)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 4,
              }}
            >
              <PlayCircleOutlined style={{ fontSize: 48, color: 'var(--placeholder-icon)' }} />
            </div>
          )}
          <div>
            <h3 style={{ margin: 0, marginBottom: 8 }}>{mediaItem.name}</h3>
            <Space>
              <Tag>{mediaItem.type}</Tag>
              {mediaItem.has_subtitles ? (
                <Tag icon={<CheckCircleOutlined />} color="success">
                  已有字幕
                </Tag>
              ) : (
                <Tag icon={<CloseCircleOutlined />} color="error">
                  无字幕
                </Tag>
              )}
            </Space>
          </div>
        </Space>
      </div>

      <Divider />

      {/* 全局配置提示 */}
      <div style={{ marginBottom: 16, padding: 12, background: 'var(--info-bg)', borderRadius: 8 }}>
        <div style={{ marginBottom: 8, fontWeight: 'bold' }}>当前全局配置：</div>
        <Space wrap>
          <Tag>ASR: {globalConfig?.asr_engine || '未配置'}</Tag>
          <Tag>识别语言: {globalConfig?.source_language || 'ja'}</Tag>
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
        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
          留空则使用全局配置
        </div>
      </div>

      {/* 配置表单 */}
      <Form
        form={form}
        layout="vertical"
      >
        <Form.Item
          label="ASR 引擎"
          name="asr_engine"
          tooltip="语音识别引擎，留空使用全局配置"
        >
          <Select placeholder="使用全局配置" allowClear>
            <Option value="sherpa-onnx">Sherpa-ONNX (本地)</Option>
            <Option value="cloud">云端 ASR</Option>
          </Select>
        </Form.Item>

        <Form.Item
          label="识别语言"
          name="source_language"
          tooltip="音频的语言，Whisper 模型支持运行时切换；Online/Transducer 模型为固定语言，此设置不生效。留空使用全局配置"
        >
          <Select placeholder={`使用全局配置 (${globalConfig?.source_language || 'ja'})`} allowClear>
            <Option value="ja">日语 (ja)</Option>
            <Option value="zh">中文 (zh)</Option>
            <Option value="en">英语 (en)</Option>
            <Option value="ko">韩语 (ko)</Option>
            <Option value="fr">法语 (fr)</Option>
            <Option value="de">德语 (de)</Option>
            <Option value="es">西班牙语 (es)</Option>
            <Option value="ru">俄语 (ru)</Option>
          </Select>
        </Form.Item>

        <Form.Item
          label="翻译服务"
          name="translation_service"
          tooltip="翻译服务提供商，留空使用全局配置"
        >
          <Select placeholder="使用全局配置" allowClear>
            <Option value="openai">OpenAI</Option>
            <Option value="deepseek">DeepSeek</Option>
            <Option value="local">本地 LLM</Option>
          </Select>
        </Form.Item>

        <Form.Item
          label="模型"
          name="openai_model"
          tooltip="翻译使用的模型，留空使用全局配置"
        >
          <Select placeholder="使用全局配置" allowClear>
            <Option value="gpt-4">GPT-4</Option>
            <Option value="gpt-3.5-turbo">GPT-3.5 Turbo</Option>
            <Option value="deepseek-chat">DeepSeek Chat</Option>
          </Select>
        </Form.Item>

        <Form.Item
          label="路径映射规则"
          name="path_mapping_index"
          tooltip="字幕文件将复制到映射后的本地目录，留空使用媒体库默认规则"
        >
          {globalConfig?.path_mappings && globalConfig.path_mappings.length > 0 ? (
            <Select placeholder="使用媒体库默认规则" allowClear>
              {globalConfig.path_mappings.map((mapping, idx) => (
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
          ) : (
            <Select placeholder="未配置路径映射" disabled>
              <Option value={undefined}>未配置路径映射</Option>
            </Select>
          )}
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default MediaConfigModal;
