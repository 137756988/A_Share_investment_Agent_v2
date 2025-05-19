import React, { useState } from 'react';
import { Input, Button, Card, Typography, Spin, message, Layout, Space, Tag, Divider } from 'antd';
import { SearchOutlined, LineChartOutlined, BarChartOutlined, BulbOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { askAgent } from './api';

const { Title, Paragraph, Text } = Typography;
const { Header, Content, Footer } = Layout;

export default function App() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState('');
  const [loading, setLoading] = useState(false);
  const [queryHistory, setQueryHistory] = useState(['贵州茅台的股票价值', '平安银行是否值得买入', '000858最近的技术分析']);

  // 处理提交
  const handleSubmit = async () => {
    if (!query.trim()) {
      message.warning('请输入您的分析请求，如"贵州茅台的股票价值"');
      return;
    }
    setLoading(true);
    setResult('');
    try {
      const res = await askAgent(query);
      setResult(res);
      // 添加到查询历史
      if (!queryHistory.includes(query)) {
        setQueryHistory([query, ...queryHistory.slice(0, 4)]);
      }
    } catch (err) {
      message.error('请求失败，请检查后端服务是否启动');
      setResult('请求失败，请检查后端服务是否启动。');
    } finally {
      setLoading(false);
    }
  };

  // 使用历史查询
  const useHistoryQuery = (historyQuery) => {
    setQuery(historyQuery);
  };

  // 按下Enter键时提交
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ background: '#1890ff', padding: '0 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', color: 'white' }}>
          <LineChartOutlined style={{ fontSize: 24, marginRight: 12 }} />
          <Title level={3} style={{ color: 'white', margin: 0 }}>A股智能投顾系统</Title>
        </div>
      </Header>
      <Content style={{ padding: '20px 50px' }}>
        <div style={{ maxWidth: 800, margin: '0 auto' }}>
          <Card 
            bordered={false} 
            style={{ borderRadius: 8, marginBottom: 20, boxShadow: '0 4px 12px rgba(0,0,0,0.05)' }}
          >
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <Title level={4}>
                <BulbOutlined style={{ marginRight: 8, color: '#faad14' }} />
                智能投资分析
              </Title>
              
              <Paragraph>
                输入您的自然语言分析请求，系统将利用多Agent协作进行股票分析，提供投资建议。
              </Paragraph>
              
              <Input.TextArea
                rows={3}
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder='请输入您的分析请求，例如"贵州茅台的股票价值"...'
                style={{ borderRadius: 4, fontSize: 16 }}
              />
              
              <Space wrap>
                <Text type="secondary">热门查询:</Text>
                {queryHistory.map((item, index) => (
                  <Tag 
                    key={index} 
                    color="blue" 
                    style={{ cursor: 'pointer' }}
                    onClick={() => useHistoryQuery(item)}
                  >
                    {item.length > 15 ? item.substring(0, 15) + '...' : item}
                  </Tag>
                ))}
              </Space>
              
              <Button 
                type="primary" 
                icon={<SearchOutlined />} 
                onClick={handleSubmit} 
                loading={loading} 
                size="large"
                style={{ borderRadius: 4, height: 48 }}
                block
              >
                开始分析
              </Button>
            </Space>
          </Card>
          
          <Card 
            title={
              <Space>
                <BarChartOutlined style={{ color: '#1890ff' }} />
                <span>分析结果</span>
              </Space>
            }
            bordered={false}
            style={{ 
              borderRadius: 8, 
              minHeight: 300,
              boxShadow: '0 4px 12px rgba(0,0,0,0.05)'
            }}
          >
            {loading ? (
              <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 200 }}>
                <Spin tip="正在分析中..." size="large" />
              </div>
            ) : (
              <div>
                {result ? (
                  <div className="result-container">
                    <Divider orientation="left">
                      <ThunderboltOutlined style={{ color: '#52c41a' }} /> 投资分析
                    </Divider>
                    <Paragraph style={{ whiteSpace: 'pre-wrap', fontSize: 15, lineHeight: 1.8 }}>
                      {result}
                    </Paragraph>
                  </div>
                ) : (
                  <div style={{ color: '#8c8c8c', textAlign: 'center', padding: '40px 0' }}>
                    <SearchOutlined style={{ fontSize: 40, color: '#d9d9d9', display: 'block', margin: '0 auto 20px' }} />
                    <p>分析结果将在这里显示</p>
                  </div>
                )}
              </div>
            )}
          </Card>
        </div>
      </Content>
      <Footer style={{ textAlign: 'center', background: '#f0f2f5' }}>
        A股智能投顾系统 ©{new Date().getFullYear()} - 多智能体协同投资决策
      </Footer>
    </Layout>
  );
} 