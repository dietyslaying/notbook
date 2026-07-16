"""Render.com REST API client for Deploy Console."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

API_BASE = "https://api.render.com/v1"


class RenderAPIError(Exception):
    def __init__(self, message: str, status: int = 0, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class RenderClient:
    def __init__(self, api_key: str):
        self.api_key = (api_key or "").strip()
        if not self.api_key:
            raise RenderAPIError("RENDER_API_KEY is empty")

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        query: Optional[dict] = None,
    ) -> Any:
        url = API_BASE + path
        if query:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in query.items() if v is not None}
            )
        data = None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "Notbook-Deploy-Console/1.0",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RenderAPIError(
                f"Render API {method} {path} → {e.code}: {err_body[:400]}",
                status=e.code,
                body=err_body,
            ) from e
        except urllib.error.URLError as e:
            raise RenderAPIError(f"Network error: {e}") from e

    def list_services(self, limit: int = 50) -> list[dict]:
        """Return flattened service list."""
        raw = self._request("GET", "/services", query={"limit": str(limit)})
        # API returns [{service: {...}, cursor: ...}, ...] or list of services
        out: list[dict] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and "service" in item:
                    out.append(item["service"])
                elif isinstance(item, dict):
                    out.append(item)
        return out

    def get_service(self, service_id: str) -> dict:
        raw = self._request("GET", f"/services/{service_id}")
        if isinstance(raw, dict) and "service" in raw:
            return raw["service"]
        return raw if isinstance(raw, dict) else {}

    def list_deploys(self, service_id: str, limit: int = 10) -> list[dict]:
        raw = self._request(
            "GET", f"/services/{service_id}/deploys", query={"limit": str(limit)}
        )
        out: list[dict] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and "deploy" in item:
                    out.append(item["deploy"])
                elif isinstance(item, dict):
                    out.append(item)
        return out

    def trigger_deploy(
        self,
        service_id: str,
        *,
        clear_cache: bool = False,
        commit_id: Optional[str] = None,
    ) -> dict:
        body: dict[str, Any] = {"clearCache": "clear" if clear_cache else "do_not_clear"}
        if commit_id:
            body["commitId"] = commit_id
        raw = self._request("POST", f"/services/{service_id}/deploys", body=body)
        if isinstance(raw, dict) and "deploy" in raw:
            return raw["deploy"]
        return raw if isinstance(raw, dict) else {"raw": raw}

    def list_env_vars(self, service_id: str) -> list[dict]:
        raw = self._request("GET", f"/services/{service_id}/env-vars")
        out: list[dict] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and "envVar" in item:
                    out.append(item["envVar"])
                elif isinstance(item, dict):
                    out.append(item)
        return out

    def put_env_vars(self, service_id: str, env_vars: list[dict[str, str]]) -> list[dict]:
        """
        Replace env vars. Each item: {key, value}
        Warning: variables omitted are removed by Render API.
        """
        body = [{"key": e["key"], "value": e["value"]} for e in env_vars if e.get("key")]
        raw = self._request("PUT", f"/services/{service_id}/env-vars", body=body)
        out: list[dict] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and "envVar" in item:
                    out.append(item["envVar"])
                elif isinstance(item, dict):
                    out.append(item)
        return out

    def upsert_env_vars(
        self, service_id: str, updates: dict[str, str]
    ) -> list[dict]:
        """Merge updates into existing env vars (does not drop other keys)."""
        existing = self.list_env_vars(service_id)
        merged: dict[str, str] = {}
        for e in existing:
            k = e.get("key")
            v = e.get("value")
            if k is not None and v is not None:
                merged[str(k)] = str(v)
        for k, v in updates.items():
            if v is None:
                continue
            merged[str(k)] = str(v)
        payload = [{"key": k, "value": v} for k, v in merged.items()]
        return self.put_env_vars(service_id, payload)

    def suspend(self, service_id: str) -> Any:
        return self._request("POST", f"/services/{service_id}/suspend")

    def resume(self, service_id: str) -> Any:
        return self._request("POST", f"/services/{service_id}/resume")

    def restart(self, service_id: str) -> Any:
        # Restart = deploy of current commit without cache clear
        return self.trigger_deploy(service_id, clear_cache=False)

    def summarize_service(self, svc: dict) -> dict:
        """Compact view for the UI."""
        return {
            "id": svc.get("id"),
            "name": svc.get("name"),
            "type": svc.get("type"),
            "slug": svc.get("slug"),
            "region": (svc.get("serviceDetails") or {}).get("region")
            or svc.get("region"),
            "url": (svc.get("serviceDetails") or {}).get("url") or svc.get("url"),
            "branch": (svc.get("serviceDetails") or {}).get("branch")
            or (svc.get("repo") or {}).get("branch")
            if isinstance(svc.get("repo"), dict)
            else (svc.get("serviceDetails") or {}).get("branch"),
            "repo": svc.get("repo"),
            "autoDeploy": svc.get("autoDeploy"),
            "suspended": svc.get("suspended"),
            "updatedAt": svc.get("updatedAt"),
            "dashboard": f"https://dashboard.render.com/web/{svc.get('id')}"
            if svc.get("id")
            else None,
        }
