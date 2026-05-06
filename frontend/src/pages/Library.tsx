import React, { useState, useEffect } from 'react';
import {
  Row,
  Col,
  Select,
  Input,
  message,
  Spin,
  Alert,
  Pagination,
  Empty,
  Button,
  Typography,
  Space,
  Badge,
  Tag,
} from 'antd';
import {
  SearchOutlined,
  PlayCircleOutlined,
  FilterOutlined,
  AppstoreOutlined,
} from '@ant-design/icons';
import { api, getImageUrl, isRequestCancelled } from '../services/api';
import type { Library, MediaItem, TaskConfig } from '../types/api';
import SeriesEpisodesModal from '../components/SeriesEpisodesModal';
import MediaConfigModal from '../components/MediaConfigModal';

const { Search } = Input;
const { Option } = Select;
const { Text, Title } = Typography;

const MediaItemImage: React.FC<{
  imageUrl?: string;
  name: string;
  hasSubtitles: boolean;
  type: string;
}> = ({ imageUrl, name, hasSubtitles, type }) => {
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        paddingTop: '150%',
        background: 'var(--bg-container)',
        overflow: 'hidden',
        borderRadius: '8px 8px 0 0',
      }}
    >
      {imageUrl && !imageError ? (
        <img
          src={getImageUrl(imageUrl)}
          alt={name}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            opacity: imageLoaded ? 1 : 0,
            transition: 'transform 0.5s ease, opacity 0.3s ease',
          }}
          onLoad={() => setImageLoaded(true)}
          onError={() => setImageError(true)}
          className="media-card-img"
        />
      ) : (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'var(--placeholder-bg)',
            gap: 12,
          }}
        >
          <PlayCircleOutlined style={{ fontSize: 40, color: 'var(--placeholder-icon)' }} />
          <Text type="secondary" style={{ fontSize: 10 }}>暂无封面</Text>
        </div>
      )}

      <div style={{ position: 'absolute', top: 8, right: 8, zIndex: 2 }}>
        <Badge
          count={hasSubtitles ? '已有字幕' : '无字幕'}
          style={{
            background: hasSubtitles ? 'var(--accent-emerald-bg)' : 'var(--accent-rose-bg)',
            color: hasSubtitles ? 'var(--accent-emerald)' : 'var(--accent-rose)',
            border: hasSubtitles ? '1px solid var(--accent-emerald)' : '1px solid var(--accent-rose)',
            boxShadow: 'none',
            fontSize: '10px',
          }}
        />
      </div>

      <div className="media-card-overlay">
        <div className="overlay-content">
          <Button
            type="primary"
            shape="circle"
            icon={<PlayCircleOutlined />}
            size="large"
            style={{
              width: 50,
              height: 50,
              fontSize: 24,
              boxShadow: '0 4px 15px var(--accent-cyan-border)',
            }}
          />
          <div style={{ marginTop: 12, color: 'white', fontSize: 12, fontWeight: 500 }}>
            {type === 'Series' ? '展开剧集' : '生成字幕'}
          </div>
        </div>
      </div>
    </div>
  );
};

