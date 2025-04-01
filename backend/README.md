# A 股投资 Agent 后端 API

本文档提供 A 股投资 Agent 后端 API 的概览和使用指南。

## API 结构

API 分为两个主要部分：

1. **新 API** (`/api/*`): 新的标准化 API，使用统一的响应格式
2. **旧 API** (`/*`): 原有的 API，为向后兼容性保留

### 统一响应格式

所有新 API 端点使用统一的`ApiResponse`格式:

```json
{
  "success": true,
  "message": "操作成功",
  "data": {
    /* 具体响应数据 */
  },
  "timestamp": "2023-04-01T12:34:56.789Z"
}
```

## 运行历史查询

系统提供两种访问运行历史的方式：

### 1. 通过`/api/runs/*`访问（实时状态）

这些端点访问`api_state`模块管理的内存中状态，适用于：

- 查询正在进行中的分析任务
- 获取最近完成的运行状态

主要端点：

- `GET /api/runs/`: 获取所有运行历史
- `GET /api/runs/{run_id}`: 获取特定运行的详情

### 2. 通过`/runs/*`访问（持久化日志）

这些端点访问`BaseLogStorage`接口实现的持久化存储，适用于：

- 查询详细的运行日志和 Agent 执行数据
- 分析完整的工作流程和 Agent 相互作用

主要端点：

- `GET /runs/`: 获取所有运行历史
- `GET /runs/{run_id}`: 获取特定运行的详情
- `GET /runs/{run_id}/agents`: 获取运行中所有 Agent 的执行情况
- `GET /runs/{run_id}/agents/{agent_name}`: 获取特定 Agent 的详细执行信息
- `GET /runs/{run_id}/flow`: 获取完整的工作流程图数据

## 常见问题解决

### 问题：运行 ID 在`/api/runs/`中可见但在`/runs/`中不可见

这通常是因为运行被注册到了`api_state`但没有生成相应的 Agent 执行日志。解决方法：

1. 确保所有 Agent 执行都使用`log_agent_execution`装饰器
2. 确保工作流使用`workflow_run`上下文管理器
3. 请等待分析完成，日志可能会延迟写入

### 问题：运行 ID 在`/runs/`中可见但在`/api/runs/`中不可见

这种情况较少见，可能是因为 Agent 日志被直接写入存储但没有在`api_state`中注册。解决方法：

1. 检查 Agent 执行代码是否正确调用了`api_state.register_run`
2. 确认运行时间，`api_state`中的数据可能会在重启后丢失

## 开发指南

添加新的 API 端点时请遵循以下规则：

1. 将新端点放入适当的路由模块中
2. 使用`ApiResponse`包装所有响应
3. 为接口提供清晰的文档字符串
4. 添加适当的错误处理
