"""
Odoo XML-RPC client for creating products and invoices.
Uses XML-RPC because it's the most stable and well-documented Odoo API.
Compatible with Odoo 16, 17, and 18.
"""
import xmlrpc.client
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class OdooClient:
    """
    Handles all Odoo operations via XML-RPC:
    - Product creation (product.product / product.template)
    - Invoice creation (account.move)
    - Partner lookup (res.partner)
    """

    def __init__(self, url: str, db: str, username: str, api_key: str):
        self.url = url
        self.db = db
        self.username = username
        self.api_key = api_key
        self.uid = None
        self.models = None
        self._product_cache: Dict[str, int] = {}  # sku -> product_id
        self._partner_cache: Dict[str, int] = {}   # name -> partner_id

    def connect(self):
        """Authenticate and get uid."""
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        version = common.version()
        logger.info(f"Connected to Odoo {version.get('server_version', 'unknown')}")

        self.uid = common.authenticate(self.db, self.username, self.api_key, {})
        if not self.uid:
            raise ConnectionError("Failed to authenticate with Odoo. Check credentials.")
        logger.info(f"Authenticated as UID={self.uid}")

        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    def _execute(self, model: str, method: str, *args, **kwargs):
        """Execute an Odoo model method."""
        return self.models.execute_kw(
            self.db, self.uid, self.api_key, model, method, *args, **kwargs
        )

    # ─── Partner (Dropshipper/Client) ──────────────────────────

    def find_or_create_partner(self, name: str, email: str = "") -> int:
        """
        Find a partner (dropshipper) by name, or create if not exists.
        Returns the partner ID.
        """
        if name in self._partner_cache:
            return self._partner_cache[name]

        # Search by name
        partner_ids = self._execute(
            "res.partner", "search",
            [[["name", "=", name]]],
        )

        if partner_ids:
            partner_id = partner_ids[0]
            logger.debug(f"Found existing partner: {name} (ID={partner_id})")
        else:
            # Create new partner
            partner_id = self._execute(
                "res.partner", "create",
                [{
                    "name": name,
                    "email": email,
                    "is_company": True,
                    "customer_rank": 1,
                    "supplier_rank": 0,
                    "comment": "Auto-created by SonIA Daily Invoicing",
                }],
            )
            logger.info(f"Created new partner: {name} (ID={partner_id})")

        self._partner_cache[name] = partner_id
        return partner_id

    # ─── Products ──────────────────────────────────────────────

    def find_or_create_product(
        self,
        sku: str,
        name: str,
        cost: float = 0.0,
        weight: float = 0.0,
        hs_code: str = "",
        brand: str = "",
        category_name: str = "",
    ) -> int:
        """
        Find a product by SKU (default_code), or create if not exists.
        Products are created as MTO (Make to Order).
        The brand field stores the client/dropshipper name.
        Returns the product.product ID.
        """
        cache_key = f"{sku}:{brand}"
        if cache_key in self._product_cache:
            return self._product_cache[cache_key]

        # Search by default_code (SKU) - could also filter by brand
        product_ids = self._execute(
            "product.product", "search",
            [[["default_code", "=", sku]]],
        )

        if product_ids:
            product_id = product_ids[0]
            logger.debug(f"Found existing product: {sku} (ID={product_id})")
            # Update brand if needed
            if brand:
                self._execute(
                    "product.product", "write",
                    [[product_id], {"x_brand": brand}],
                )
        else:
            # Prepare product values
            product_vals = {
                "name": name or sku,
                "default_code": sku,
                "type": "consu",  # Consumable for now (change to 'product' if storable needed)
                "standard_price": cost,
                "weight": weight,
                "sale_ok": True,
                "purchase_ok": True,
                "description": f"Auto-created by SonIA - Brand: {brand}",
            }

            # Add HS code if available (for customs/international)
            if hs_code:
                product_vals["hs_code"] = hs_code

            # Try to set brand as custom field
            if brand:
                product_vals["x_brand"] = brand

            try:
                product_id = self._execute(
                    "product.product", "create",
                    [product_vals],
                )
                logger.info(f"Created product: {sku} - {name} (ID={product_id})")
            except Exception as e:
                # If x_brand field doesn't exist, retry without it
                if "x_brand" in str(e):
                    logger.warning(
                        "x_brand field not found in Odoo. Creating product without brand. "
                        "Consider adding a custom field 'x_brand' to product.product."
                    )
                    product_vals.pop("x_brand", None)
                    product_vals["description"] = f"Brand: {brand} | {product_vals.get('description', '')}"
                    product_id = self._execute(
                        "product.product", "create",
                        [product_vals],
                    )
                    logger.info(f"Created product (no brand field): {sku} (ID={product_id})")
                else:
                    raise

        self._product_cache[cache_key] = product_id
        return product_id

    def find_or_create_logistics_product(self) -> Dict[str, int]:
        """
        Ensure the logistics service products exist in Odoo:
        - 'LOGISTICS-WEIGHT': Costo logístico por peso (per kg)
        - 'LOGISTICS-ADDRESS': Address fee (per order)
        Returns dict with product IDs.
        """
        products = {}

        for sku, name, price in [
            ("LOGISTICS-WEIGHT-KG", "Costo Logístico por Peso (por Kg)", 6.5),
            ("LOGISTICS-ADDRESS-FEE", "Address Fee (por Orden)", 8.0),
        ]:
            product_ids = self._execute(
                "product.product", "search",
                [[["default_code", "=", sku]]],
            )
            if product_ids:
                products[sku] = product_ids[0]
            else:
                product_id = self._execute(
                    "product.product", "create",
                    [{
                        "name": name,
                        "default_code": sku,
                        "type": "service",
                        "list_price": price,
                        "standard_price": price,
                        "sale_ok": True,
                        "purchase_ok": False,
                        "description": "Producto de servicio logístico - SonIA",
                    }],
                )
                products[sku] = product_id
                logger.info(f"Created logistics product: {sku} (ID={product_id})")

        return products

    # ─── Invoices ──────────────────────────────────────────────

    def create_invoice(
        self,
        partner_id: int,
        invoice_lines: List[Dict[str, Any]],
        reference: str = "",
        narration: str = "",
    ) -> Dict[str, Any]:
        """
        Create a customer invoice (account.move) in Odoo.

        Args:
            partner_id: Odoo partner ID (the dropshipper/client)
            invoice_lines: List of dicts with line items
            reference: Invoice reference text
            narration: Internal notes

        Returns:
            Dict with 'id' and 'name' of the created invoice
        """
        # Build invoice line commands (Odoo one2many format: (0, 0, vals))
        line_commands = []
        for line in invoice_lines:
            line_vals = {
                "product_id": line["product_id"],
                "name": line.get("description", ""),
                "quantity": line.get("quantity", 1),
                "price_unit": line.get("price_unit", 0),
            }
            # Add account if specified
            if line.get("account_id"):
                line_vals["account_id"] = line["account_id"]

            line_commands.append((0, 0, line_vals))

        invoice_vals = {
            "move_type": "out_invoice",  # Customer Invoice
            "partner_id": partner_id,
            "invoice_line_ids": line_commands,
            "ref": reference,
            "narration": narration,
        }

        invoice_id = self._execute("account.move", "create", [invoice_vals])

        # Get the invoice name/number
        invoice_data = self._execute(
            "account.move", "read",
            [[invoice_id], ["name", "amount_total", "state"]],
        )

        invoice_name = invoice_data[0]["name"] if invoice_data else f"INV-{invoice_id}"
        amount_total = invoice_data[0]["amount_total"] if invoice_data else 0

        logger.info(
            f"Created invoice {invoice_name} (ID={invoice_id}) "
            f"for partner {partner_id}, total=${amount_total:.2f}"
        )

        return {
            "id": invoice_id,
            "name": invoice_name,
            "amount_total": amount_total,
            "state": invoice_data[0].get("state", "draft") if invoice_data else "draft",
        }

    def get_default_income_account(self) -> Optional[int]:
        """Get the default income account for invoice lines."""
        accounts = self._execute(
            "account.account", "search",
            [[["account_type", "=", "income"]]],
            {"limit": 1},
        )
        return accounts[0] if accounts else None