const LibraryPage: React.FC = () => {
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [mediaItems, setMediaItems] = useState<MediaItem[]>([]);
  const [selectedLibrary, setSelectedLibrary] = useState<string | undefined>(undefined);
  const [selectedType, setSelectedType] = useState<string | undefined>(undefined);
  const [searchText, setSearchText] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [_error, setError] = useState<string | null>(null);
  const [embyConfigured, setEmbyConfigured] = useState(true);
  const [configValid, setConfigValid] = useState(true);
  const [configMessage, setConfigMessage] = useState<string>('');

  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(24);
  const [total, setTotal] = useState(0);

  const [seriesModalVisible, setSeriesModalVisible] = useState(false);
  const [selectedSeries, setSelectedSeries] = useState<{ id: string; name: string } | null>(null);
  const [mediaConfigModalVisible, setMediaConfigModalVisible] = useState(false);
  const [selectedMediaItem, setSelectedMediaItem] = useState<MediaItem | null>(null);

  const fetchLibraries = async () => {
    try {
      const data = await api.media.getLibraries();
      setLibraries(data);
      if (data.length > 0 && !selectedLibrary) {
        setSelectedLibrary(data[0].id);
      }
      setEmbyConfigured(true);
    } catch (err: any) {
      if (err.message && (err.message.includes('Emby') || err.message.includes('配置'))) {
        setEmbyConfigured(false);
      } else {
        message.error('获取媒体库列表失败');
      }
    }
  };

  const validateConfig = async () => {
    try {
      const result = await api.config.validateConfig();
      setConfigValid(result.is_valid);
      setConfigMessage(result.message);
    } catch (err: any) {
      setConfigValid(false);
      setConfigMessage('无法验证配置，请检查系统设置');
    }
  };

  const fetchMediaItems = async () => {
    if (!embyConfigured || !selectedLibrary) return;

    setLoading(true);
    try {
      const signal = api.createAbortSignal('media-items');
      const response = await api.media.getMediaItems({
        library_id: selectedLibrary,
        item_type: selectedType,
        search: searchText || undefined,
        limit: pageSize,
        offset: (currentPage - 1) * pageSize,
      }, signal);
      setMediaItems(response.items);
      setTotal(response.total);
    } catch (err: any) {
      if (isRequestCancelled(err)) return;
      setError(err.message || '获取媒体项失败');
    } finally {
      setLoading(false);
      setInitialLoading(false);
    }
  };

  useEffect(() => {
    fetchLibraries();
    validateConfig();
  }, []);

  useEffect(() => {
    fetchMediaItems();
    return () => {
      api.cancelRequest('media-items');
    };
  }, [selectedLibrary, selectedType, searchText, currentPage, pageSize]);

  const handleItemClick = (item: MediaItem) => {
    if (item.type === 'Series') {
      setSelectedSeries({ id: item.id, name: item.name });
      setSeriesModalVisible(true);
    } else {
      setSelectedMediaItem(item);
      setMediaConfigModalVisible(true);
    }
  };

  const handleMediaItemGenerateSubtitle = async (task: TaskConfig) => {
    if (!configValid) {
      message.warning('配置不完整，无法生成字幕。');
      return;
    }
    try {
      await api.tasks.createTasks({ tasks: [task], library_id: selectedLibrary });
      message.success('成功创建字幕生成任务');
    } catch (err: any) {
      message.error(err.message || '创建任务失败');
    }
  };

  const handleSeriesGenerateSubtitles = async (tasks: TaskConfig[]) => {
    if (!configValid) {
      message.warning('配置不完整，无法生成字幕。');
      return;
    }
    try {
      await api.tasks.createTasks({ tasks, library_id: selectedLibrary });
      message.success(`成功创建 ${tasks.length} 个任务`);
    } catch (err: any) {
      message.error(err.message || '创建任务失败');
    }
  };

  return (
    <div style={{ maxWidth: 1600, margin: '0 auto' }}>
      {!embyConfigured && (
        <Alert
          message="Emby 未配置"
          description={<Button type="link" onClick={() => window.location.href = '/settings'}>前往设置页面完成配置</Button>}
          type="warning"
          showIcon
          style={{ marginBottom: 24, borderRadius: 12 }}
        />
      )}

      <div className="glass-card animate-fade-in-up delay-1 library-toolbar" style={{ marginBottom: 16, borderRadius: 16, padding: '14px 16px' }}>
        <Row gutter={[12, 12]} align="middle">
          <Col xs={0} md={6}>
            <Space size={12}>
              <div style={{ background: 'var(--accent-cyan)', padding: 8, borderRadius: 8, color: 'white', display: 'flex' }}>
                <AppstoreOutlined />
              </div>
              <Title level={5} style={{ margin: 0 }}>媒体库浏览</Title>
            </Space>
          </Col>
          <Col xs={14} sm={8} md={5}>
            <Select
              style={{ width: '100%' }}
              placeholder="选择媒体库"
              value={selectedLibrary}
              onChange={(val) => { setSelectedLibrary(val); setCurrentPage(1); }}
              suffixIcon={<FilterOutlined />}
            >
              {libraries.map((lib) => (
                <Option key={lib.id} value={lib.id}>{lib.name}</Option>
              ))}
            </Select>
          </Col>
          <Col xs={10} sm={8} md={4}>
            <Select
              style={{ width: '100%' }}
              placeholder="类型"
              value={selectedType}
              onChange={(val) => { setSelectedType(val); setCurrentPage(1); }}
            >
              <Option value={undefined}>全部类型</Option>
              <Option value="Movie">电影</Option>
              <Option value="Series">剧集</Option>
              <Option value="Episode">单集</Option>
            </Select>
          </Col>
          <Col xs={24} sm={8} md={9}>
            <Search
              placeholder="搜索..."
              allowClear
              enterButton={<SearchOutlined />}
              onSearch={(val) => { setSearchText(val); setCurrentPage(1); }}
            />
          </Col>
        </Row>
      </div>

      {initialLoading ? (
        <div style={{ textAlign: 'center', padding: '100px' }}><Spin size="large" tip="正在同步媒体库..." /></div>
      ) : !selectedLibrary ? (
        <Empty description="请从上方选择一个媒体库开始浏览" style={{ marginTop: 100 }} />
      ) : mediaItems.length === 0 && !loading ? (
        <Empty description="该媒体库中没有找到符合条件的媒体项" style={{ marginTop: 100 }} />
      ) : (
        <Spin spinning={loading} tip="加载中...">
          <Row gutter={[20, 20]}>
            {mediaItems.map((item) => (
              <Col key={item.id} xs={12} sm={8} md={6} lg={4} xl={3}>
                <div
                  className="media-card"
                  onClick={() => handleItemClick(item)}
                >
                  <MediaItemImage
                    imageUrl={item.image_url}
                    name={item.name}
                    hasSubtitles={item.has_subtitles}
                    type={item.type}
                  />
                  <div className="media-card-info">
                    <Text className="media-card-title" ellipsis={{ tooltip: item.name }}>{item.name}</Text>
                    <div style={{ marginTop: 4 }}>
                      <Tag style={{ fontSize: 10, border: 'none', margin: 0, color: 'var(--text-secondary)', background: 'var(--bg-spotlight)' }}>
                        {item.type === 'Series' ? '剧集' : item.type === 'Movie' ? '电影' : '视频'}
                      </Tag>
                    </div>
                  </div>
                </div>
              </Col>
            ))}
          </Row>

          <div style={{ marginTop: 40, textAlign: 'center', paddingBottom: 40 }}>
            <Pagination
              current={currentPage}
              pageSize={pageSize}
              total={total}
              onChange={(page, size) => { setCurrentPage(page); setPageSize(size); }}
              showSizeChanger
              showTotal={(total) => <Text type="secondary">共 {total} 个媒体项</Text>}
              pageSizeOptions={['12', '24', '48', '96']}
            />
          </div>
        </Spin>
      )}

      {selectedSeries && (
        <SeriesEpisodesModal
          visible={seriesModalVisible}
          seriesId={selectedSeries.id}
          seriesName={selectedSeries.name}
          configValid={configValid}
          configMessage={configMessage}
          onClose={() => { setSeriesModalVisible(false); setSelectedSeries(null); }}
          onGenerateSubtitles={handleSeriesGenerateSubtitles}
        />
      )}

      {selectedMediaItem && (
        <MediaConfigModal
          visible={mediaConfigModalVisible}
          mediaItem={selectedMediaItem}
          configValid={configValid}
          configMessage={configMessage}
          onClose={() => { setMediaConfigModalVisible(false); setSelectedMediaItem(null); }}
          onGenerateSubtitle={handleMediaItemGenerateSubtitle}
        />
      )}

      <style dangerouslySetInnerHTML={{ __html: `
        .media-card {
          background: var(--bg-container);
          border-radius: 12px;
          border: 1px solid var(--border-color);
          cursor: pointer;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          height: 100%;
          overflow: hidden;
          position: relative;
        }
        .media-card:hover {
          transform: translateY(-8px);
          border-color: var(--card-hover-border);
          box-shadow: var(--card-hover-shadow);
        }
        .media-card:hover .media-card-img {
          transform: scale(1.1);
        }
        .media-card:hover .media-card-overlay {
          opacity: 1;
        }
        .media-card-info {
          padding: 12px;
        }
        .media-card-title {
          font-size: 13px;
          font-weight: 500;
          display: block;
          color: var(--text-primary);
        }
        .media-card-overlay {
          position: absolute;
          top: 0; left: 0; right: 0; bottom: 0;
          background: var(--bg-overlay);
          backdrop-filter: blur(4px);
          display: flex;
          align-items: center;
          justify-content: center;
          opacity: 0;
          transition: opacity 0.3s ease;
          z-index: 1;
        }
        .overlay-content {
          text-align: center;
          transform: translateY(20px);
          transition: transform 0.3s ease;
        }
        .media-card:hover .overlay-content {
          transform: translateY(0);
        }
        
        /* Fix input focus double border */
        .ant-input:hover {
          border-color: var(--accent-cyan-border) !important;
        }

        .ant-input:focus,
        .ant-input-focused {
          border-color: var(--accent-cyan) !important;
          box-shadow: var(--accent-cyan-shadow) !important;
          outline: none !important;
        }

        /* Fix Input with allowClear (affix wrapper) double border */
        .ant-input-affix-wrapper {
          padding: 0 !important;
          border: none !important;
          background: transparent !important;
        }

        .ant-input-affix-wrapper:hover,
        .ant-input-affix-wrapper:focus,
        .ant-input-affix-wrapper-focused {
          border: none !important;
          box-shadow: none !important;
        }

        .ant-input-affix-wrapper .ant-input {
          border: 1px solid var(--glass-border) !important;
          background: var(--bg-input) !important;
        }

        .ant-input-affix-wrapper:hover .ant-input {
          border-color: var(--accent-cyan-border) !important;
        }

        .ant-input-affix-wrapper-focused .ant-input,
        .ant-input-affix-wrapper .ant-input:focus {
          border-color: var(--accent-cyan) !important;
          box-shadow: var(--accent-cyan-shadow) !important;
        }

        /* Fix Search component double border */
        .ant-input-search .ant-input-group .ant-input-affix-wrapper {
          border-right: none !important;
        }

        .ant-input-search .ant-input-group .ant-input-affix-wrapper .ant-input {
          border-right: none !important;
        }

        .ant-input-search-button {
          border: 1px solid var(--glass-border) !important;
          border-left: none !important;
          background: var(--bg-input) !important;
        }

        .ant-input-search:hover .ant-input-search-button {
          border-color: var(--accent-cyan-border) !important;
        }

        .ant-input-search-focused .ant-input-search-button {
          border-color: var(--accent-cyan) !important;
        }
      `}} />
    </div>
  );
};

export default LibraryPage;
