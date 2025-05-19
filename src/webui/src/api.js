import axios from 'axios';

/**
 * 发送分析请求到后端
 * @param {string} query 用户输入的自然语言分析请求
 * @returns {Promise<string>} 分析结果
 */
export async function askAgent(query) {
  const resp = await axios.post('/api/ask', { query });
  return resp.data.result || JSON.stringify(resp.data);
} 