import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Empty,
  Input,
  message,
  Modal,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  CloudDownloadOutlined,
  InfoCircleOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';

import { api, ApiError } from '../services/api';
import type {
  MediaItem,
  SubtitleSearchLanguageInfo,
  SubtitleSearchResult,
  SystemConfig,
} from '../types/api';
import { LANGUAGE_NAMES } from '../types/api';
import { useIsMobile } from '../utils/useIsMobile';

const { Text } = Typography;

interface SubtitleSearchModalProps {
  visible: boolean;
  mediaItem: MediaItem;
  libraryId?: string;
  pathMappingIndex?: number;
  onClose: () => void;
  onApplied?: () => void;
}

const LANG_SOURCE_LABELS: Record<string, string> = {
  api_field: 'API',
  filename: '文件名',
  content: '内容检测',
  unknown: '未识别',
};

const ALL_LANG_OPTIONS: { value: string; label: string }[] = [
  { value: 'zh', label: '中文 (zh)' },
  { value: 'zh-Hant', label: '繁体中文 (zh-Hant)' },
  { value: 'en', label: '英语 (en)' },
  { value: 'ja', label: '日语 (ja)' },
  { value: 'ko', label: '韩语 (ko)' },
  { value: 'fr', label: '法语 (fr)' },
  { value: 'de', label: '德语 (de)' },
  { value: 'es', label: '西班牙语 (es)' },
  { value: 'ru', label: '俄语 (ru)' },
];

function formatDuration(ms: number): string {
  if (!ms || ms <= 0) return '—';
  const totalSec = Math.round(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function languageLabel(language: SubtitleSearchLanguageInfo): string {
  if (!language.code) return '未识别';
  const name = LANGUAGE_NAMES[language.code] || language.code;
  if (language.is_bilingual && language.secondary_code) {
    const secondary = LANGUAGE_NAMES[language.secondary_code] || language.secondary_code;
    return `${name} + ${secondary}`;
  }
  return name;
}

/**
 * 从标题中提取 AV 番号（与后端 query_builder.extract_av_codes 行为对齐）。
 * 例如 "ADN-351 周末限定..." → ["ADN-351"]，"周末ADN-351..." → ["ADN-351"]。
 * 使用 lookaround 而非 \b，确保中文紧贴英文时也能匹配。
 */
function extractAvCodes(title: string): string[] {
  if (!title) return [];
  const re = /(?<![A-Za-z0-9])([A-Za-z]{2,7})[-_]?(\d{2,6})(?![A-Za-z0-9])/g;
  const seen = new Set<string>();
  const result: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(title)) !== null) {
    const normalized = `${m[1].toUpperCase()}-${m[2]}`;
    if (!seen.has(normalized)) {
      seen.add(normalized);
      result.push(normalized);
    }
  }
  return result;
}

function buildDefaultQuery(title: string | undefined): string {
  if (!title) return '';
  const codes = extractAvCodes(title);
  return codes.length > 0 ? codes[0] : title;
}

