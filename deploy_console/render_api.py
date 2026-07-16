"""Render.com REST API client for Deploy Console."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

API_BASE = "https://api.render.com/v1"

# Map Render region codes to SSH hostnames
_SSH_REGION = {
    "oregon": "oregon",
    "ohio": "ohio",
    "virginia": "virginia",
    "frankfurt": "frankfurt",
    "singapore": "singapore",
    "sydney": "sydney",
    "tokyo": "tokyo",
    "mumbai": "mumbai",
}


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
            # support multi resource= for logs
            parts = []
            for k, v in query.items():
                if v is None:
                    continue
                if isinstance(v, (list, tuple)):
                    for item in v:
                        parts.append(
                            f"{urllib.parse.quote(str(k))}={urllib.parse.quote(str(item))}"
                        )
                else:
                    parts.append(
                        f"{urllib.parse.quote(str(k))}={urllib.parse.quote(str(v))}"
                    )
            if parts:
                url += "?" + "&".join(parts)
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
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RenderAPIError(
                f"Render API {method} {path} → {e.code}: {err_body[:500]}",
                status=e.code,
                body=err_body,
            ) from e
        except urllib.error.URLError as e:
            raise RenderAPIError(f"Network error: {e}") from e

    def list_owners(self) -> list[dict]:
        raw = self._request("GET", "/owners")
        out = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and "owner" in item:
                    out.append(item["owner"])
                elif isinstance(item, dict):
                    out.append(item)
        return out

    def list_services(self, limit: int = 50) -> list[dict]:
        raw = self._request("GET", "/services", query={"limit": str(limit)})
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
        """
        Deploy latest commit from the linked repo branch.
        clear_cache=True → clear build cache (full rebuild).
        """
        body: dict[str, Any] = {
            "clearCache": "clear" if clear_cache else "do_not_clear"
        }
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

    def get_logs(
        self,
        service_id: str,
        *,
        owner_id: Optional[str] = None,
        limit: int = 100,
        log_type: Optional[str] = None,
        text: Optional[str] = None,
    ) -> dict:
        """
        Fetch recent logs for a service.
        log_type: app | request | build (optional filter)
        """
        if not owner_id:
            svc = self.get_service(service_id)
            owner_id = svc.get("ownerId")
        if not owner_id:
            owners = self.list_owners()
            if owners:
                owner_id = owners[0].get("id")
        if not owner_id:
            raise RenderAPIError("Could not resolve ownerId for logs")

        query: dict[str, Any] = {
            "ownerId": owner_id,
            "resource": [service_id],
            "limit": str(min(100, max(1, int(limit)))),
            "direction": "backward",
        }
        if log_type:
            query["type"] = [log_type]
        if text:
            query["text"] = [text]

        raw = self._request("GET", "/logs", query=query)
        if not isinstance(raw, dict):
            return {"logs": [], "hasMore": False, "raw": raw}
        logs = raw.get("logs") or []
        # normalize lines for UI
        lines = []
        for entry in logs:
            if not isinstance(entry, dict):
                continue
            ts = entry.get("timestamp") or ""
            msg = entry.get("message") or ""
            # strip ANSI
            msg = _strip_ansi(str(msg))
            labels = entry.get("labels") or []
            typ = ""
            for lab in labels:
                if isinstance(lab, dict) and lab.get("name") == "type":
                    typ = str(lab.get("value") or "")
            lines.append({"timestamp": ts, "type": typ, "message": msg})
        return {
            "logs": lines,
            "hasMore": bool(raw.get("hasMore")),
            "nextStartTime": raw.get("nextStartTime"),
            "nextEndTime": raw.get("nextEndTime"),
            "ownerId": owner_id,
        }

    def suspend(self, service_id: str) -> Any:
        return self._request("POST", f"/services/{service_id}/suspend")

    def resume(self, service_id: str) -> Any:
        return self._request("POST", f"/services/{service_id}/resume")

    def restart(self, service_id: str) -> Any:
        return self.trigger_deploy(service_id, clear_cache=False)

    def summarize_service(self, svc: dict) -> dict:
        details = svc.get("serviceDetails") or {}
        region = details.get("region") or svc.get("region") or "oregon"
        sid = svc.get("id")
        ssh_host = f"ssh.{_SSH_REGION.get(str(region).lower(), str(region).lower())}.render.com"
        return {
            "id": sid,
            "name": svc.get("name"),
            "type": svc.get("type"),
            "slug": svc.get("slug"),
            "ownerId": svc.get("ownerId"),
            "region": region,
            "url": details.get("url") or svc.get("url"),
            "branch": details.get("branch") or svc.get("branch"),
            "repo": svc.get("repo"),
            "autoDeploy": svc.get("autoDeploy"),
            "suspended": svc.get("suspended"),
            "updatedAt": svc.get("updatedAt"),
            "dashboard": svc.get("dashboardUrl")
            or (f"https://dashboard.render.com/web/{sid}" if sid else None),
            "ssh_user": sid,
            "ssh_host": ssh_host,
            "ssh_command": f"ssh {sid}@{ssh_host}" if sid else None,
        }


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
