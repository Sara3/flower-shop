"""
UCP MCP Server (HTTP/SSE Transport)

Connects to real UCP merchants and exposes them as MCP tools.
Default: Pudding Heroes sandbox (puddingheroes.com)

Run:
  python mcp_server.py
  
Connect via: http://localhost:8000/sse
"""

import json
import httpx
import os
from typing import Any

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse


# ============ CONFIG ============
# Default to the Pudding Heroes sandbox - a real live UCP merchant
UCP_BASE_URL = os.environ.get("UCP_BASE_URL", "https://puddingheroes.com")


# ============ UCP REST CLIENT ============
class UCPClient:
    """Connects to real UCP merchants"""
    
    def __init__(self, base_url: str = UCP_BASE_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def discover(self) -> dict:
        """GET /.well-known/ucp.json - Discover merchant capabilities"""
        resp = await self.client.get(f"{self.base_url}/.well-known/ucp.json")
        resp.raise_for_status()
        return resp.json()
    
    async def list_products(self, product_type: str = None, max_price: float = None) -> dict:
        """GET /api/ucp/products - List available products"""
        params = {}
        if product_type:
            params["type"] = product_type
        if max_price is not None:
            params["max_price"] = max_price
            
        resp = await self.client.get(
            f"{self.base_url}/api/ucp/products",
            params=params
        )
        resp.raise_for_status()
        return resp.json()
    
    async def get_product(self, product_id: str) -> dict:
        """GET /api/ucp/products/{id} - Get product details"""
        resp = await self.client.get(
            f"{self.base_url}/api/ucp/products/{product_id}"
        )
        resp.raise_for_status()
        return resp.json()
    
    async def checkout(
        self,
        line_items: list[dict],
        buyer: dict = None,
        payment_token: str = "sandbox_test"
    ) -> dict:
        """POST /api/ucp/checkout - Create order"""
        payload = {
            "line_items": line_items,
            "payment_token": payment_token
        }
        if buyer:
            payload["buyer"] = buyer
            
        resp = await self.client.post(
            f"{self.base_url}/api/ucp/checkout",
            json=payload
        )
        resp.raise_for_status()
        return resp.json()
    
    async def get_order(self, order_id: str) -> dict:
        """GET /api/ucp/orders/{id} - Get order details"""
        resp = await self.client.get(
            f"{self.base_url}/api/ucp/orders/{order_id}"
        )
        resp.raise_for_status()
        return resp.json()
    
    async def list_orders(self) -> dict:
        """GET /api/ucp/orders - List all orders"""
        resp = await self.client.get(f"{self.base_url}/api/ucp/orders")
        resp.raise_for_status()
        return resp.json()


ucp = UCPClient()


# ============ MCP SERVER ============
server = Server("ucp-merchant")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="ucp_discover",
            description="Discover merchant capabilities. Returns merchant info, supported services, and payment options.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="ucp_list_products",
            description="List available products from the merchant catalog. Can filter by type and max price.",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_type": {
                        "type": "string",
                        "description": "Filter by type: 'digital', 'physical', 'booking', 'subscription', 'experience'",
                        "enum": ["digital", "physical", "booking", "subscription", "experience"]
                    },
                    "max_price": {
                        "type": "number",
                        "description": "Maximum price filter"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="ucp_get_product",
            description="Get detailed information about a specific product.",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The product ID"
                    }
                },
                "required": ["product_id"]
            }
        ),
        Tool(
            name="ucp_checkout",
            description="Purchase a product. Creates an order and returns fulfillment details (download links, tracking, confirmations).",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "Product ID to purchase"
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Quantity (default: 1)",
                        "default": 1
                    },
                    "buyer_name": {
                        "type": "string",
                        "description": "Buyer's name"
                    },
                    "buyer_email": {
                        "type": "string",
                        "description": "Buyer's email (for digital delivery)"
                    }
                },
                "required": ["product_id"]
            }
        ),
        Tool(
            name="ucp_get_order",
            description="Get details of a completed order by order ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The order ID"
                    }
                },
                "required": ["order_id"]
            }
        ),
        Tool(
            name="ucp_list_orders",
            description="List all orders.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "ucp_discover":
            result = await ucp.discover()
            merchant = result.get("ucp", {}).get("merchant", {})
            
            summary = f"**{merchant.get('name', 'Unknown Merchant')}**\n"
            summary += f"_{merchant.get('description', '')}_\n\n"
            summary += f"Website: {merchant.get('website', 'N/A')}\n"
            summary += f"Sandbox Mode: {result.get('ucp', {}).get('sandbox', False)}\n\n"
            summary += f"**Capabilities:** {', '.join(result.get('ucp', {}).get('capabilities', []))}\n\n"
            summary += f"Full discovery:\n```json\n{json.dumps(result, indent=2)}\n```"
            
            return [TextContent(type="text", text=summary)]
        
        elif name == "ucp_list_products":
            result = await ucp.list_products(
                product_type=arguments.get("product_type"),
                max_price=arguments.get("max_price")
            )
            
            products = result.get("products", [])
            count = result.get("count", len(products))
            
            if not products:
                return [TextContent(type="text", text="No products found matching your criteria.")]
            
            output = f"**{count} Products Available**\n\n"
            
            for p in products:
                price = p.get("price", 0)
                price_str = "FREE" if price == 0 else f"${price:.2f}"
                output += f"**{p.get('name')}** - {price_str}\n"
                output += f"  ID: `{p.get('id')}`\n"
                output += f"  Type: {p.get('type')} | Fulfillment: {p.get('fulfillment')}\n"
                if p.get("description"):
                    output += f"  _{p.get('description')}_\n"
                output += "\n"
            
            return [TextContent(type="text", text=output)]
        
        elif name == "ucp_get_product":
            result = await ucp.get_product(arguments["product_id"])
            return [TextContent(
                type="text",
                text=f"Product Details:\n\n```json\n{json.dumps(result, indent=2)}\n```"
            )]
        
        elif name == "ucp_checkout":
            line_items = [{
                "product_id": arguments["product_id"],
                "quantity": arguments.get("quantity", 1)
            }]
            
            buyer = None
            if arguments.get("buyer_name") or arguments.get("buyer_email"):
                buyer = {}
                if arguments.get("buyer_name"):
                    buyer["name"] = arguments["buyer_name"]
                if arguments.get("buyer_email"):
                    buyer["email"] = arguments["buyer_email"]
            
            result = await ucp.checkout(line_items, buyer)
            
            order_id = result.get("order_id", "N/A")
            status = result.get("status", "unknown")
            
            output = f"🎉 **Order Complete!**\n\n"
            output += f"Order ID: `{order_id}`\n"
            output += f"Status: {status}\n\n"
            
            # Show fulfillment info
            fulfillment = result.get("fulfillment", [])
            if fulfillment:
                output += "**Fulfillment:**\n"
                for f in fulfillment:
                    if f.get("download_url"):
                        output += f"  📥 Download: {UCP_BASE_URL}{f['download_url']}\n"
                    if f.get("tracking_number"):
                        output += f"  📦 Tracking: {f['tracking_number']}\n"
                    if f.get("confirmation_code"):
                        output += f"  ✅ Confirmation: {f['confirmation_code']}\n"
            
            output += f"\nFull response:\n```json\n{json.dumps(result, indent=2)}\n```"
            
            return [TextContent(type="text", text=output)]
        
        elif name == "ucp_get_order":
            result = await ucp.get_order(arguments["order_id"])
            return [TextContent(
                type="text",
                text=f"Order Details:\n\n```json\n{json.dumps(result, indent=2)}\n```"
            )]
        
        elif name == "ucp_list_orders":
            result = await ucp.list_orders()
            return [TextContent(
                type="text",
                text=f"Orders:\n\n```json\n{json.dumps(result, indent=2)}\n```"
            )]
        
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    except httpx.HTTPStatusError as e:
        return [TextContent(
            type="text",
            text=f"❌ API Error: {e.response.status_code}\n\n{e.response.text}"
        )]
    except httpx.ConnectError:
        return [TextContent(
            type="text",
            text=f"❌ Cannot connect to UCP merchant at {UCP_BASE_URL}"
        )]
    except Exception as e:
        return [TextContent(type="text", text=f"❌ Error: {type(e).__name__}: {e}")]


# ============ HTTP/SSE SERVER ============
sse_transport = SseServerTransport("/messages")


async def handle_sse(request):
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await server.run(
            streams[0], streams[1], server.create_initialization_options()
        )


async def handle_messages(request):
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)


