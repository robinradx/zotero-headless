import unittest
from pathlib import Path
import tempfile
import io
import zipfile

from zotero_headless.config import Settings
from zotero_headless.web_api import ZoteroWebClient


class InspectingWebClient(ZoteroWebClient):
    def __init__(self):
        super().__init__(Settings(api_key="test-key"))
        self.calls: list[dict] = []
        self.next_payload = {"successful": {"0": {"key": "ABCD1234"}}, "failed": {}}
        self.next_headers = {"Last-Modified-Version": "88"}
        self.next_status = 200
        self.form_calls: list[dict] = []
        self.upload_calls: list[dict] = []
        self.next_form_payload = {}
        self.next_form_headers = {}
        self.next_form_status = 200
        self.next_upload_payload = None
        self.next_upload_headers = {}
        self.next_upload_status = 201

    def _request(self, method, path, *, query=None, headers=None, json_body=None, expected=(200,)):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": query,
                "headers": headers,
                "json_body": json_body,
                "expected": expected,
            }
        )
        return self.next_status, self.next_headers, self.next_payload

    def _request_form(self, method, path, *, headers=None, form_fields=None, expected=(200,)):
        self.form_calls.append(
            {
                "method": method,
                "path": path,
                "headers": headers,
                "form_fields": form_fields,
                "expected": expected,
            }
        )
        return self.next_form_status, self.next_form_headers, self.next_form_payload

    def _upload_to_url(self, url, *, content_type, body, expected=(201,)):
        self.upload_calls.append(
            {
                "url": url,
                "content_type": content_type,
                "body": body,
                "expected": expected,
            }
        )
        return self.next_upload_status, self.next_upload_headers, self.next_upload_payload


