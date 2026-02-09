// API 配置
// 通过 nginx 代理，使用相对路径或当前域名

const getApiBase = () => {
  // 生产环境：通过 nginx 代理，使用当前域名（无端口）
  // 开发环境：如果端口是 8888（Vite 开发服务器），则使用 8000 端口连接后端
  const { protocol, hostname, port } = window.location;
  
  // 开发环境检测（Vite 默认端口 5173，但配置中是 8888）
  if (port === '8888' || port === '5173' || hostname === 'localhost' || hostname === '127.0.0.1') {
    return `${protocol}//${hostname}:8000`;
  }
  
  // 生产环境：使用当前域名（nginx 会代理到后端）
  return `${protocol}//${hostname}`;
};

export const API_BASE = getApiBase();
export const API_URL = `${API_BASE}/api`;