const SubtitleSearchModal: React.FC<SubtitleSearchModalProps> = ({
  visible,
  mediaItem,
  libraryId,
  pathMappingIndex,
  onClose,
  onApplied,
}) => {
  const isMobile = useIsMobile();
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [results, setResults] = useState<SubtitleSearchResult[]>([]);
  const [mediaDurationMs, setMediaDurationMs] = useState<number | null>(null);
  const [targetLanguages, setTargetLanguages] = useState<string[]>([]);
  const [globalConfig, setGlobalConfig] = useState<SystemConfig | null>(null);
  // 行级状态：被覆盖的语言、应用中
  const [overrideLang, setOverrideLang] = useState<Record<string, string | undefined>>({});
  const [applyingKey, setApplyingKey] = useState<string | null>(null);

  // 重置状态 + 默认查询（自动从标题提番号）
  useEffect(() => {
    if (!visible) return;
    setQuery(buildDefaultQuery(mediaItem?.name));
    setResults([]);
    setSearched(false);
    setOverrideLang({});
    setApplyingKey(null);
    setMediaDurationMs(null);
    setTargetLanguages([]);

    api.config
      .getConfig()
      .then((cfg) => setGlobalConfig(cfg))
      .catch(() => setGlobalConfig(null));
  }, [visible, mediaItem]);

  const handleSearch = async () => {
    const q = query.trim();
    if (!q) {
      message.warning('请输入查询关键词');
      return;
    }
    setSearching(true);
    try {
      const resp = await api.subtitleSearch.search({
        query: q,
        media_item_id: mediaItem?.id,
      });
      setResults(resp.items);
      setMediaDurationMs(resp.media_duration_ms ?? null);
      setTargetLanguages(resp.target_languages || []);
      setSearched(true);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : '搜索失败';
      message.error(msg);
    } finally {
      setSearching(false);
    }
  };

  const rowKey = (record: SubtitleSearchResult) => record.gcid || record.url;

  const handleApply = async (record: SubtitleSearchResult) => {
    const key = rowKey(record);
    const finalLang = overrideLang[key] ?? record.language.code ?? undefined;
    if (!finalLang) {
      message.warning('该字幕未识别出语言，请先选择语言再应用');
      return;
    }
    setApplyingKey(key);
    try {
      const resp = await api.subtitleSearch.apply({
        media_item_id: mediaItem.id,
        url: record.url,
        ext: record.ext,
        name: record.name,
        raw_languages: record.raw_languages,
        library_id: libraryId,
        path_mapping_index: pathMappingIndex,
        force_language: overrideLang[key], // 仅在用户显式覆盖时强制
      });
      const langText = resp.language.code ? LANGUAGE_NAMES[resp.language.code] || resp.language.code : '未知';
      message.success(`已应用字幕 (${langText}) → ${resp.target_path}`);
      onApplied?.();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : '应用失败';
      message.error(msg);
    } finally {
      setApplyingKey(null);
    }
  };

  const columns: ColumnsType<SubtitleSearchResult> = useMemo(() => {
    const cols: ColumnsType<SubtitleSearchResult> = [
      {
        title: '名称',
        dataIndex: 'name',
        key: 'name',
        render: (text: string, record) => (
          <Space direction="vertical" size={2}>
            <Text style={{ wordBreak: 'break-all' }}>{text || '(无名称)'}</Text>
            {record.extra_name && (
              <Text type="secondary" style={{ fontSize: 11 }}>
                {record.extra_name}
              </Text>
            )}
          </Space>
        ),
      },
      {
        title: '语言',
        key: 'language',
        width: 200,
        render: (_, record) => {
          const key = rowKey(record);
          const detected = record.language;
          const sourceLabel = LANG_SOURCE_LABELS[detected.source] || detected.source;
          return (
            <Space direction="vertical" size={4}>
              {detected.code ? (
                <Tag color={detected.is_bilingual ? 'geekblue' : 'blue'}>
                  {languageLabel(detected)}
                </Tag>
              ) : (
                <Tag color="orange">未识别</Tag>
              )}
              <Tooltip title={`置信度 ${detected.confidence.toFixed(2)} · 来源: ${sourceLabel}`}>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {sourceLabel} · {(detected.confidence * 100).toFixed(0)}%
                </Text>
              </Tooltip>
              <Select
                size="small"
                style={{ width: 150 }}
                placeholder="覆盖语言"
                allowClear
                value={overrideLang[key]}
                onChange={(val) =>
                  setOverrideLang((prev) => ({ ...prev, [key]: val || undefined }))
                }
                options={ALL_LANG_OPTIONS}
              />
            </Space>
          );
        },
      },
      {
        title: '格式',
        dataIndex: 'ext',
        key: 'ext',
        width: 70,
        render: (ext: string) => <Tag>{(ext || '').toUpperCase()}</Tag>,
      },
      {
        title: '时长',
        dataIndex: 'duration_ms',
        key: 'duration_ms',
        width: 100,
        render: (ms: number) => formatDuration(ms),
      },
      {
        title: (
          <Space size={4}>
            分数
            <Tooltip title="综合分（语言/时长/扩展/文件名/双语）">
              <InfoCircleOutlined />
            </Tooltip>
          </Space>
        ),
        dataIndex: 'score',
        key: 'score',
        width: 80,
        sorter: (a, b) => a.score - b.score,
        defaultSortOrder: 'descend',
        render: (score: number) => {
          const color =
            score >= 0.7 ? '#52c41a'
            : score >= 0.4 ? '#faad14'
            : '#8c8c8c';
          return (
            <Text strong style={{ color, fontSize: 13 }}>
              {score.toFixed(2)}
            </Text>
          );
        },
      },
      {
        title: '操作',
        key: 'action',
        width: 100,
        fixed: isMobile ? undefined : 'right',
        render: (_, record) => {
          const key = rowKey(record);
          return (
            <Button
              type="primary"
              size="small"
              icon={<CloudDownloadOutlined />}
              loading={applyingKey === key}
              disabled={applyingKey !== null && applyingKey !== key}
              onClick={() => handleApply(record)}
            >
              应用
            </Button>
          );
        },
      },
    ];
    return cols;
  }, [overrideLang, applyingKey, isMobile]);

  const pathMappingMissing = !globalConfig?.path_mappings || globalConfig.path_mappings.length === 0;

  return (
    <Modal
      title="搜索现有字幕"
      open={visible}
      onCancel={onClose}
      width={isMobile ? '100%' : 900}
      style={isMobile ? { top: 0, paddingBottom: 0, maxWidth: '100vw', margin: 0 } : undefined}
      styles={isMobile ? { body: { maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' } } : undefined}
      footer={[
        <Button key="close" onClick={onClose}>
          关闭
        </Button>,
      ]}
    >
      {pathMappingMissing && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="未配置路径映射规则"
          description="字幕应用需要将文件复制到视频目录，请先在设置中添加路径映射。"
        />
      )}

      <div style={{ marginBottom: 12 }}>
        <Space size={8} wrap>
          <Text strong>{mediaItem?.name}</Text>
          <Tag>{mediaItem?.type}</Tag>
        </Space>
      </div>

      <Space.Compact style={{ width: '100%', marginBottom: 12 }}>
        <Input
          placeholder="查询关键词，如电影名 / SxxExx / 番号"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onPressEnter={handleSearch}
          allowClear
        />
        <Button
          type="primary"
          icon={<SearchOutlined />}
          loading={searching}
          onClick={handleSearch}
        >
          搜索
        </Button>
      </Space.Compact>

      {searched && targetLanguages.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <Space size={6} wrap>
            <Text type="secondary" style={{ fontSize: 12 }}>
              目标语言:
            </Text>
            {targetLanguages.map((lang) => (
              <Tag key={lang}>{LANGUAGE_NAMES[lang] || lang}</Tag>
            ))}
            {mediaDurationMs ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                媒体时长 {formatDuration(mediaDurationMs)}
              </Text>
            ) : (
              <Text type="secondary" style={{ fontSize: 12 }}>
                媒体时长未知
              </Text>
            )}
          </Space>
        </div>
      )}

      <Spin spinning={searching}>
        {searched && results.length === 0 ? (
          <Empty description="无匹配字幕" />
        ) : (
          <Table
            rowKey={rowKey}
            columns={columns}
            dataSource={results}
            pagination={false}
            size="small"
            scroll={{ x: isMobile ? 700 : undefined, y: 400 }}
          />
        )}
      </Spin>
    </Modal>
  );
};

export default SubtitleSearchModal;
