"""OOXML text-only readers; no Office engine, macros, formulas or answer inference."""

import json
import posixpath
import re
import stat
import struct
import unicodedata
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as XML  # type: ignore[import-untyped]
from pydantic import ValidationError

from app.admin.schemas import QuestionBody
from app.content.fingerprints import content_hash, fingerprint
from app.imports.errors import ImportFileError
from app.imports.limits import (
    CENTRAL_BYTES,
    PART_BYTES,
    ROW_BYTES,
    ROWS,
    UNPACKED_BYTES,
    UPLOAD_BYTES,
    XML_NODES,
    ZIP_ENTRIES,
)

S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
HEADERS = [
    "discipline",
    "topic",
    "question",
    "option_A",
    "option_B",
    "correct",
    "option_C",
    "option_D",
    "option_E",
    "option_F",
    "option_G",
    "option_H",
    "external_id",
    "kind",
    "source_reference",
    "license_reference",
    "source_page",
    "explanation",
    "source_id",
]
REQUIRED = {"discipline", "topic", "question", "option_A", "option_B", "correct"}
RU = {
    "дисциплина": "discipline",
    "тема": "topic",
    "вопрос": "question",
    "правильный ответ": "correct",
    "внешний id": "external_id",
    "тип": "kind",
    "источник": "source_reference",
    "лицензия": "license_reference",
    "страница": "source_page",
    "объяснение": "explanation",
    **{"ответ " + c.lower(): "option_" + c for c in "ABCDEFGH"},
}


def xml_events(stream: Any) -> Any:
    return XML.iterparse(
        stream, events=("start", "end"), forbid_dtd=True, forbid_entities=True, forbid_external=True
    )