class ZoteroWebClientTests(unittest.TestCase):
    def test_create_item_strips_internal_headless_properties(self):
        client = InspectingWebClient()

        result = client.create_item(
            "user:123",
            {
                "key": "ITEM1234",
                "itemType": "book",
                "title": "Draft",
                "fields": {"title": "Draft"},
                "citationKey": "doe2026draft",
                "citationAliases": ["doe2026draft", "doe2026book"],
                "extra": "Citation Key: doe2026draft\ntex.ids: doe2026draft, doe2026book",
                "attachments": [{"path": "storage:test.pdf"}],
                "notes": [{"note": "<p>Draft</p>"}],
            },
            library_version=77,
        )

        self.assertEqual(result["version"], 88)
        body = client.calls[0]["json_body"][0]
        self.assertEqual(body["key"], "ITEM1234")
        self.assertEqual(body["itemType"], "book")
        self.assertEqual(body["title"], "Draft")
        self.assertEqual(body["citationKey"], "doe2026draft")
        self.assertEqual(body["extra"], "Citation Key: doe2026draft\ntex.ids: doe2026draft, doe2026book")
        self.assertNotIn("fields", body)
        self.assertNotIn("citationAliases", body)
        self.assertNotIn("attachments", body)
        self.assertNotIn("notes", body)

    def test_create_collection_strips_non_zotero_properties(self):
        client = InspectingWebClient()

        result = client.create_collection(
            "user:123",
            {
                "key": "COLL1234",
                "name": "Reading",
                "title": "Reading",
                "parentCollectionKey": "PARENT999",
                "parentCollection": "PARENT999",
            },
            library_version=77,
        )

        self.assertEqual(result["version"], 88)
        body = client.calls[0]["json_body"][0]
        self.assertEqual(body["key"], "COLL1234")
        self.assertEqual(body["name"], "Reading")
        self.assertEqual(body["parentCollection"], "PARENT999")
        self.assertNotIn("title", body)
        self.assertNotIn("parentCollectionKey", body)

    def test_create_collection_raises_when_zotero_reports_failed_objects(self):
        client = InspectingWebClient()
        client.next_payload = {
            "successful": {},
            "failed": {"0": {"code": 400, "message": "Invalid property 'title'"}},
        }

        with self.assertRaisesRegex(RuntimeError, "Invalid property 'title'"):
            client.create_collection("user:123", {"key": "COLL1234", "name": "Reading", "title": "Reading"})

    def test_update_item_strips_internal_headless_properties(self):
        client = InspectingWebClient()
        client.next_status = 204
        client.next_payload = None

        version = client.update_item(
            "user:123",
            "ITEM1234",
            {
                "title": "Updated",
                "fields": {"title": "Updated"},
                "citationKey": "doe2026updated",
            },
            item_version=55,
        )

        self.assertEqual(version, 88)
        body = client.calls[0]["json_body"]
        self.assertEqual(body["title"], "Updated")
        self.assertEqual(body["citationKey"], "doe2026updated")
        self.assertNotIn("fields", body)

    def test_create_item_retries_without_native_citation_key_if_api_rejects_it(self):
        client = InspectingWebClient()

        def request_with_citation_retry(method, path, *, query=None, headers=None, json_body=None, expected=(200,)):
            client.calls.append(
                {
                    "method": method,
                    "path": path,
                    "query": query,
                    "headers": headers,
                    "json_body": json_body,
                    "expected": expected,
                }
            )
            if len(client.calls) == 1:
                return 200, client.next_headers, {
                    "successful": {},
                    "failed": {"0": {"code": 400, "message": "Invalid property 'citationKey'"}},
                }
            return 200, client.next_headers, client.next_payload

        client._request = request_with_citation_retry  # type: ignore[method-assign]

        result = client.create_item(
            "user:123",
            {
                "itemType": "book",
                "title": "Draft",
                "citationKey": "doe2026draft",
                "extra": "Citation Key: doe2026draft",
            },
        )

        self.assertEqual(result["version"], 88)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[0]["json_body"][0]["citationKey"], "doe2026draft")
        self.assertNotIn("citationKey", client.calls[1]["json_body"][0])
        self.assertEqual(client.calls[1]["json_body"][0]["extra"], "Citation Key: doe2026draft")

    def test_update_item_retries_without_native_citation_key_if_api_rejects_it(self):
        client = InspectingWebClient()

        def request_with_citation_retry(method, path, *, query=None, headers=None, json_body=None, expected=(200,)):
            client.calls.append(
                {
                    "method": method,
                    "path": path,
                    "query": query,
                    "headers": headers,
                    "json_body": json_body,
                    "expected": expected,
                }
            )
            if len(client.calls) == 1:
                from zotero_headless.web_api import ZoteroApiError

                raise ZoteroApiError(400, "Bad Request", '{"error":"Invalid property \\"citationKey\\""}')
            return 204, client.next_headers, None

        client._request = request_with_citation_retry  # type: ignore[method-assign]

        version = client.update_item(
            "user:123",
            "ITEM1234",
            {
                "title": "Updated",
                "citationKey": "doe2026updated",
                "extra": "Citation Key: doe2026updated",
            },
            item_version=55,
        )

        self.assertEqual(version, 88)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[0]["json_body"]["citationKey"], "doe2026updated")
        self.assertNotIn("citationKey", client.calls[1]["json_body"])

    def test_create_item_maps_parent_item_key_to_parent_item(self):
        client = InspectingWebClient()

        client.create_item(
            "user:123",
            {
                "key": "NOTE1234",
                "itemType": "note",
                "note": "<p>Child note</p>",
                "parentItemKey": "PARENT123",
            },
        )

        body = client.calls[0]["json_body"][0]
        self.assertEqual(body["parentItem"], "PARENT123")
        self.assertNotIn("parentItemKey", body)

    def test_create_annotation_strips_derived_title_and_internal_annotation_fields(self):
        client = InspectingWebClient()

        client.create_item(
            "user:123",
            {
                "key": "ANNO1234",
                "itemType": "annotation",
                "title": "highlight@4: Important passage",
                "annotationType": "highlight",
                "annotationTypeID": 1,
                "annotationText": "Important passage",
                "annotationPageLabel": "4",
                "parentItemKey": "ATTACH123",
            },
        )

        body = client.calls[0]["json_body"][0]
        self.assertEqual(body["parentItem"], "ATTACH123")
        self.assertEqual(body["annotationType"], "highlight")
        self.assertEqual(body["annotationText"], "Important passage")
        self.assertEqual(body["annotationPageLabel"], "4")
        self.assertNotIn("title", body)
        self.assertNotIn("annotationTypeID", body)
        self.assertNotIn("parentItemKey", body)

    def test_create_attachment_keeps_filename_for_remote_metadata(self):
        client = InspectingWebClient()

        client.create_item(
            "user:123",
            {
                "key": "ATTACH01",
                "itemType": "attachment",
                "linkMode": "imported_file",
                "filename": "paper.pdf",
                "contentType": "application/pdf",
            },
        )

        body = client.calls[0]["json_body"][0]
        self.assertEqual(body["filename"], "paper.pdf")
        self.assertEqual(body["contentType"], "application/pdf")

    def test_upload_attachment_file_authorizes_uploads_and_registers(self):
        client = InspectingWebClient()
        client.next_form_payload = {
            "url": "https://uploads.example.test/file",
            "contentType": "application/octet-stream",
            "prefix": "prefix-",
            "suffix": "-suffix",
            "uploadKey": "UPLOAD123",
        }
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "paper.txt"
            source.write_text("hello", encoding="utf-8")

            result = client.upload_attachment_file("user:123", "ATTACH01", source_path=str(source))

        self.assertTrue(result["uploaded"])
        self.assertFalse(result["exists"])
        self.assertEqual(result["filename"], "paper.txt")
        self.assertEqual(result["contentType"], "text/plain")
        self.assertEqual(client.form_calls[0]["path"], "/users/123/items/ATTACH01/file")
        self.assertEqual(client.form_calls[0]["headers"], {"If-None-Match": "*"})
        self.assertEqual(client.form_calls[0]["form_fields"]["filename"], "paper.txt")
        self.assertEqual(client.upload_calls[0]["url"], "https://uploads.example.test/file")
        self.assertEqual(client.upload_calls[0]["content_type"], "application/octet-stream")
        self.assertEqual(client.upload_calls[0]["body"], b"prefix-hello-suffix")
        self.assertEqual(client.form_calls[1]["form_fields"], {"upload": "UPLOAD123"})

    def test_upload_attachment_file_short_circuits_when_file_exists(self):
        client = InspectingWebClient()
        client.next_form_payload = {"exists": 1}
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "paper.pdf"
            source.write_bytes(b"%PDF-1.4")

            result = client.upload_attachment_file("user:123", "ATTACH01", source_path=str(source))

        self.assertFalse(result["uploaded"])
        self.assertTrue(result["exists"])
        self.assertEqual(client.form_calls[0]["headers"], {"If-None-Match": "*"})
        self.assertEqual(client.upload_calls, [])
        self.assertEqual(len(client.form_calls), 1)

    def test_upload_attachment_file_uses_if_match_for_existing_files(self):
        client = InspectingWebClient()
        client.next_form_payload = {"exists": 1}
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "paper.pdf"
            source.write_bytes(b"%PDF-1.4")

            client.upload_attachment_file(
                "user:123",
                "ATTACH01",
                source_path=str(source),
                previous_md5="old-md5",
            )

        self.assertEqual(client.form_calls[0]["headers"], {"If-Match": "old-md5"})

    def test_upload_attachment_file_supports_zip_transport_fields(self):
        client = InspectingWebClient()
        client.next_form_payload = {
            "url": "https://uploads.example.test/file",
            "contentType": "application/zip",
            "prefix": "",
            "suffix": "",
            "uploadKey": "UPLOAD123",
        }
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "index.html"
            source.write_text("<html>snapshot</html>", encoding="utf-8")
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("index.html", "<html>snapshot</html>")

            result = client.upload_attachment_file(
                "user:123",
                "ATTACH01",
                source_path=str(source),
                filename="index.html",
                content_type="text/html",
                upload_bytes=zip_buffer.getvalue(),
                upload_filename="ATTACH01.zip",
                upload_content_type="application/zip",
                md5="raw-md5",
                mtime=1234567890,
            )

        self.assertTrue(result["uploaded"])
        form = client.form_calls[0]["form_fields"]
        self.assertEqual(form["md5"], "raw-md5")
        self.assertEqual(form["filename"], "index.html")
        self.assertEqual(form["zipFilename"], "ATTACH01.zip")
        self.assertIn("zipMD5", form)
        self.assertEqual(form["mtime"], 1234567890)
        self.assertEqual(client.upload_calls[0]["content_type"], "application/zip")

    def test_sanitize_item_payload_strips_headless_cache_fields(self):
        client = InspectingWebClient()

        client.create_item(
            "user:123",
            {
                "key": "ATTACH01",
                "itemType": "attachment",
                "filename": "paper.pdf",
                "headlessFilePath": "/tmp/cache/paper.pdf",
                "headlessFileMd5": "abc",
                "headlessFileETag": "etag",
                "fulltext": {"content": "hello"},
            },
        )

        body = client.calls[0]["json_body"][0]
        self.assertNotIn("headlessFilePath", body)
        self.assertNotIn("headlessFileMd5", body)
        self.assertNotIn("headlessFileETag", body)
        self.assertNotIn("fulltext", body)


if __name__ == "__main__":
    unittest.main()
