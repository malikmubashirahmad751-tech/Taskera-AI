import httpx
from typing import Any, Dict

from app.core.logger import logger

MCP_SERVER_URL = "http://127.0.0.1:8000/mcp"

_client = httpx.AsyncClient(
    timeout=httpx.Timeout(60.0, connect=10.0),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
)

class MCPError(Exception):
    """Custom exception for MCP failures"""
    def __init__(self, message: str, code: int = None):
        self.message = message
        self.code = code
        super().__init__(f"MCP Error [{code}]: {message}")

async def call_mcp(method: str, params: Dict[str, Any] = None) -> Any:
    """
    Make a JSON-RPC 2.0 call to the MCP server
    
    Args:
        method: The MCP method name
        params: Method parameters
        
    Returns:
        Result from the MCP server
        
    Raises:
        MCPError: If the call fails
    """
    params = params or {}
    
    mcp_request = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1
    }
    
    try:
        logger.debug(f"[MCP] Calling method='{method}'")
        
        response = await _client.post(MCP_SERVER_URL, json=mcp_request)
        response.raise_for_status()
        
        mcp_response = response.json()
        
        if "error" in mcp_response and mcp_response["error"]:
            error = mcp_response["error"]
            error_msg = error.get("message", "Unknown error")
            error_code = error.get("code", -1)
            
            logger.error(f"[MCP] Server error for '{method}': {error_msg}")
            raise MCPError(message=error_msg, code=error_code)
        
        logger.debug(f"[MCP] Method '{method}' completed successfully")
        return mcp_response.get("result")
        
    except httpx.ConnectError as e:
        logger.error(f"[MCP] Connection failed: {e}")
        raise MCPError(
            message="Could not connect to tool server. Is it running?",
            code=-32000
        )
        
    except httpx.HTTPStatusError as e:
        logger.error(f"[MCP] HTTP error {e.response.status_code}: {e}")
        raise MCPError(
            message=f"Server returned error: {e.response.status_code}",
            code=-32001
        )
        
    except Exception as e:
        logger.error(f"[MCP] Unexpected error calling '{method}': {e}")
        raise MCPError(message=str(e), code=-32002)

async def shutdown_mcp_client():
    """Close the persistent HTTP client"""
    try:
        await _client.aclose()
        logger.info("[MCP] Client shut down")
    except Exception as e:
        logger.error(f"[MCP] Shutdown error: {e}")