async def handle_health(request):
    return JSONResponse({"status": "ok", "server": "ucp-merchant", "backend": UCP_BASE_URL})


async def handle_info(request):
    return JSONResponse({
        "name": "ucp-merchant",
        "description": "MCP Server connecting to real UCP merchants",
        "ucp_backend": UCP_BASE_URL,
        "transport": "HTTP/SSE",
        "sse_endpoint": "/sse",
        "tools": [
            "ucp_discover",
            "ucp_list_products", 
            "ucp_get_product",
            "ucp_checkout",
            "ucp_get_order",
            "ucp_list_orders"
        ]
    })


app = Starlette(
    debug=True,
    routes=[
        Route("/health", handle_health),
        Route("/info", handle_info),
        Route("/sse", handle_sse),
        Route("/messages", handle_messages, methods=["POST"]),
        Route("/messages/", handle_messages, methods=["POST"]),
    ]
)


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8000))
    
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║                  🛒 UCP MCP Server                               ║
║                                                                  ║
║  SSE Endpoint:  http://localhost:{port}/sse                        ║
║  Health:        http://localhost:{port}/health                     ║
║  Info:          http://localhost:{port}/info                       ║
║                                                                  ║
║  UCP Merchant:  {UCP_BASE_URL:<44} ║
║                                                                  ║
║  Tools:                                                          ║
║    • ucp_discover      - Get merchant info & capabilities        ║
║    • ucp_list_products - Browse product catalog                  ║
║    • ucp_get_product   - Get product details                     ║
║    • ucp_checkout      - Purchase a product                      ║
║    • ucp_get_order     - View order details                      ║
║    • ucp_list_orders   - List all orders                         ║
║                                                                  ║
║  Set UCP_BASE_URL env var to connect to a different merchant     ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    uvicorn.run(app, host="0.0.0.0", port=port)
