"""
Conta Azul Backend — Integração com Conta Azul API.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shopman.ordering.protocols import (
    AccountEntry,
    AccountsSummary,
    CashFlowSummary,
    CreateEntryResult,
)

logger = logging.getLogger(__name__)


class ContaAzulTokenManager:
    """
    Gerencia tokens OAuth2 do Conta Azul.

    Armazena access_token e refresh_token.
    Renova automaticamente quando expirado.
    """

    TOKEN_URL = "https://api.contaazul.com/oauth2/token"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self._token_data: dict | None = None

    def get_access_token(self) -> str:
        """Retorna access_token válido. Renova se necessário."""
        token_data = self._load_token()
        if not token_data or self._is_expired(token_data):
            token_data = self._refresh_token(token_data)
            self._save_token(token_data)
        return token_data["access_token"]

    def authorize(self, authorization_code: str) -> dict:
        """Troca authorization code por tokens (primeira vez)."""
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": authorization_code,
            "redirect_uri": self.redirect_uri,
        }
        token_data = self._token_request(payload)
        self._save_token(token_data)
        return token_data

    def _refresh_token(self, token_data: dict | None) -> dict:
        """Renova access_token usando refresh_token."""
        if not token_data or "refresh_token" not in token_data:
            raise RuntimeError(
                "No refresh token available. Run authorize() first."
            )
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": token_data["refresh_token"],
        }
        return self._token_request(payload)

    def _token_request(self, payload: dict) -> dict:
        """Faz request de token para Conta Azul."""
        data = urlencode(payload).encode("utf-8")
        request = Request(
            self.TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _load_token(self) -> dict | None:
        """Carrega tokens do storage."""
        from django.core.cache import cache

        cached = cache.get("contaazul_token")
        if cached:
            return cached
        return self._token_data

    def _save_token(self, token_data: dict) -> None:
        """Salva tokens no storage."""
        from django.core.cache import cache

        self._token_data = token_data
        expires_in = token_data.get("expires_in", 3600)
        cache.set("contaazul_token", token_data, timeout=expires_in - 60)

    def _is_expired(self, token_data: dict) -> bool:
        """Verifica se token expirou (conservador: assume expirado se não cacheable)."""
        from django.core.cache import cache

        return cache.get("contaazul_token") is None


class ContaAzulBackend:
    """
    AccountingBackend para Conta Azul API.

    Configuração:
        SHOPMAN_ACCOUNTING = {
            "backend": "contaazul",
            "client_id": env("CONTAAZUL_CLIENT_ID"),
            "client_secret": env("CONTAAZUL_CLIENT_SECRET"),
            "redirect_uri": env("CONTAAZUL_REDIRECT_URI"),
            "category_map": {
                "insumos": "uuid-cat-insumos",
                "vendas_balcao": "uuid-cat-vendas-balcao",
            },
        }
    """

    BASE_URL = "https://api.contaazul.com/v1"

    def __init__(
        self,
        token_manager: ContaAzulTokenManager,
        category_map: dict[str, str] | None = None,
    ):
        self.token_manager = token_manager
        self.category_map = category_map or {}

    def get_cash_flow(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> CashFlowSummary:
        """Calcula fluxo de caixa combinando sales + bills."""
        sales = self._api_call(
            "GET", "/sales",
            params={
                "emission_start": start_date.isoformat(),
                "emission_end": end_date.isoformat(),
                "status": "COMMITTED",
            },
        )

        bills = self._api_call(
            "GET", "/bills",
            params={
                "due_date_start": start_date.isoformat(),
                "due_date_end": end_date.isoformat(),
                "status": "PAID",
            },
        )

        total_revenue_q = sum(
            int(s.get("total", 0) * 100) for s in sales
        )
        total_expenses_q = sum(
            int(b.get("value", 0) * 100) for b in bills
        )

        return CashFlowSummary(
            period_start=start_date,
            period_end=end_date,
            total_revenue_q=total_revenue_q,
            total_expenses_q=total_expenses_q,
            net_q=total_revenue_q - total_expenses_q,
            balance_q=0,
            revenue_by_category=self._group_by_category(sales, "revenue"),
            expenses_by_category=self._group_by_category(bills, "expense"),
        )

    def get_accounts_summary(
        self,
        *,
        as_of: date | None = None,
    ) -> AccountsSummary:
        """Retorna contas a pagar e receber pendentes."""
        ref_date = as_of or date.today()

        receivables_raw = self._api_call(
            "GET", "/receivables",
            params={"status": "AWAITING"},
        )
        bills_raw = self._api_call(
            "GET", "/bills",
            params={"status": "AWAITING"},
        )

        receivables = [self._to_entry(r, "receivable") for r in receivables_raw]
        payables = [self._to_entry(b, "expense") for b in bills_raw]

        total_receivable_q = sum(e.amount_q for e in receivables)
        total_payable_q = sum(e.amount_q for e in payables)
        overdue_receivable_q = sum(
            e.amount_q for e in receivables
            if e.due_date and e.due_date < ref_date
        )
        overdue_payable_q = sum(
            e.amount_q for e in payables
            if e.due_date and e.due_date < ref_date
        )

        return AccountsSummary(
            total_receivable_q=total_receivable_q,
            total_payable_q=total_payable_q,
            overdue_receivable_q=overdue_receivable_q,
            overdue_payable_q=overdue_payable_q,
            receivables=receivables,
            payables=payables,
        )

    def list_entries(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        type: str | None = None,
        status: str | None = None,
        category: str | None = None,
        reference: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AccountEntry]:
        """Lista lançamentos combinados (vendas + bills + receivables)."""
        entries: list[AccountEntry] = []

        if type in (None, "revenue"):
            params: dict = {}
            if start_date:
                params["emission_start"] = start_date.isoformat()
            if end_date:
                params["emission_end"] = end_date.isoformat()
            sales = self._api_call("GET", "/sales", params=params)
            entries.extend(self._to_entry(s, "revenue") for s in sales)

        if type in (None, "expense"):
            params = {}
            if start_date:
                params["due_date_start"] = start_date.isoformat()
            if end_date:
                params["due_date_end"] = end_date.isoformat()
            if status:
                params["status"] = self._map_status(status)
            bills = self._api_call("GET", "/bills", params=params)
            entries.extend(self._to_entry(b, "expense") for b in bills)

        entries.sort(key=lambda e: e.date, reverse=True)

        return entries[offset:offset + limit]

    def create_payable(
        self,
        *,
        description: str,
        amount_q: int,
        due_date: date,
        category: str,
        supplier_name: str | None = None,
        reference: str | None = None,
        notes: str | None = None,
    ) -> CreateEntryResult:
        """Cria conta a pagar no Conta Azul."""
        category_id = self.category_map.get(category)
        if not category_id:
            return CreateEntryResult(
                success=False,
                error_message=f"Categoria não mapeada: {category}",
            )

        supplier_id = None
        if supplier_name:
            supplier_id = self._resolve_supplier(supplier_name)

        payload: dict = {
            "due_date": due_date.isoformat(),
            "value": amount_q / 100,
            "category_id": category_id,
            "document": reference or "",
            "notes": notes or description,
        }
        if supplier_id:
            payload["supplier_id"] = supplier_id

        try:
            result = self._api_call("POST", "/bills", payload=payload)
            return CreateEntryResult(
                success=True,
                entry_id=result.get("id"),
            )
        except Exception as e:
            return CreateEntryResult(
                success=False,
                error_message=str(e),
            )

    def create_receivable(
        self,
        *,
        description: str,
        amount_q: int,
        due_date: date,
        category: str,
        customer_name: str | None = None,
        reference: str | None = None,
        notes: str | None = None,
    ) -> CreateEntryResult:
        """Cria conta a receber no Conta Azul."""
        category_id = self.category_map.get(category)

        payload: dict = {
            "due_date": due_date.isoformat(),
            "value": amount_q / 100,
            "document": reference or "",
            "notes": notes or description,
        }
        if category_id:
            payload["category_id"] = category_id

        try:
            result = self._api_call("POST", "/receivables", payload=payload)
            return CreateEntryResult(
                success=True,
                entry_id=result.get("id"),
            )
        except Exception as e:
            return CreateEntryResult(
                success=False,
                error_message=str(e),
            )

    def mark_as_paid(
        self,
        *,
        entry_id: str,
        paid_date: date | None = None,
        amount_q: int | None = None,
    ) -> CreateEntryResult:
        """Marca lançamento como pago."""
        payload: dict = {"status": "PAID"}
        if paid_date:
            payload["payment_date"] = paid_date.isoformat()
        if amount_q is not None:
            payload["value"] = amount_q / 100

        try:
            self._api_call("PUT", f"/bills/{entry_id}", payload=payload)
            return CreateEntryResult(success=True, entry_id=entry_id)
        except Exception as e:
            return CreateEntryResult(
                success=False,
                error_message=str(e),
            )

    def _resolve_supplier(self, name: str) -> str | None:
        """Busca supplier_id por nome no Conta Azul."""
        results = self._api_call(
            "GET", "/suppliers",
            params={"search": name},
        )
        if results:
            return results[0].get("id")
        return None

    def _to_entry(self, raw: dict, type: str) -> AccountEntry:
        """Converte resposta da API para AccountEntry."""
        if type == "revenue":
            return AccountEntry(
                entry_id=raw["id"],
                description=f"Venda #{raw.get('number', '')}",
                amount_q=int(raw.get("total", 0) * 100),
                type="revenue",
                category=raw.get("category", {}).get("name", ""),
                date=date.fromisoformat(raw.get("emission", "")[:10]),
                status="paid" if raw.get("status") == "COMMITTED" else "pending",
                reference=str(raw.get("number", "")),
                customer_name=raw.get("customer", {}).get("name"),
            )
        elif type == "receivable":
            return AccountEntry(
                entry_id=raw["id"],
                description=raw.get("notes", raw.get("document", f"Receivable #{raw.get('id', '')}")),
                amount_q=int(raw.get("value", 0) * 100),
                type="revenue",
                category=raw.get("category", {}).get("name", ""),
                date=date.fromisoformat(raw.get("due_date", "")[:10]),
                due_date=(
                    date.fromisoformat(raw["due_date"][:10])
                    if raw.get("due_date") else None
                ),
                status="paid" if raw.get("status") == "PAID" else "pending",
                reference=raw.get("document"),
                customer_name=raw.get("customer", {}).get("name"),
            )
        else:
            return AccountEntry(
                entry_id=raw["id"],
                description=raw.get("notes", raw.get("document", "")),
                amount_q=int(raw.get("value", 0) * 100),
                type="expense",
                category=raw.get("category", {}).get("name", ""),
                date=date.fromisoformat(raw.get("due_date", "")[:10]),
                due_date=(
                    date.fromisoformat(raw["due_date"][:10])
                    if raw.get("due_date") else None
                ),
                paid_date=(
                    date.fromisoformat(raw["payment_date"][:10])
                    if raw.get("payment_date") else None
                ),
                status="paid" if raw.get("status") == "PAID" else "pending",
                reference=raw.get("document"),
                supplier_name=raw.get("supplier", {}).get("name"),
            )

    def _api_call(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        payload: dict | None = None,
    ) -> dict | list:
        """Chamada autenticada para Conta Azul API."""
        token = self.token_manager.get_access_token()
        url = f"{self.BASE_URL}{path}"

        if params:
            url += f"?{urlencode(params)}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        data = json.dumps(payload).encode("utf-8") if payload else None

        request = Request(url, data=data, headers=headers, method=method)

        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def _map_status(self, status: str) -> str:
        """Mapeia status interno -> Conta Azul."""
        return {
            "pending": "AWAITING",
            "paid": "PAID",
            "overdue": "AWAITING",
        }.get(status, status.upper())

    def _group_by_category(
        self,
        items: list[dict],
        type: str,
    ) -> dict[str, int]:
        """Agrupa valores por categoria."""
        groups: dict[str, int] = {}
        for item in items:
            cat = item.get("category", {}).get("name", "Outros")
            value_q = int(
                item.get("total" if type == "revenue" else "value", 0) * 100
            )
            groups[cat] = groups.get(cat, 0) + value_q
        return groups