def preflight(path: Path, fmt: str) -> zipfile.ZipFile:
    size = path.stat().st_size
    if size < 22 or size > UPLOAD_BYTES:
        raise ImportFileError("FILE_FORMAT")
    with path.open("rb") as file:
        file.seek(max(0, size - 65557))
        tail = file.read()
    offset = tail.rfind(b"PK\x05\x06")
    if offset < 0 or len(tail) - offset < 22:
        raise ImportFileError("FILE_FORMAT")
    _, disk, cd_disk, disk_entries, entries, cd_size, cd_offset, comment = struct.unpack(
        "<4s4H2LH", tail[offset : offset + 22]
    )
    if (
        disk
        or cd_disk
        or entries != disk_entries
        or entries > ZIP_ENTRIES
        or cd_size > CENTRAL_BYTES
    ):
        raise ImportFileError("ZIP_LIMIT")
    if cd_offset + cd_size > size or offset + 22 + comment != len(tail) or b"PK\x06\x06" in tail:
        raise ImportFileError("FILE_FORMAT")
    archive = zipfile.ZipFile(path)
    try:
        infos = archive.infolist()
        if len(infos) != entries or sum(info.file_size for info in infos) > UNPACKED_BYTES:
            raise ImportFileError("ZIP_LIMIT")
        seen = set()
        for info in infos:
            name = info.filename
            key = unicodedata.normalize("NFC", name).casefold()
            parts = name.rstrip("/").split("/")
            if (
                key in seen
                or len(name) > 160
                or not re.fullmatch(r"[A-Za-z0-9_./\[\]-]+", name)
                or name.startswith("/")
                or any(part in ("", ".", "..") for part in parts)
                or stat.S_ISLNK(info.external_attr >> 16)
                or info.flag_bits & 1
                or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
            ):
                raise ImportFileError("UNSAFE_PACKAGE")
            seen.add(key)
            if info.file_size > PART_BYTES or (
                info.file_size > 1048576 and info.file_size > max(1, info.compress_size) * 250
            ):
                raise ImportFileError("ZIP_LIMIT")
            if info.is_dir():
                continue
            if not (
                name == "[Content_Types].xml"
                or name.startswith(("_rels/", "docProps/", "xl/" if fmt == "xlsx" else "word/"))
            ):
                raise ImportFileError("UNSAFE_PACKAGE")
            if not name.endswith((".xml", ".rels")) or any(
                part in key
                for part in (
                    "vbaproject",
                    "activex",
                    "embeddings",
                    "externallinks",
                    "customxml",
                    "connections",
                )
            ):
                raise ImportFileError("UNSAFE_PACKAGE")
        names = set(archive.namelist())
        main = "xl/workbook.xml" if fmt == "xlsx" else "word/document.xml"
        if not {"[Content_Types].xml", "_rels/.rels", main}.issubset(names):
            raise ImportFileError("FILE_FORMAT")
        nodes = 0
        main_type = False
        for info in infos:
            if info.is_dir():
                continue
            with archive.open(info) as stream:
                first = True
                for event, element in xml_events(stream):
                    if event == "start":
                        if first:
                            expected_root = (
                                "{http://schemas.openxmlformats.org/package/2006/content-types}Types"
                                if info.filename == "[Content_Types].xml"
                                else "{http://schemas.openxmlformats.org/package/2006/relationships}Relationships"
                                if info.filename.endswith(".rels")
                                else S + "workbook"
                                if info.filename == "xl/workbook.xml"
                                else W + "document"
                                if info.filename == "word/document.xml"
                                else None
                            )
                            if expected_root is not None and element.tag != expected_root:
                                raise ImportFileError("FILE_FORMAT")
                            first = False
                        nodes += 1
                        if nodes > XML_NODES:
                            raise ImportFileError("ZIP_LIMIT")
                        tag = element.tag
                        if tag == S + "f" or tag == S + "definedName":
                            raise ImportFileError("FORMULA")
                        if tag in {
                            W + "altChunk",
                            W + "object",
                            W + "ins",
                            W + "del",
                            W + "instrText",
                            W + "fldSimple",
                        }:
                            raise ImportFileError("UNSAFE_PACKAGE")
                        if tag.endswith("}Relationship"):
                            target = element.get("Target", "")
                            if (
                                element.get("TargetMode", "").lower() == "external"
                                or not target
                                or any(c in target for c in (":", "%", "\\", "\x00", "#"))
                            ):
                                raise ImportFileError("UNSAFE_PACKAGE")
                            folder = posixpath.dirname(posixpath.dirname(info.filename))
                            resolved = posixpath.normpath(
                                target.lstrip("/")
                                if target.startswith("/")
                                else posixpath.join(folder, target)
                            )
                            if resolved.startswith("../") or resolved not in names:
                                raise ImportFileError("UNSAFE_PACKAGE")
                        if info.filename == "[Content_Types].xml" and tag.endswith("}Override"):
                            mime = element.get("ContentType", "")
                            if any(
                                c in mime.lower() for c in ("macro", "vba", "activex", "oleobject")
                            ):
                                raise ImportFileError("UNSAFE_PACKAGE")
                            expected = (
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
                                if fmt == "xlsx"
                                else "application/vnd.openxmlformats-officedocument."
                                "wordprocessingml.document.main+xml"
                            )
                            if element.get("PartName") == "/" + main and mime == expected:
                                main_type = True
                    else:
                        element.clear()
        if not main_type:
            raise ImportFileError("FILE_FORMAT")
        return archive
    except BaseException:
        archive.close()
        raise


def header(values: list[str]) -> list[str]:
    result = []
    canonical = {h.lower(): h for h in HEADERS}
    for value in values:
        key = value.strip().lower()
        result.append(RU.get(key, canonical.get(key, "")))
    if not REQUIRED.issubset(result) or "" in result or len(set(result)) != len(result):
        raise ImportFileError("TEMPLATE")
    return result


