"""
HTTP工具 - 调用外部API、Webhook等
"""

import httpx

from .base import BaseTool, ToolParam, ToolResult


class HttpRequest(BaseTool):
    name = "http_request"
    description = "发送HTTP请求，调用外部API"
    parameters = [
        ToolParam(name="url", type="string", description="请求URL", required=True),
        ToolParam(name="method", type="string", description="HTTP方法: GET/POST/PUT/DELETE，默认GET", required=False),
        ToolParam(name="headers", type="object", description="请求头", required=False),
        ToolParam(name="body", type="string", description="请求体(JSON字符串)", required=False),
        ToolParam(name="timeout", type="integer", description="超时秒数，默认15", required=False),
    ]

    def __init__(self, allowed_domains: list[str] = None):
        self.allowed_domains = allowed_domains

    async def execute(self, **kwargs) -> ToolResult:
        url = kwargs.get("url", "")
        method = kwargs.get("method", "GET").upper()
        headers = kwargs.get("headers", {})
        body = kwargs.get("body", "")
        timeout = kwargs.get("timeout", 15)

        if not url:
            return ToolResult(success=False, error="URL为空")

        if self.allowed_domains:
            from urllib.parse import urlparse
            domain = urlparse(url).hostname
            if domain not in self.allowed_domains:
                return ToolResult(success=False, error=f"域名 {domain} 不在白名单中")

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == "GET":
                    resp = await client.get(url, headers=headers)
                elif method == "POST":
                    resp = await client.post(url, headers=headers, content=body)
                elif method == "PUT":
                    resp = await client.put(url, headers=headers, content=body)
                elif method == "DELETE":
                    resp = await client.delete(url, headers=headers)
                else:
                    return ToolResult(success=False, error=f"不支持的HTTP方法: {method}")

                response_text = resp.text[:30000]
                return ToolResult(
                    success=200 <= resp.status_code < 400,
                    data={
                        "status_code": resp.status_code,
                        "body": response_text,
                        "headers": dict(resp.headers),
                    },
                )
        except httpx.TimeoutException:
            return ToolResult(success=False, error=f"请求超时 ({timeout}秒)")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
