# WebUI 前端说明

本目录用于存放A股智能投顾系统的Web前端代码。

- 前端采用React + Vite实现，支持本地运行和开发。
- 通过API与后端Python主流程交互，实现自然语言股票分析。

## 目录结构
- src/webui/
  - README.md         # 本说明
  - package.json      # 前端依赖
  - vite.config.js    # Vite配置
  - public/           # 静态资源
  - src/              # 前端源码

## 启动方式
1. 进入本目录
2. 安装依赖：`npm install`
3. 启动开发服务器：`npm run dev`

## 功能
- 输入自然语言查询（如"贵州茅台的股票价值"）
- 展示分析结果、投资建议、报告下载等 