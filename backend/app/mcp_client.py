import httpx
import asyncio
from typing import Any, Dict
from app.core.logger import logger

MCP_SERVER_URL = "http://127.0.0.1:8000/mcp"

_client = httpx.AsyncClient(timeout=60.0)

class MCPError(Exception):
    """Custom exception for MCP call failures."""
    def __init__(self, message, code=None):
        self.message = message
        self.code = code
        super().__init__(f"MCP Error {code}: {message}")

async def call_mcp(method: str, params: Dict[str, Any] = None) -> Any:
    """
    Makes a JSON-RPC 2.0 call to the internal MCP server.
    """
    params = params or {}
    mcp_request = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1  
    }
    
    try:
        logger.debug(f"[MCP Client] Calling method '{method}' with params {params.keys()}")
        response = await _client.post(MCP_SERVER_URL, json=mcp_request)
        
        response.raise_for_status()  
        
        mcp_response = response.json()
        
        if "error" in mcp_response and mcp_response["error"]:
            err = mcp_response["error"]
            logger.error(f"[MCP Client] MCP server returned error for method '{method}': {err.get('message')}")
            raise MCPError(message=err.get("message"), code=err.get("code"))
            
        logger.debug(f"[MCP Client] Method '{method}' successful.")
        return mcp_response.get("result")
        
    except httpx.ConnectError as e:
        logger.error(f"[MCP Client] Connection failed. Is server running at {MCP_SERVER_URL}? Error: {e}")
        raise MCPError(message=f"Connection failed to tool server. Is it running?")
    except Exception as e:
        logger.error(f"[MCP Client] Unexpected error calling method '{method}': {e}")
        raise MCPError(message=str(e))

async def shutdown_mcp_client():
    """Closes the persistent httpx client."""
    await _client.aclose()