"""
SonIA Core — Odoo Sale Order Creator
Creates draft sale orders in Odoo via JSON-RPC for each dropshipper.
"""

import logging
import json
from typing import Dict, List, Any, Optional

import httpx

logger = logging.getLogger(__name__)


class OdooSaleOrderCreator:
    """Create sale orders in Odoo via JSON-RPC."""

    def __init__(self, url: str, db: str, username: str, password: str):
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self.uid: Optional[int] = None
        self._rpc_id = 0

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        """Authenticate with Odoo and get UID."""
        try:
            result = self._jsonrpc(
                f"{self.url}/jsonrpc",
                service="common",
                method="login",
                args=[self.db, self.username, self.password],
            )
            if result and isinstance(result, int):
                self.uid = result
                logger.info(f"Odoo JSON-RPC auth successful (UID: {self.uid})")
                return True
            else:
                logger.error(f"Odoo JSON-RPC auth failed: {result}")
                return False
        except Exception as e:
            logger.error(f"Odoo JSON-RPC auth error: {e}")
            return False

    # ------------------------------------------------------------------
    # Sale Order Creation
    # ------------------------------------------------------------------

    def create_sale_order(
        self,
        partner_id: int,
        order_lines: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Create a draft sale order in Odoo.

        Args:
            partner_id: Odoo res.partner ID
            order_lines: List of dicts with product_id, product_uom_qty, price_unit

        Returns:
            {"order_id": int, "order_name": str, "state": str, "amount_total": float}
        """
        if not self.uid:
            raise RuntimeError("Not authenticated with Odoo")

        # Build Odoo order line tuples: (0, 0, vals)
        odoo_lines = []
        for line in order_lines:
            line_vals = {
                "product_id": line["product_id"],
                "product_uom_qty": line["product_uom_qty"],
                "price_unit": line["price_unit"],
                "tax_ids": [(5, 0, 0)],  # Clear all taxes
            }
            if line.get("name"):
                line_vals["name"] = line["name"]
            odoo_lines.append((0, 0, line_vals))

        # Create the sale order
        # Warehouse orders are always created by Jenifer Parra (UID 10)
        order_vals = {
            "partner_id": partner_id,
            "order_line": odoo_lines,
            "user_id": 10,  # jeniferparra@bloomspal.com
        }

        order_id = self._call("sale.order", "create", [order_vals])

        if not order_id:
            raise RuntimeError(f"Failed to create sale order for partner {partner_id}")

        # Read back the created order
        order_data = self._call(
            "sale.order", "read",
            [order_id],
            {"fields": ["name", "state", "amount_total"]},
        )

        if order_data and isinstance(order_data, list) and order_data:
            order = order_data[0]
            result = {
                "order_id": order_id,
                "order_name": order.get("name", ""),
                "state": order.get("state", "draft"),
                "amount_total": order.get("amount_total", 0.0),
            }
            logger.info(
                f"Created sale order {result['order_name']} (ID: {order_id}) "
                f"for partner {partner_id}, total: ${result['amount_total']}"
            )
            return result

        return {"order_id": order_id, "order_name": "", "state": "draft", "amount_total": 0.0}

    # ------------------------------------------------------------------
    # JSON-RPC internals
    # ------------------------------------------------------------------

    def _call(self, model: str, method: str, args: list, kwargs: dict = None):
        """Execute an Odoo model method via JSON-RPC."""
        if not self.uid:
            raise RuntimeError("Not authenticated")

        call_args = [self.db, self.uid, self.password, model, method] + [args]
        if kwargs:
            call_args.append(kwargs)

        return self._jsonrpc(
            f"{self.url}/jsonrpc",
            service="object",
            method="execute_kw",
            args=call_args,
        )

    def _jsonrpc(self, url: str, service: str, method: str, args: list) -> Any:
        """Make a JSON-RPC 2.0 call to Odoo."""
        self._rpc_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._rpc_id,
            "method": "call",
            "params": {
                "service": service,
                "method": method,
                "args": args,
            },
        }

        response = httpx.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60.0,
        )
        response.raise_for_status()

        data = response.json()
        if data.get("error"):
            error_msg = data["error"].get("data", {}).get("message", str(data["error"]))
            raise RuntimeError(f"Odoo RPC error: {error_msg}")

        return data.get("result")
