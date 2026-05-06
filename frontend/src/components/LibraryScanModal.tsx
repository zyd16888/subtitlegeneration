import React, { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Form,
  InputNumber,
  message,
  Modal,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
} from 'antd';
import { PlayCircleOutlined } from '@ant-design/icons';

import { api, ApiError } from '../services/api';
import type { Library, SystemConfig } from '../types/api';
import { LANGUAGE_NAMES } from '../types/api';
import { useIsMobile } from '../utils/useIsMobile';

const { Text } = Typography;
const { Option } = Select;

interface LibraryScanModalProps {
  visible: boolean;
  library: Library;
  onClose: () => void;
  onStarted?: (taskId: string) => void;
}

const TARGET_LANG_OPTIONS = [
  { value: 'zh', label: '中文 (zh)' },
  { value: 'zh-Hant', label: '繁体中文 (zh-Hant)' },
  { value: 'en', label: '英语 (en)' },
  { value: 'ja', label: '日语 (ja)' },
  { value: 'ko', label: '韩语 (ko)' },
];

const LibraryScanModal: React.FC<LibraryScanModalProps> = ({
  visible,
  library,
  onClose,
  onStarted,
}) => {
  const isMobile = useIsMobile();
  const [form] = Form.useForm();
  const [globalConfig, setGlobalConfig] = useState<SystemConfig | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!visible) return;
    api.config
      .getConfig()
      .then((cfg) => {
        setGlobalConfig(cfg);
        // 默认值：跟随全局配置
        form.setFieldsValue({
          target_languages: undefined,  // 留空 = 用全局
          skip_if_has_subtitle: true,
          max_items: 0,
          concurrency: 3,
          item_type: undefined,
        });
      })
      .catch(() => setGlobalConfig(null));
  }, [visible, form]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      const resp = await api.libraryScan.start({
        library_id: library.id,
        target_languages: values.target_languages && values.target_languages.length > 0
          ? values.target_languages
          : undefined,
        skip_if_has_subtitle: values.skip_if_has_subtitle,
        max_items: values.max_items || 0,
        concurrency: values.concurrency || 3,
        item_type: values.item_type || undefined,
      });
      message.success(`已创建扫描任务，可在"任务"页查看进度`);
      onStarted?.(resp.task_id);
      onClose();
    } catch (err) {
      if ((err as any)?.errorFields) return;  // form validation error
      const msg = err instanceof ApiError ? err.message : '启动扫描失败';
      message.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const pathMappingMissing = !globalConfig?.path_mappings || globalConfig.path_mappings.length === 0;
  const searchDisabled = !globalConfig?.subtitle_search_enabled;
  const globalTargets = (globalConfig?.target_languages && globalConfig.target_languages.length > 0)
    ? globalConfig.target_languages
    : (globalConfig?.target_language ? [globalConfig.target_language] : []);

  return (
    <Modal
      title="批量扫描媒体库字幕"
      open={visible}
      onCancel={onClose}
      width={isMobile ? '100%' : 600}
      style={isMobile ? { top: 0, paddingBottom: 0, maxWidth: '100vw', margin: 0 } : undefined}
      styles={isMobile ? { body: { maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' } } : undefined}
      footer={[
        <Button key="cancel" onClick={onClose}>
          取消
        </Button>,
        <Button
          key="start"
          type="primary"
          icon={<PlayCircleOutlined />}
          loading={submitting}
          disabled={searchDisabled || pathMappingMissing}
          onClick={handleSubmit}
        >
          启动扫描
        </Button>,
      ]}
    >
      {searchDisabled && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="字幕搜索功能未启用"
          description="请先到设置 → 字幕搜索中开启总开关。"
        />
      )}
      {pathMappingMissing && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="未配置路径映射规则"
          description="字幕需要复制到视频目录，请先在路径映射中添加规则。"
        />
      )}

      <div style={{ marginBottom: 16, padding: 12, background: 'var(--bg-input, #fafafa)', borderRadius: 8 }}>
        <Space size={6} wrap>
          <Text strong>{library.name}</Text>
          <Tag>{library.type}</Tag>
        </Space>
        <div style={{ marginTop: 6 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            将逐个调用迅雷字幕 API，找到达阈值的字幕则自动下载并应用。来源为第三方网友上传，质量参差不齐。
          </Text>
        </div>
      </div>

      <Form form={form} layout="vertical">
        <Form.Item
          label="目标语言（留空使用全局配置）"
          name="target_languages"
          tooltip="必须每个目标语言都有命中且达阈值才算应用成功"
        >
          <Select
            mode="multiple"
            placeholder={
              globalTargets.length > 0
                ? `使用全局配置 (${globalTargets.join(', ')})`
                : '请选择目标语言'
            }
            allowClear
            options={TARGET_LANG_OPTIONS.map(opt => ({
              value: opt.value,
              label: opt.label,
            }))}
          />
        </Form.Item>

        <Form.Item
          label="跳过已有字幕的媒体项"
          name="skip_if_has_subtitle"
          valuePropName="checked"
          tooltip="开启后，扫描时遇到已有任意字幕的媒体项直接跳过"
        >
          <Switch />
        </Form.Item>

        <Form.Item
          label="仅扫描类型"
          name="item_type"
          tooltip="留空扫描全部，否则只扫描指定类型"
        >
          <Select placeholder="全部类型" allowClear>
            <Option value="Movie">电影</Option>
            <Option value="Episode">单集</Option>
          </Select>
        </Form.Item>

        <Form.Item
          label="最多扫描数量"
          name="max_items"
          tooltip="0 = 不限。建议初次扫描先设上限观察效果"
        >
          <InputNumber min={0} max={10000} step={50} style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item
          label="并发处理项数量"
          name="concurrency"
          tooltip="并发越高越快但可能被 API 限速；建议 2-5"
        >
          <InputNumber min={1} max={10} style={{ width: '100%' }} />
        </Form.Item>

        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          <Text type="secondary">
            目标语言阈值：{(globalConfig?.subtitle_search_min_score ?? 0.7).toFixed(2)}
            （来自字幕搜索设置）
          </Text>
        </div>
      </Form>
    </Modal>
  );
};

export default LibraryScanModal;
