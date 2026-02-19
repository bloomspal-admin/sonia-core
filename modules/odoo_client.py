"""
SonIA Core - Odoo Client Module
Connects to Odoo via XML-RPC to read WhatsApp BBDD spreadsheet.
"""

import json
import base64
import logging
import zlib
from typing import Dict, List, Optional, Any
from xmlrpc import client as xmlrpc_client

logger = logging.getLogger(__name__)


class OdooClient:
    def __init__(self, url: str, db: str, username: str, password: str):
        self.url = url
        self.db = db
        self.username = username
        self.password = password
        self.uid = None
        self.common = None
        self.models = None

    def authenticate(self) -> bool:
        try:
            self.common = xmlrpc_client.ServerProxy(f"{self.url}/xmlrpc/2/common")
            self.uid = self.common.authenticate(self.db, self.username, self.password, {})
            if self.uid:
                self.models = xmlrpc_client.ServerProxy(f"{self.url}/xmlrpc/2/object")
                logger.info(f"Odoo auth OK - uid={self.uid}")
                return True
            logger.error("Odoo auth failed - no uid")
            return False
        except Exception as e:
            logger.error(f"Odoo auth error: {e}")
            return False

    def _execute(self, model: str, method: str, *args, **kwargs):
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, method, *args, **kwargs
        )

    # ==================================================================
    # SPREADSHEET ACCESS - Multiple approaches for Odoo Documents
    # ==================================================================

    def test_spreadsheet_access(self, doc_id: int) -> Dict:
        """Diagnostic: try multiple approaches to read spreadsheet data."""
        results = {}

        # Approach a1: spreadsheet_data field (template/structure only)
        try:
            records = self._execute(
                "documents.document", "read",
                [[doc_id]],
                {"fields": ["name", "handler", "spreadsheet_data"]}
            )
            if records:
                r = records[0]
                sd = r.get("spreadsheet_data", "")
                results["a1_spreadsheet_data"] = {
                    "status": "ok",
                    "name": r.get("name"),
                    "handler": r.get("handler"),
                    "data_len": len(sd) if sd else 0,
                    "preview": sd[:200] if sd else None,
                }
        except Exception as e:
            results["a1_spreadsheet_data"] = {"status": "error", "error": str(e)}

        # Approach a2: spreadsheet_snapshot (full state with cell data)
        try:
            records = self._execute(
                "documents.document", "read",
                [[doc_id]],
                {"fields": ["spreadsheet_snapshot"]}
            )
            if records:
                snapshot = records[0].get("spreadsheet_snapshot")
                if snapshot:
                    # snapshot is base64 encoded, possibly gzipped
                    raw = base64.b64decode(snapshot)
                    try:
                        decompressed = zlib.decompress(raw, 15 + 32)
                        text = decompressed.decode("utf-8")
                    except Exception:
                        text = raw.decode("utf-8", errors="replace")
                    parsed = json.loads(text)
                    sheet_names = [s.get("name") for s in parsed.get("sheets", [])]
                    cell_counts = {}
                    for s in parsed.get("sheets", []):
                        cell_counts[s.get("name", "?")] = len(s.get("cells", {}))
                    results["a2_snapshot"] = {
                        "status": "ok",
                        "data_len": len(text),
                        "sheets": sheet_names,
                        "cell_counts": cell_counts,
                        "preview": text[:200],
                    }
                else:
                    results["a2_snapshot"] = {"status": "empty", "note": "snapshot field is empty"}
        except Exception as e:
            results["a2_snapshot"] = {"status": "error", "error": str(e)[:300]}

        # Approach a3: spreadsheet_binary_data
        try:
            records = self._execute(
                "documents.document", "read",
                [[doc_id]],
                {"fields": ["spreadsheet_binary_data"]}
            )
            if records:
                bin_data = records[0].get("spreadsheet_binary_data")
                if bin_data:
                    raw = base64.b64decode(bin_data)
                    try:
                        decompressed = zlib.decompress(raw, 15 + 32)
                        text = decompressed.decode("utf-8")
                    except Exception:
                        text = raw.decode("utf-8", errors="replace")
                    try:
                        parsed = json.loads(text)
                        sheet_names = [s.get("name") for s in parsed.get("sheets", [])]
                        cell_counts = {}
                        for s in parsed.get("sheets", []):
                            cell_counts[s.get("name", "?")] = len(s.get("cells", {}))
                        results["a3_binary_data"] = {
                            "status": "ok",
                            "data_len": len(text),
                            "sheets": sheet_names,
                            "cell_counts": cell_counts,
                        }
                    except json.JSONDecodeError:
                        results["a3_binary_data"] = {
                            "status": "ok_raw",
                            "data_len": len(text),
                            "preview": text[:200],
                        }
                else:
                    results["a3_binary_data"] = {"status": "empty"}
        except Exception as e:
            results["a3_binary_data"] = {"status": "error", "error": str(e)[:300]}

        # Approach a4: fields_get to list all relevant fields
        try:
            all_fields = self._execute(
                "documents.document", "fields_get",
                [],
                {"attributes": ["string", "type"]}
            )
            relevant = {k: v for k, v in all_fields.items()
                        if "spread" in k.lower() or "data" in k.lower()
                        or k in ("datas", "raw")}
            results["fields"] = {
                "status": "ok",
                "total": len(all_fields),
                "relevant": relevant,
            }
        except Exception as e:
            results["fields"] = {"status": "error", "error": str(e)[:200]}

        return results

    def read_spreadsheet(self, doc_id: int) -> Optional[Dict]:
        """Read Odoo Documents spreadsheet, trying all approaches and using the one with most data."""
        best_result = None
        best_cells = 0
        best_source = ""

        def _count_cells(parsed):
            return sum(len(s.get("cells", {})) for s in parsed.get("sheets", []))

        def _decode_data(raw_b64):
            raw = base64.b64decode(raw_b64)
            try:
                text = zlib.decompress(raw, 15 + 32).decode("utf-8")
            except Exception:
                text = raw.decode("utf-8", errors="replace")
            return json.loads(text)

        # Approach 1: spreadsheet_snapshot
        try:
            records = self._execute(
                "documents.document", "read", [[doc_id]],
                {"fields": ["spreadsheet_snapshot"]}
            )
            if records:
                snapshot = records[0].get("spreadsheet_snapshot")
                if snapshot:
                    parsed = _decode_data(snapshot)
                    cells = _count_cells(parsed)
                    logger.info(f"Snapshot: {cells} cells across {len(parsed.get('sheets', []))} sheets")
                    if cells > best_cells:
                        best_result, best_cells, best_source = parsed, cells, "snapshot"
        except Exception as e:
            logger.warning(f"Snapshot approach failed: {e}")

        # Approach 2: spreadsheet_binary_data
        try:
            records = self._execute(
                "documents.document", "read", [[doc_id]],
                {"fields": ["spreadsheet_binary_data"]}
            )
            if records:
                bin_data = records[0].get("spreadsheet_binary_data")
                if bin_data:
                    parsed = _decode_data(bin_data)
                    cells = _count_cells(parsed)
                    logger.info(f"Binary data: {cells} cells across {len(parsed.get('sheets', []))} sheets")
                    if cells > best_cells:
                        best_result, best_cells, best_source = parsed, cells, "binary_data"
        except Exception as e:
            logger.warning(f"Binary data approach failed: {e}")

        # Approach 3: spreadsheet_data
        try:
            records = self._execute(
                "documents.document", "read", [[doc_id]],
                {"fields": ["spreadsheet_data"]}
            )
            if records:
                sd = records[0].get("spreadsheet_data")
                if sd:
                    parsed = json.loads(sd)
                    cells = _count_cells(parsed)
                    logger.info(f"Spreadsheet data: {cells} cells across {len(parsed.get('sheets', []))} sheets")
                    if cells > best_cells:
                        best_result, best_cells, best_source = parsed, cells, "spreadsheet_data"
        except Exception as e:
            logger.warning(f"spreadsheet_data approach failed: {e}")

        if best_result:
            logger.info(f"Using {best_source} with {best_cells} total cells for spreadsheet {doc_id}")
            # Apply any pending revisions on top of the snapshot
            best_result = self._apply_revisions(doc_id, best_result)
            return best_result

        logger.error(f"All approaches failed for spreadsheet {doc_id}")
        return None

    def get_whatsapp_bbdd(self, doc_id: int) -> Dict:
        """Read WhatsApp BBDD spreadsheet and parse both sheets."""
        data = self.read_spreadsheet(doc_id)
        if not data:
            return {"tenant_mapping": {}, "contacts": [], "error": "Could not read spreadsheet"}

        sheets = data.get("sheets", [])
        tenant_mapping = {}
        contacts = []

        for sheet in sheets:
            name = sheet.get("name", "").strip().lower()
            cells = sheet.get("cells", {})

            if "hoja2" in name or "hoja 2" in name:
                tenant_mapping = self._parse_tenant_mapping(cells)
            elif "hoja1" in name or "hoja 1" in name:
                contacts = self._parse_contacts(cells)

        return {
            "tenant_mapping": tenant_mapping,
            "contacts": contacts,
            "sheets_found": [s.get("name") for s in sheets],
        }

    @staticmethod
    def _cell_value(cells: Dict, key: str) -> str:
        """Extract cell value - handles both dict and string cell formats."""
        raw = cells.get(key, "")
        if isinstance(raw, dict):
            return str(raw.get("content", raw.get("value", ""))).strip()
        return str(raw).strip() if raw else ""

    def _parse_tenant_mapping(self, cells: Dict) -> Dict[int, str]:
        """Parse Hoja 2 cells: tenant_number (col A) -> client_name (col B)."""
        mapping = {}
        row = 2  # Skip header row
        while row < 100:
            tenant_val = self._cell_value(cells, f"A{row}")
            client_val = self._cell_value(cells, f"B{row}")

            # Skip empty rows but keep scanning
            if not tenant_val and not client_val:
                row += 1
                continue

            try:
                tenant_num = int(tenant_val)
                if client_val:
                    mapping[tenant_num] = client_val
            except (ValueError, TypeError):
                pass
            row += 1

        logger.info(f"Parsed {len(mapping)} tenant mappings from Hoja 2")
        return mapping

    @staticmethod
    def _col_to_letter(col: int) -> str:
        """Convert 0-indexed column number to letter (0=A, 1=B, ..., 25=Z)."""
        return chr(65 + col)

    def _apply_revisions(self, doc_id: int, data: Dict) -> Dict:
        """Fetch spreadsheet revisions and apply UPDATE_CELL commands on top of snapshot."""
        try:
            revisions = self._execute(
                "spreadsheet.revision", "search_read",
                [[["res_id", "=", doc_id], ["res_model", "=", "documents.document"]]],
                {"fields": ["commands"], "order": "id asc"}
            )
            if not revisions:
                logger.info(f"No revisions found for spreadsheet {doc_id}")
                return data

            logger.info(f"Found {len(revisions)} revisions to apply for spreadsheet {doc_id}")

            # Build sheet_id -> sheet index mapping
            sheet_map = {}
            for idx, sheet in enumerate(data.get("sheets", [])):
                sid = sheet.get("id", "")
                sheet_map[sid] = idx

            applied = 0
            for rev in revisions:
                try:
                    cmds_raw = rev.get("commands", "")
                    if not cmds_raw:
                        continue
                    cmds_data = json.loads(cmds_raw)
                    commands = cmds_data.get("commands", [])
                    for cmd in commands:
                        cmd_type = cmd.get("type", "")
                        if cmd_type == "UPDATE_CELL":
                            sheet_id = cmd.get("sheetId", "")
                            col = cmd.get("col", 0)
                            row = cmd.get("row", 0)
                            content_val = cmd.get("content", "")
                            s_idx = sheet_map.get(sheet_id)
                            if s_idx is None:
                                continue
                            cell_ref = self._col_to_letter(col) + str(row + 1)
                            sheet = data["sheets"][s_idx]
                            if "cells" not in sheet:
                                sheet["cells"] = {}
                            if content_val:
                                sheet["cells"][cell_ref] = {"content": content_val}
                            else:
                                sheet["cells"].pop(cell_ref, None)
                            applied += 1
                        elif cmd_type == "DELETE_CONTENT":
                            sheet_id = cmd.get("sheetId", "")
                            s_idx = sheet_map.get(sheet_id)
                            if s_idx is None:
                                continue
                            target = cmd.get("target", [])
                            for zone in target:
                                for r in range(zone.get("top", 0), zone.get("bottom", 0) + 1):
                                    for c in range(zone.get("left", 0), zone.get("right", 0) + 1):
                                        cell_ref = self._col_to_letter(c) + str(r + 1)
                                        data["sheets"][s_idx].get("cells", {}).pop(cell_ref, None)
                                        applied += 1
                except Exception as e:
                    logger.debug(f"Error applying revision: {e}")
                    continue

            total_cells = sum(len(s.get("cells", {})) for s in data.get("sheets", []))
            logger.info(f"Applied {applied} cell updates from revisions. Total cells now: {total_cells}")
            return data

        except Exception as e:
            logger.warning(f"Could not fetch/apply revisions for spreadsheet {doc_id}: {e}")
            return data

    def _parse_contacts(self, cells: Dict) -> List[Dict]:
        """Parse Hoja 1 cells into contact list."""
        contacts = []
        row = 2  # Skip header
        while row < 200:
            cliente = self._cell_value(cells, f"A{row}")
            nombre = self._cell_value(cells, f"B{row}")
            nickname = self._cell_value(cells, f"C{row}")
            whatsapp = self._cell_value(cells, f"D{row}")
            rol = self._cell_value(cells, f"E{row}")
            clave = self._cell_value(cells, f"F{row}")
            bloqueo = self._cell_value(cells, f"G{row}")
            tenant_num = self._cell_value(cells, f"H{row}")
            email = self._cell_value(cells, f"I{row}")

            # Skip empty rows but keep scanning to the end
            if not cliente and not nombre and not whatsapp:
                row += 1
                continue

            contact = {
                "cliente": cliente,
                "nombre_usuario": nombre,
                "nickname": nickname,
                "whatsapp": self._clean_phone(whatsapp),
                "email": email.strip() if email else "",
                "rol": rol,
                "clave": clave,
                "bloqueo": bloqueo,
                "tenant_number": None,
            }

            if tenant_num:
                try:
                    contact["tenant_number"] = int(tenant_num)
                except (ValueError, TypeError):
                    pass

            contacts.append(contact)
            row += 1

        logger.info(f"Parsed {len(contacts)} contacts from Hoja 1")
        return contacts

    # ==================================================================
    # LEGACY METHODS (kept for backwards compatibility)
    # ==================================================================

    def search_companies(self, limit: int = 50) -> List[Dict]:
        return self._execute(
            "res.partner", "search_read",
            [[["is_company", "=", True]]],
            {"fields": ["id", "name", "email", "phone"], "limit": limit}
        )

    def find_company_by_tenant_number(self, tenant_number: int, field_name: str = "x_studio_tenant") -> Optional[Dict]:
        try:
            results = self._execute(
                "res.partner", "search_read",
                [[[field_name, "=", tenant_number], ["is_company", "=", True]]],
                {"fields": ["id", "name", "email", "phone", field_name], "limit": 1}
            )
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Tenant lookup error: {e}")
            return None

    def find_company_by_name(self, name: str) -> Optional[Dict]:
        try:
            results = self._execute(
                "res.partner", "search_read",
                [[["name", "ilike", name], ["is_company", "=", True]]],
                {"fields": ["id", "name", "email", "phone"], "limit": 5}
            )
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Company name lookup error: {e}")
            return None

    @staticmethod
    def _clean_phone(phone: str) -> str:
        if not phone:
            return ""
        cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
        if cleaned.startswith("+"):
            cleaned = cleaned[1:]
        return cleaned
