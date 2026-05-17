import client from './client'

export default {
  /** 获取用户工作流列表（返回完整配置） */
  getWorkflows() {
    return client.get('/workflows')
  },

  /** 获取单个工作流的完整配置 */
  getWorkflow(workflowId) {
    return client.get(`/workflows/${workflowId}`)
  },

  /** 保存工作流（新建或更新） */
  saveWorkflow(data) {
    return client.post('/workflows', data)
  },

  /** 删除工作流 */
  deleteWorkflow(workflowId) {
    return client.delete(`/workflows/${workflowId}`)
  },

  /** 执行工作流（文档翻译等） */
  execute(data) {
    return client.post('/workflows/execute', data)
  },

  /** 查询工作流执行状态 */
  getExecutionStatus(executionId) {
    return client.get(`/workflows/executions/${executionId}`)
  },

  /** 获取可用的 LLM 模型列表 */
  getModels() {
    return client.get('/workflows/models')
  },

  /** 获取支持的目标语言列表 */
  getLanguages() {
    return client.get('/workflows/languages')
  },

  /** 获取支持的输出格式列表 */
  getOutputFormats() {
    return client.get('/workflows/output-formats')
  },
}