def xlsx_rows(archive: zipfile.ZipFile) -> Iterator[tuple[str, list[str]]]:
    strings: list[str] = []
    total = 0
    if "xl/sharedStrings.xml" in archive.namelist():
        with archive.open("xl/sharedStrings.xml") as stream:
            for event, node in xml_events(stream):
                if event == "end" and node.tag == S + "si":
                    value = "".join(n.text or "" for n in node.iter(S + "t"))
                    total += len(value.encode())
                    if len(strings) >= 100000 or total > PART_BYTES:
                        raise ImportFileError("ZIP_LIMIT")
                    strings.append(value)
                    node.clear()
    with archive.open("xl/workbook.xml") as stream:
        workbook = XML.parse(stream, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    sheets = list(workbook.getroot().iter(S + "sheet"))
    if len(sheets) != 1 or "xl/_rels/workbook.xml.rels" not in archive.namelist():
        raise ImportFileError("TEMPLATE")
    with archive.open("xl/_rels/workbook.xml.rels") as stream:
        rels = XML.parse(stream, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    relation = next((n for n in rels.getroot() if n.get("Id") == sheets[0].get(R + "id")), None)
    if relation is None:
        raise ImportFileError("TEMPLATE")
    target = relation.get("Target", "")
    name = posixpath.normpath(target.lstrip("/") if target.startswith("/") else "xl/" + target)
    with archive.open(name) as stream:
        for event, node in xml_events(stream):
            if event == "end" and node.tag == S + "row":
                row_number = node.get("r", "")
                if not re.fullmatch(r"[1-9][0-9]{0,6}", row_number) or int(row_number) > 1048576:
                    raise ImportFileError("TEMPLATE")
                values: dict[int, str] = {}
                for cell in node.findall(S + "c"):
                    reference = cell.get("r", "")
                    match = re.fullmatch(r"([A-Z]{1,2})([1-9][0-9]{0,6})", reference)
                    if not match or match[2] != row_number:
                        raise ImportFileError("TEMPLATE")
                    col = 0
                    for c in match[1]:
                        col = col * 26 + ord(c) - 64
                    if col > 32 or col in values:
                        raise ImportFileError("TEMPLATE")
                    value = cell.findtext(S + "v", default="")
                    kind = cell.get("t")
                    if kind == "s":
                        if not value.isdigit() or int(value) >= len(strings):
                            raise ImportFileError("TEMPLATE")
                        value = strings[int(value)]
                    elif kind == "inlineStr":
                        value = "".join(n.text or "" for n in cell.iter(S + "t"))
                    elif kind not in (None, "n", "str", "b"):
                        raise ImportFileError("TEMPLATE")
                    values[col] = value
                if any(v.strip() for v in values.values()):
                    yield (
                        "sheet:row:" + row_number,
                        [values.get(i, "") for i in range(1, max(values) + 1)],
                    )
                node.clear()


def docx_rows(archive: zipfile.ZipFile) -> Iterator[tuple[str, list[str]]]:
    table = 0
    row = 0
    depth = 0
    with archive.open("word/document.xml") as stream:
        for event, node in xml_events(stream):
            if event == "start" and node.tag == W + "tbl":
                depth += 1
                if depth > 1:
                    raise ImportFileError("TEMPLATE")
                table += 1
                row = 0
            if event == "end" and node.tag == W + "tr":
                row += 1
                values = []
                if list(node.iter(W + "vMerge")) or list(node.iter(W + "gridSpan")):
                    raise ImportFileError("TEMPLATE")
                for cell in node.findall(W + "tc"):
                    paragraphs = []
                    for paragraph in cell.findall(W + "p"):
                        paragraphs.append(
                            "".join(
                                (n.text or "")
                                if n.tag == W + "t"
                                else "\n"
                                if n.tag == W + "br"
                                else "\t"
                                if n.tag == W + "tab"
                                else ""
                                for n in paragraph.iter()
                            )
                        )
                    values.append("\n".join(paragraphs))
                if any(v.strip() for v in values):
                    yield f"table:{table}:row:{row}", values
                node.clear()
            if event == "end" and node.tag == W + "tbl":
                depth -= 1


def normalized_row(values: dict[str, str], position: int, location: str) -> dict[str, Any]:
    values = {
        k: unicodedata.normalize("NFC", v).strip().replace("\r\n", "\n") for k, v in values.items()
    }
    result: dict[str, Any] = {
        "position": position,
        "location": location,
        "discipline": values.get("discipline", "")[:512],
        "topic": values.get("topic", "")[:512],
        "payload": {},
        "errors": [],
        "warnings": [],
        "external_key": "",
        "generated_key": False,
        "fingerprint": None,
        "content_hash": None,
    }
    try:
        if any("\x00" in value for value in values.values()):
            raise ValueError("INVALID_TEXT")
        if (
            not values.get("discipline")
            or not values.get("topic")
            or len(values.get("discipline", "")) > 512
            or len(values.get("topic", "")) > 512
        ):
            raise ValueError("REQUIRED_CATALOG")
        correct = set(re.split(r"[,;|\s]+", values.get("correct", "").upper()))
        choices = [
            {"code": c, "text": values["option_" + c], "is_correct": c in correct}
            for c in "ABCDEFGH"
            if values.get("option_" + c)
        ]
        if not correct or not correct.issubset({c["code"] for c in choices}):
            raise ValueError("INVALID_CORRECT")
        body = QuestionBody(
            text=values.get("question", ""),
            kind=values.get("kind") or "single_choice",
            options=choices,
            source_id=values.get("source_id") or None,
            **{
                k: values.get(k) or None
                for k in ("explanation", "source_reference", "license_reference", "source_page")
            },
        )
        result["payload"] = body.model_dump(mode="json")
        result["fingerprint"] = fingerprint(body)
        result["content_hash"] = content_hash(body)
        external = values.get("external_id", "")
        if external and len(external) > 124:
            raise ValueError("INVALID_EXTERNAL_ID")
        result["generated_key"] = not bool(external)
        result["external_key"] = (
            "id:" + external if external else "auto:" + content_hash(body, include_key=False)
        )
        if not external:
            result["warnings"].append("GENERATED_ID")
        if body.kind == "multiple_choice":
            result["warnings"].append("DRAFT_ONLY_KIND")
        if len(json.dumps(result, ensure_ascii=False).encode()) > ROW_BYTES:
            raise ValueError("ROW_SIZE")
    except ValidationError as exc:
        result["payload"] = {}
        fields = {
            str(error["loc"][0]) if error["loc"] else "answer_key"
            for error in exc.errors(include_input=False, include_context=False)
        }
        result["errors"] = [
            "INVALID_QUESTION_TEXT" if field == "text" else "INVALID_" + field.upper()
            for field in sorted(fields)
        ]
    except (ValueError, TypeError) as exc:
        result["payload"] = {}
        result["errors"] = [
            str(exc)
            if str(exc)
            in {
                "INVALID_TEXT",
                "REQUIRED_CATALOG",
                "INVALID_CORRECT",
                "INVALID_EXTERNAL_ID",
                "ROW_SIZE",
            }
            else "INVALID_STRUCTURE"
        ]
    return result


def parse(path: Path, fmt: str) -> Iterator[dict[str, Any]]:
    with preflight(path, fmt) as archive:
        columns = None
        count = 0
        last_table = ""
        rows = xlsx_rows(archive) if fmt == "xlsx" else docx_rows(archive)
        for location, values in rows:
            if fmt == "docx":
                current = location.split(":row:")[0]
                if current != last_table:
                    columns = None
                    last_table = current
            if columns is None:
                columns = header(values)
                continue
            count += 1
            if count > ROWS:
                raise ImportFileError("ROW_LIMIT")
            if len(values) > len(columns) and any(values[len(columns) :]):
                result = normalized_row({}, count, location)
            else:
                result = normalized_row(
                    dict(
                        zip(
                            columns,
                            values[: len(columns)] + [""] * max(0, len(columns) - len(values)),
                            strict=True,
                        )
                    ),
                    count,
                    location,
                )
            yield result
        if not count:
            raise ImportFileError("EMPTY_FILE")
