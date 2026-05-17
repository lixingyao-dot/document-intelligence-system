"""
MCP Client - 连接 MCP Documents Reader 服务
"""
import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClient:
    def __init__(self):
        self.session = None
        self.tools = []
    
    async def connect(self):
        """连接到 MCP Documents Reader 服务"""
        server_params = StdioServerParameters(
            command="uvx",
            args=["mcp-documents-reader"],
        )
        
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                self.session = session
                await session.initialize()
                
                # 获取可用工具列表
                response = await session.list_tools()
                self.tools = response.tools
                
                print(f"[MCP] 已连接，可用工具: {[t.name for t in self.tools]}")
                
                # 保持连接直到断开
                try:
                    while True:
                        await asyncio.sleep(1)
                except asyncio.CancelledError:
                    pass
    
    async def call_tool(self, tool_name: str, arguments: dict):
        """调用 MCP 工具"""
        if not self.session:
            raise RuntimeError("MCP 客户端未连接")
        
        result = await self.session.call_tool(tool_name, arguments)
        return result
    
    def get_tools_description(self) -> str:
        """获取工具描述，用于给 LLM 参考"""
        if not self.tools:
            return "无可用工具"
        
        desc = "可用的文档读取工具:\n"
        for tool in self.tools:
            desc += f"- {tool.name}: {tool.description}\n"
            if hasattr(tool, 'inputSchema'):
                desc += f"  参数: {json.dumps(tool.inputSchema, ensure_ascii=False)}\n"
        return desc


async def main():
    """测试 MCP 连接"""
    client = MCPClient()
    await client.connect()


if __name__ == "__main__":
    asyncio.run(main())
