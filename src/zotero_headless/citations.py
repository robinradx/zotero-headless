from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .config import Settings
from .core import CanonicalStore, EntityType
from .utils import ensure_dir


class CitationExportFormat(StrEnum):
    BIBLATEX = "biblatex"
    CSL_JSON = "csl-json"


_BIBLATEX_TYPE_MAP = {
    "blogPost": "online",
    "book": "book",
    "bookSection": "incollection",
    "conferencePaper": "inproceedings",
    "dataset": "dataset",
    "document": "misc",
    "forumPost": "online",
    "journalArticle": "article",
    "magazineArticle": "article",
    "manuscript": "unpublished",
    "newspaperArticle": "article",
    "patent": "patent",
    "podcast": "online",
    "preprint": "online",
    "presentation": "unpublished",
    "report": "report",
    "thesis": "thesis",
    "webpage": "online",
}

_CSL_TYPE_MAP = {
    "blogPost": "post-weblog",
    "book": "book",
    "bookSection": "chapter",
    "conferencePaper": "paper-conference",
    "dataset": "dataset",
    "document": "document",
    "forumPost": "post",
    "journalArticle": "article-journal",
    "magazineArticle": "article-magazine",
    "manuscript": "manuscript",
    "newspaperArticle": "article-newspaper",
    "patent": "patent",
    "podcast": "broadcast",
    "preprint": "manuscript",
    "presentation": "speech",
    "report": "report",
    "thesis": "thesis",
    "webpage": "webpage",
}

_TOP_LEVEL_FIELDS = (
    "DOI",
    "ISBN",
    "ISSN",
    "abstractNote",
    "accessDate",
    "archive",
    "archiveLocation",
    "date",
    "edition",
    "extra",
    "issue",
    "language",
    "number",
    "pages",
    "place",
    "proceedingsTitle",
    "publicationTitle",
    "publisher",
    "reportNumber",
    "rights",
    "series",
    "shortTitle",
    "title",
    "url",
    "volume",
    "websiteTitle",
)

_CITEABLE_ITEM_TYPES = {
    "artwork",
    "audioRecording",
    "bill",
    "blogPost",
    "book",
    "bookSection",
    "case",
    "computerProgram",
    "conferencePaper",
    "dataset",
    "dictionaryEntry",
    "document",
    "email",
    "encyclopediaArticle",
    "film",
    "forumPost",
    "hearing",
    "instantMessage",
    "interview",
    "journalArticle",
    "letter",
    "magazineArticle",
    "manuscript",
    "map",
    "newspaperArticle",
    "patent",
    "podcast",
    "preprint",
    "presentation",
    "radioBroadcast",
    "report",
    "standard",
    "statute",
    "thesis",
    "tvBroadcast",
    "videoRecording",
    "webpage",
}


@dataclass(slots=True)
class CitationEntry:
    key: str
    payload: dict[str, Any]


class CitationExportClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def enabled(self) -> bool:
        return bool(self.settings.citation_export_enabled)

    def status(self) -> dict[str, Any]:
        path = self.settings.resolved_citation_export_path()
        return {
            "enabled": self.enabled(),
            "format": self.settings.citation_export_format,
            "path": str(path),
            "exists": path.exists(),
        }

    def export_from_canonical(
        self,
        canonical: CanonicalStore,
        library_id: str | None = None,
        *,
        format_name: str | None = None,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        citation_format = CitationExportFormat(format_name or self.settings.citation_export_format)
        target_path = self._resolved_output_path(citation_format, output_path=output_path)
        ensure_dir(target_path.parent)

        libraries = [canonical.get_library(library_id)] if library_id else canonical.list_libraries()
        entries: list[CitationEntry] = []
        used_keys: dict[str, int] = {}
        active_libraries = 0
        for library in libraries:
            if not library:
                continue
            active_libraries += 1
            lib_id = str(library["library_id"])
            for entity in canonical.list_entities(lib_id, EntityType.ITEM, limit=100000):
                payload = dict(entity["payload"])
                if not self._is_citeable(payload):
                    continue
                base_key = self._citation_key(payload, str(entity["entity_key"]))
                key = self._unique_citation_key(base_key, used_keys)
                entries.append(CitationEntry(key=key, payload=payload))

        rendered = self._render(entries, citation_format)
        target_path.write_text(rendered, encoding="utf-8")
        return {
            "enabled": self.enabled(),
            "format": citation_format.value,
            "path": str(target_path),
            "library_id": library_id,
            "libraries": active_libraries,
            "exported": len(entries),
        }

    def _resolved_output_path(
        self,
        citation_format: CitationExportFormat,
        *,
        output_path: str | None = None,
    ) -> Path:
        if output_path:
            return Path(output_path).expanduser()
        if self.settings.citation_export_path:
            return Path(self.settings.citation_export_path).expanduser()
        suffix = ".json" if citation_format == CitationExportFormat.CSL_JSON else ".bib"
        return self.settings.resolved_state_dir() / f"citations{suffix}"

    def _render(self, entries: list[CitationEntry], citation_format: CitationExportFormat) -> str:
        if citation_format == CitationExportFormat.CSL_JSON:
            payload = [self._render_csl_entry(entry) for entry in entries]
            return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        lines = ["% Generated by zotero-headless", ""]
        for entry in entries:
            lines.extend(self._render_biblatex_entry(entry))
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _render_biblatex_entry(self, entry: CitationEntry) -> list[str]:
        payload = entry.payload
        item_type = str(payload.get("itemType") or "")
        bib_type = _BIBLATEX_TYPE_MAP.get(item_type, "misc")
        fields = self._payload_fields(payload)
        year, iso_date = self._date_parts(fields.get("date"))
        field_map: list[tuple[str, str]] = []
        authors = self._creator_names(payload.get("creators") or [], role="author")
        editors = self._creator_names(payload.get("creators") or [], role="editor")
        translators = self._creator_names(payload.get("creators") or [], role="translator")
        if authors:
            field_map.append(("author", " and ".join(authors)))
        if editors:
            field_map.append(("editor", " and ".join(editors)))
        if translators:
            field_map.append(("translator", " and ".join(translators)))
        self._append_bib_field(field_map, "title", fields.get("title"))
        self._append_bib_field(field_map, "shorttitle", fields.get("shortTitle"))
        self._append_bib_field(field_map, "abstract", fields.get("abstractNote"))
        self._append_bib_field(field_map, "journaltitle", fields.get("publicationTitle"))
        self._append_bib_field(field_map, "booktitle", fields.get("proceedingsTitle"))
        self._append_bib_field(field_map, "publisher", fields.get("publisher"))
        self._append_bib_field(field_map, "location", fields.get("place"))
        self._append_bib_field(field_map, "volume", fields.get("volume"))
        self._append_bib_field(field_map, "number", fields.get("issue") or fields.get("number"))
        self._append_bib_field(field_map, "pages", fields.get("pages"))
        self._append_bib_field(field_map, "doi", fields.get("DOI"))
        self._append_bib_field(field_map, "url", fields.get("url"))
        self._append_bib_field(field_map, "urldate", fields.get("accessDate"))
        self._append_bib_field(field_map, "isbn", fields.get("ISBN"))
        self._append_bib_field(field_map, "issn", fields.get("ISSN"))
        self._append_bib_field(field_map, "language", fields.get("language"))
        self._append_bib_field(field_map, "note", fields.get("extra"))
        self._append_bib_field(field_map, "date", iso_date)
        self._append_bib_field(field_map, "year", year)

        lines = [f"@{bib_type}{{{entry.key},"]
        for name, value in field_map:
            lines.append(f"  {name} = {{{self._bib_escape(value)}}},")
        if field_map and lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]
        lines.append("}")
        return lines

    def _append_bib_field(self, field_map: list[tuple[str, str]], name: str, value: object) -> None:
        if value is None:
            return
        text = str(value).strip()
        if text:
            field_map.append((name, text))

    def _render_csl_entry(self, entry: CitationEntry) -> dict[str, Any]:
        payload = entry.payload
        item_type = str(payload.get("itemType") or "")
        fields = self._payload_fields(payload)
        year, _iso_date = self._date_parts(fields.get("date"))
        csl: dict[str, Any] = {
            "id": entry.key,
            "type": _CSL_TYPE_MAP.get(item_type, "document"),
            "title": fields.get("title") or entry.key,
        }
        if authors := self._creator_name_parts(payload.get("creators") or [], role="author"):
            csl["author"] = authors
        if editors := self._creator_name_parts(payload.get("creators") or [], role="editor"):
            csl["editor"] = editors
        if translators := self._creator_name_parts(payload.get("creators") or [], role="translator"):
            csl["translator"] = translators
        if value := fields.get("publicationTitle"):
            csl["container-title"] = value
        elif value := fields.get("websiteTitle"):
            csl["container-title"] = value
        if value := fields.get("volume"):
            csl["volume"] = value
        if value := fields.get("issue") or fields.get("number"):
            csl["issue"] = value
        if value := fields.get("pages"):
            csl["page"] = value
        if value := fields.get("publisher"):
            csl["publisher"] = value
        if value := fields.get("place"):
            csl["publisher-place"] = value
        if value := fields.get("url"):
            csl["URL"] = value
        if value := fields.get("DOI"):
            csl["DOI"] = value
        if value := fields.get("ISBN"):
            csl["ISBN"] = value
        if value := fields.get("ISSN"):
            csl["ISSN"] = value
        if value := fields.get("abstractNote"):
            csl["abstract"] = value
        if value := fields.get("language"):
            csl["language"] = value
        if issued := self._csl_issued(fields.get("date")):
            csl["issued"] = issued
        elif year:
            csl["issued"] = {"date-parts": [[int(year)]]}
        return csl

    def _payload_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        fields = dict(payload.get("fields") or {})
        for field_name in _TOP_LEVEL_FIELDS:
            value = payload.get(field_name)
            if value is not None:
                fields[field_name] = value
        return fields

    def _is_citeable(self, payload: dict[str, Any]) -> bool:
        item_type = str(payload.get("itemType") or "")
        if item_type in {"attachment", "note", "annotation"}:
            return False
        return item_type in _CITEABLE_ITEM_TYPES

    def _citation_key(self, payload: dict[str, Any], fallback: str) -> str:
        raw = str(payload.get("citationKey") or fallback).strip()
        return re.sub(r"\s+", "_", raw) or fallback

    def _unique_citation_key(self, key: str, used_keys: dict[str, int]) -> str:
        count = used_keys.get(key, 0) + 1
        used_keys[key] = count
        if count == 1:
            return key
        return f"{key}-{count}"

    def _creator_names(self, creators: list[dict[str, Any]], *, role: str) -> list[str]:
        names: list[str] = []
        for creator in creators:
            creator_role = str(creator.get("creatorType") or "")
            if role == "author":
                if creator_role in {"editor", "translator"}:
                    continue
            elif creator_role != role:
                continue
            if literal := str(creator.get("name") or "").strip():
                names.append(f"{{{literal}}}")
                continue
            given = str(creator.get("firstName") or "").strip()
            family = str(creator.get("lastName") or "").strip()
            if family and given:
                names.append(f"{family}, {given}")
            elif family:
                names.append(family)
            elif given:
                names.append(given)
        return names

    def _creator_name_parts(self, creators: list[dict[str, Any]], *, role: str) -> list[dict[str, str]]:
        parts: list[dict[str, str]] = []
        for creator in creators:
            creator_role = str(creator.get("creatorType") or "")
            if role == "author":
                if creator_role in {"editor", "translator"}:
                    continue
            elif creator_role != role:
                continue
            if literal := str(creator.get("name") or "").strip():
                parts.append({"literal": literal})
                continue
            given = str(creator.get("firstName") or "").strip()
            family = str(creator.get("lastName") or "").strip()
            if family or given:
                name: dict[str, str] = {}
                if family:
                    name["family"] = family
                if given:
                    name["given"] = given
                parts.append(name)
        return parts

    def _csl_issued(self, value: object) -> dict[str, list[list[int]]] | None:
        year, iso_date = self._date_parts(value)
        if not year:
            return None
        if iso_date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso_date):
            y, m, d = iso_date.split("-")
            return {"date-parts": [[int(y), int(m), int(d)]]}
        if iso_date and re.fullmatch(r"\d{4}-\d{2}", iso_date):
            y, m = iso_date.split("-")
            return {"date-parts": [[int(y), int(m)]]}
        return {"date-parts": [[int(year)]]}

    def _date_parts(self, value: object) -> tuple[str | None, str | None]:
        if value is None:
            return None, None
        text = str(value).strip()
        if not text:
            return None, None
        if match := re.match(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$", text):
            year = match.group(1)
            month = match.group(2)
            day = match.group(3)
            if day:
                return year, f"{year}-{month}-{day}"
            if month:
                return year, f"{year}-{month}"
            return year, year
        if match := re.search(r"\b(\d{4})\b", text):
            return match.group(1), None
        return None, None

    def _bib_escape(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
