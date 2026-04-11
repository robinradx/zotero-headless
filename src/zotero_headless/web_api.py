from __future__ import annotations

import mimetypes
import json
import hashlib
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .config import Settings
from .utils import parse_library_id


class ZoteroApiError(RuntimeError):
    def __init__(self, status: int, message: str, body: str | None = None):
        self.status = status
        self.body = body
        super().__init__(f"Zotero API error {status}: {message}")


class ZoteroWebClient:
    def __init__(self, settings: Settings):
        if not settings.api_key:
            raise ValueError("Zotero API key is required for web sync")
        self.settings = settings

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Zotero-API-Key": self.settings.api_key or "",
            "Zotero-API-Version": "3",
            "User-Agent": "zotero-headless/0.1",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _sanitize_collection_payload(self, collection_data: dict[str, Any]) -> dict[str, Any]:
        allowed = {"key", "version", "name", "parentCollection"}
        payload = {key: value for key, value in dict(collection_data).items() if key in allowed}
        if payload.get("parentCollection") is None:
            payload.pop("parentCollection", None)
        return payload

    def _sanitize_item_payload(self, item_data: dict[str, Any]) -> dict[str, Any]:
        payload = dict(item_data)
        item_type = payload.get("itemType")
        parent_item = payload.get("parentItem")
        parent_item_key = payload.get("parentItemKey")
        if parent_item is None and isinstance(parent_item_key, str) and parent_item_key:
            payload["parentItem"] = parent_item_key
        if payload.get("parentItem") is None:
            payload.pop("parentItem", None)
        if item_type == "annotation":
            payload.pop("title", None)
        internal_only = {
            "fields",
            "notes",
            "attachments",
            "citationAliases",
            "annotationTypeID",
            "sourcePath",
            "headlessFilePath",
            "headlessFileDir",
            "headlessFileMd5",
            "headlessFileETag",
            "fulltext",
            "parentItemKey",
            "parentCollectionKey",
        }
        for key in internal_only:
            payload.pop(key, None)
        if not payload.get("citationKey"):
            payload.pop("citationKey", None)
        return payload

    def _payload_rejects_native_citation_key(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        failed = payload.get("failed") or {}
        for failure in failed.values():
            message = str((failure or {}).get("message") or "").lower()
            if "citationkey" in message or "citation key" in message:
                return True
        return False

    def _error_rejects_native_citation_key(self, exc: ZoteroApiError) -> bool:
        if exc.status != 400:
            return False
        text = f"{exc}\n{exc.body or ''}".lower()
        return "citationkey" in text or "citation key" in text

    def _require_successful_create(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected Zotero create response: {payload!r}")
        failed = (payload.get("failed") or {})
        if failed:
            first = next(iter(failed.values()))
            code = first.get("code", "unknown")
            message = first.get("message", "unknown create failure")
            raise RuntimeError(f"Zotero create failed {code}: {message}")
        successful = (payload.get("successful") or {})
        if not successful:
            raise RuntimeError(f"Zotero create response had no successful objects: {payload!r}")

    def _encode_form(self, fields: dict[str, Any]) -> bytes:
        return urllib.parse.urlencode(
            [(key, value) for key, value in fields.items() if value is not None],
            doseq=True,
        ).encode("utf-8")

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: Any | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> tuple[int, dict[str, str], Any]:
        url = self.settings.api_base.rstrip("/") + path
        if query:
            encoded = urllib.parse.urlencode(
                [(key, value) for key, value in query.items() if value is not None],
                doseq=True,
            )
            url = f"{url}?{encoded}"

        body = None
        request_headers = self._headers(headers)
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url=url, data=body, method=method, headers=request_headers)
        try:
            with urllib.request.urlopen(request) as response:
                status = response.status
                response_headers = dict(response.headers.items())
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # type: ignore[name-defined]
            text = exc.read().decode("utf-8")
            if exc.code not in expected:
                raise ZoteroApiError(exc.code, exc.reason, text) from exc
            status = exc.code
            response_headers = dict(exc.headers.items())
        except urllib.error.URLError as exc:  # type: ignore[name-defined]
            raise RuntimeError(f"Failed to connect to Zotero API: {exc}") from exc

        if status not in expected:
            raise ZoteroApiError(status, "Unexpected status", text)

        payload: Any
        if not text:
            payload = None
        else:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = text
        return status, response_headers, payload

    def _upload_to_url(
        self,
        url: str,
        *,
        content_type: str,
        body: bytes,
        expected: tuple[int, ...] = (201,),
    ) -> tuple[int, dict[str, str], Any]:
        request = urllib.request.Request(
            url=url,
            data=body,
            method="POST",
            headers={
                "Content-Type": content_type,
                "User-Agent": "zotero-headless/0.1",
            },
        )
        try:
            with urllib.request.urlopen(request) as response:
                status = response.status
                response_headers = dict(response.headers.items())
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # type: ignore[name-defined]
            text = exc.read().decode("utf-8")
            if exc.code not in expected:
                raise ZoteroApiError(exc.code, exc.reason, text) from exc
            status = exc.code
            response_headers = dict(exc.headers.items())
        except urllib.error.URLError as exc:  # type: ignore[name-defined]
            raise RuntimeError(f"Failed to connect to upload URL: {exc}") from exc

        if status not in expected:
            raise ZoteroApiError(status, "Unexpected upload status", text)
        return status, response_headers, text if text else None

    def library_path(self, library_id: str) -> str:
        library_type, remote_id = parse_library_id(library_id)
        if library_type in {"local", "headless"}:
            raise ValueError("Local libraries do not have a Zotero Web API path")
        base = "users" if library_type == "user" else "groups"
        return f"/{base}/{remote_id}"

    def get_current_key(self) -> dict[str, Any]:
        _, _, payload = self._request("GET", "/keys/current")
        return payload

    def get_group_versions(self, user_id: int) -> tuple[dict[str, int], int]:
        _, headers, payload = self._request("GET", f"/users/{user_id}/groups", query={"format": "versions"})
        last_version = int(headers.get("Last-Modified-Version", "0"))
        return {str(k): int(v) for k, v in (payload or {}).items()}, last_version

    def get_group(self, group_id: int | str) -> tuple[dict[str, Any], int]:
        _, headers, payload = self._request("GET", f"/groups/{group_id}")
        return payload, int(headers.get("Last-Modified-Version", "0"))

    def get_versions(self, library_id: str, kind: str, *, since: int = 0) -> tuple[dict[str, int], int]:
        path = f"{self.library_path(library_id)}/{kind}"
        query: dict[str, Any] = {"format": "versions"}
        if since:
            query["since"] = since
        if kind == "items":
            query["includeTrashed"] = 1
        _, headers, payload = self._request("GET", path, query=query)
        return {str(k): int(v) for k, v in (payload or {}).items()}, int(headers.get("Last-Modified-Version", "0"))

    def get_objects_by_keys(self, library_id: str, kind: str, keys: list[str]) -> list[dict[str, Any]]:
        if not keys:
            return []
        param_name = {"items": "itemKey", "collections": "collectionKey", "searches": "searchKey"}[kind]
        query: dict[str, Any] = {param_name: ",".join(keys)}
        if kind == "items":
            query["includeTrashed"] = 1
        _, _, payload = self._request("GET", f"{self.library_path(library_id)}/{kind}", query=query)
        return payload or []

    def download_attachment_file(self, library_id: str, item_key: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url=self.settings.api_base.rstrip("/") + f"{self.library_path(library_id)}/items/{item_key}/file",
            method="GET",
            headers={
                "Zotero-API-Key": self.settings.api_key or "",
                "Zotero-API-Version": "3",
                "User-Agent": "zotero-headless/0.1",
            },
        )
        try:
            with urllib.request.urlopen(request) as response:
                status = response.status
                response_headers = dict(response.headers.items())
                body = response.read()
        except urllib.error.HTTPError as exc:  # type: ignore[name-defined]
            text = exc.read().decode("utf-8", errors="replace")
            raise ZoteroApiError(exc.code, exc.reason, text) from exc
        except urllib.error.URLError as exc:  # type: ignore[name-defined]
            raise RuntimeError(f"Failed to connect to Zotero API: {exc}") from exc

        if status != 200:
            raise ZoteroApiError(status, "Unexpected download status", None)
        return {
            "status": status,
            "headers": response_headers,
            "body": body,
        }

    def get_fulltext_versions(self, library_id: str, *, since: int = 0) -> tuple[dict[str, int], int]:
        query: dict[str, Any] = {"format": "versions"}
        if since:
            query["since"] = since
        _, headers, payload = self._request("GET", f"{self.library_path(library_id)}/fulltext", query=query)
        return {str(k): int(v) for k, v in (payload or {}).items()}, int(headers.get("Last-Modified-Version", "0"))

    def get_item_fulltext(self, library_id: str, item_key: str) -> dict[str, Any]:
        _, _, payload = self._request("GET", f"{self.library_path(library_id)}/items/{item_key}/fulltext")
        return payload or {}

    def create_item(self, library_id: str, item_data: dict[str, Any], *, library_version: int | None = None) -> dict[str, Any]:
        headers = {}
        if library_version is not None:
            headers["If-Unmodified-Since-Version"] = str(library_version)
        body = self._sanitize_item_payload(item_data)
        _, response_headers, payload = self._request(
            "POST",
            f"{self.library_path(library_id)}/items",
            headers=headers,
            json_body=[body],
        )
        if "citationKey" in body and self._payload_rejects_native_citation_key(payload):
            fallback_body = dict(body)
            fallback_body.pop("citationKey", None)
            _, response_headers, payload = self._request(
                "POST",
                f"{self.library_path(library_id)}/items",
                headers=headers,
                json_body=[fallback_body],
            )
        self._require_successful_create(payload)
        return {"result": payload, "version": int(response_headers.get("Last-Modified-Version", "0"))}

    def create_collection(
        self,
        library_id: str,
        collection_data: dict[str, Any],
        *,
        library_version: int | None = None,
    ) -> dict[str, Any]:
        headers = {}
        if library_version is not None:
            headers["If-Unmodified-Since-Version"] = str(library_version)
        body = self._sanitize_collection_payload(collection_data)
        _, response_headers, payload = self._request(
            "POST",
            f"{self.library_path(library_id)}/collections",
            headers=headers,
            json_body=[body],
        )
        self._require_successful_create(payload)
        return {"result": payload, "version": int(response_headers.get("Last-Modified-Version", "0"))}

    def upload_attachment_file(
        self,
        library_id: str,
        item_key: str,
        *,
        source_path: str,
        filename: str | None = None,
        content_type: str | None = None,
        previous_md5: str | None = None,
        upload_bytes: bytes | None = None,
        upload_filename: str | None = None,
        upload_content_type: str | None = None,
        md5: str | None = None,
        mtime: int | None = None,
    ) -> dict[str, Any]:
        path = Path(source_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Attachment source file not found: {path}")

        raw = upload_bytes if upload_bytes is not None else path.read_bytes()
        stat = path.stat()
        digest = md5 or hashlib.md5(raw).hexdigest()
        effective_mtime = mtime if mtime is not None else int(stat.st_mtime * 1000)
        resolved_filename = filename or path.name
        resolved_content_type = content_type or mimetypes.guess_type(resolved_filename)[0] or "application/octet-stream"
        resolved_upload_filename = upload_filename or resolved_filename
        resolved_upload_content_type = upload_content_type or resolved_content_type
        upload_digest = hashlib.md5(raw).hexdigest()
        auth_headers = {"If-Match": previous_md5} if previous_md5 else {"If-None-Match": "*"}
        form_fields = {
            "md5": digest,
            "filename": resolved_filename,
            "filesize": len(raw),
            "mtime": effective_mtime,
            "contentType": resolved_content_type,
        }
        if resolved_upload_filename != resolved_filename:
            form_fields["zipFilename"] = resolved_upload_filename
            form_fields["zipMD5"] = upload_digest
        _, _, auth_payload = self._request_form(
            "POST",
            f"{self.library_path(library_id)}/items/{item_key}/file",
            headers=auth_headers,
            form_fields=form_fields,
            expected=(200,),
        )
        if auth_payload.get("exists") in (1, "1", True):
            return {
                "uploaded": False,
                "exists": True,
                "md5": digest,
                "mtime": effective_mtime,
                "filename": resolved_filename,
                "contentType": resolved_content_type,
                "uploadFilename": resolved_upload_filename,
                "uploadMD5": upload_digest,
            }

        upload_url = auth_payload["url"]
        upload_content_type = auth_payload["contentType"]
        prefix = str(auth_payload.get("prefix") or "").encode("utf-8")
        suffix = str(auth_payload.get("suffix") or "").encode("utf-8")
        self._upload_to_url(upload_url, content_type=upload_content_type, body=prefix + raw + suffix, expected=(201,))
        _, _, _ = self._request_form(
            "POST",
            f"{self.library_path(library_id)}/items/{item_key}/file",
            headers=auth_headers,
            form_fields={"upload": auth_payload["uploadKey"]},
            expected=(204,),
        )
        return {
            "uploaded": True,
            "exists": False,
            "md5": digest,
            "mtime": effective_mtime,
            "filename": resolved_filename,
            "contentType": resolved_content_type,
            "uploadFilename": resolved_upload_filename,
            "uploadMD5": upload_digest,
        }

    def _request_form(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        form_fields: dict[str, Any],
        expected: tuple[int, ...] = (200,),
    ) -> tuple[int, dict[str, str], Any]:
        url = self.settings.api_base.rstrip("/") + path
        request_headers = self._headers(headers)
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(
            url=url,
            data=self._encode_form(form_fields),
            method=method,
            headers=request_headers,
        )
        try:
            with urllib.request.urlopen(request) as response:
                status = response.status
                response_headers = dict(response.headers.items())
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # type: ignore[name-defined]
            text = exc.read().decode("utf-8")
            if exc.code not in expected:
                raise ZoteroApiError(exc.code, exc.reason, text) from exc
            status = exc.code
            response_headers = dict(exc.headers.items())
        except urllib.error.URLError as exc:  # type: ignore[name-defined]
            raise RuntimeError(f"Failed to connect to Zotero API: {exc}") from exc

        if status not in expected:
            raise ZoteroApiError(status, "Unexpected status", text)
        if not text:
            return status, response_headers, None
        try:
            return status, response_headers, json.loads(text)
        except json.JSONDecodeError:
            return status, response_headers, text

    def update_item(
        self,
        library_id: str,
        item_key: str,
        item_data: dict[str, Any],
        *,
        item_version: int | None = None,
        full: bool = False,
    ) -> int:
        method = "PUT" if full else "PATCH"
        body = self._sanitize_item_payload(item_data)
        headers = {}
        if item_version is not None and "version" not in body:
            headers["If-Unmodified-Since-Version"] = str(item_version)
        try:
            _, response_headers, _ = self._request(
                method,
                f"{self.library_path(library_id)}/items/{item_key}",
                headers=headers,
                json_body=body,
                expected=(204,),
            )
        except ZoteroApiError as exc:
            if "citationKey" not in body or not self._error_rejects_native_citation_key(exc):
                raise
            fallback_body = dict(body)
            fallback_body.pop("citationKey", None)
            _, response_headers, _ = self._request(
                method,
                f"{self.library_path(library_id)}/items/{item_key}",
                headers=headers,
                json_body=fallback_body,
                expected=(204,),
            )
        return int(response_headers.get("Last-Modified-Version", "0"))

    def delete_item(self, library_id: str, item_key: str, *, item_version: int) -> int:
        _, response_headers, _ = self._request(
            "DELETE",
            f"{self.library_path(library_id)}/items/{item_key}",
            headers={"If-Unmodified-Since-Version": str(item_version)},
            expected=(204,),
        )
        return int(response_headers.get("Last-Modified-Version", "0"))

    def update_collection(
        self,
        library_id: str,
        collection_key: str,
        collection_data: dict[str, Any],
        *,
        collection_version: int | None = None,
    ) -> int:
        body = self._sanitize_collection_payload(collection_data)
        body.setdefault("key", collection_key)
        headers = {}
        if collection_version is not None and "version" not in body:
            body["version"] = int(collection_version)
            headers["If-Unmodified-Since-Version"] = str(collection_version)
        _, response_headers, _ = self._request(
            "PUT",
            f"{self.library_path(library_id)}/collections/{collection_key}",
            headers=headers,
            json_body=body,
        )
        return int(response_headers.get("Last-Modified-Version", "0"))

    def delete_collection(self, library_id: str, collection_key: str, *, collection_version: int) -> int:
        _, response_headers, _ = self._request(
            "DELETE",
            f"{self.library_path(library_id)}/collections/{collection_key}",
            headers={"If-Unmodified-Since-Version": str(collection_version)},
            expected=(204,),
        )
        return int(response_headers.get("Last-Modified-Version", "0"))
