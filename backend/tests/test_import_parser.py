import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from app.imports.api import csv_safe
from app.imports.errors import ImportFileError
from app.imports.parser import parse
from app.imports.runner import run_parser
from app.imports.store import Store
from app.imports.templates import MINIMAL_HEADERS, document

ROW = ["TEST DISCIPLINE", "TEST TOPIC", "SYNTHETIC QUESTION", "First", "Second", "A"]


def rewrite(raw, name, transform):
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(out, "w") as target:
        for part in source.namelist():
            value = source.read(part)
            target.writestr(part, transform(value) if part == name else value)
    return out.getvalue()


def read(tmp_path, raw, fmt="xlsx"):
    path = tmp_path / ("input." + fmt)
    path.write_bytes(raw)
    return list(parse(path, fmt))


@pytest.mark.parametrize("fmt", ["xlsx", "docx"])
def test_simple_templates_optional_metadata_and_explicit_key(tmp_path, fmt):
    rows = read(tmp_path, document(fmt, [ROW]), fmt)
    assert len(rows) == 1 and rows[0]["errors"] == []
    assert rows[0]["payload"]["source_reference"] is None
    assert rows[0]["payload"]["license_reference"] is None
    assert rows[0]["external_key"].startswith("auto:")
    assert rows[0]["payload"]["options"][0]["is_correct"] is True
    explicit = read(
        tmp_path, document(fmt, [[*ROW, "stable-1"]], [*MINIMAL_HEADERS, "external_id"]), fmt
    )
    assert explicit[0]["external_key"] == "id:stable-1"


def test_auto_ids_stable_across_formats_order_metadata_and_answer_correction(tmp_path):
    first = read(tmp_path, document("xlsx", [ROW]))[0]
    second = read(
        tmp_path, document("docx", [[*ROW, "optional"]], [*MINIMAL_HEADERS, "explanation"]), "docx"
    )[0]
    corrected = read(tmp_path, document("xlsx", [[*ROW[:5], "B"]]))[0]
    assert first["external_key"] == second["external_key"] == corrected["external_key"]
    assert first["fingerprint"] != second["fingerprint"] != corrected["fingerprint"]


@pytest.mark.parametrize(
    "index,value,code",
    [
        (0, "", "REQUIRED_CATALOG"),
        (2, "", "INVALID_QUESTION_TEXT"),
        (4, "", "INVALID_OPTIONS"),
        (5, "Z", "INVALID_CORRECT"),
        (5, "A B", "INVALID_ANSWER_KEY"),
    ],
)
def test_row_errors_have_locations_and_safe_field_codes(tmp_path, index, value, code):
    row = ROW.copy()
    row[index] = value
    result = read(tmp_path, document("xlsx", [row]))[0]
    assert code in result["errors"] and result["location"] == "sheet:row:2"
    assert result["payload"] == {}


def test_multiple_correct_only_when_explicitly_typed(tmp_path):
    row = [*ROW[:5], "A;B", "multiple_choice"]
    result = read(tmp_path, document("xlsx", [row], [*MINIMAL_HEADERS, "kind"]))[0]
    assert result["errors"] == [] and "DRAFT_ONLY_KIND" in result["warnings"]
    assert all(option["is_correct"] for option in result["payload"]["options"])


@pytest.mark.parametrize("fmt", ["xlsx", "docx"])
def test_blank_downloadable_template_is_not_fake_content(tmp_path, fmt):
    with pytest.raises(ImportFileError, match="EMPTY_FILE"):
        read(tmp_path, document(fmt), fmt)


@pytest.mark.parametrize(
    "name,transform,code",
    [
        ("xl/worksheets/sheet1.xml", lambda v: v.replace(b"<is>", b"<f>1+1</f><is>", 1), "FORMULA"),
        (
            "_rels/.rels",
            lambda v: v.replace(
                b'Target="xl/workbook.xml"', b'Target="https://bad.invalid/a" TargetMode="External"'
            ),
            "UNSAFE_PACKAGE",
        ),
        (
            "xl/workbook.xml",
            lambda v: b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]>' + v,
            None,
        ),
        (
            "[Content_Types].xml",
            lambda v: v.replace(
                b"spreadsheetml.sheet.main+xml", b"ms-excel.sheet.macroEnabled.main+xml"
            ),
            "UNSAFE_PACKAGE",
        ),
        ("xl/workbook.xml", lambda v: v.replace(b"2006/main", b"2006/evil"), "FILE_FORMAT"),
        (
            "xl/worksheets/sheet1.xml",
            lambda v: v.replace(b'row r="2"', b'row r="999999999999"'),
            "TEMPLATE",
        ),
    ],
)
def test_rejects_unsafe_office_parts(tmp_path, name, transform, code):
    from defusedxml.common import DefusedXmlException

    with pytest.raises((ImportFileError, DefusedXmlException)) as error:
        read(tmp_path, rewrite(document("xlsx", [ROW]), name, transform))
    if code:
        assert error.value.code == code


@pytest.mark.parametrize(
    "part", ["../escape.xml", "xl/vbaProject.bin", "xl/embeddings/payload.xml"]
)
def test_no_extraction_or_embedded_objects(tmp_path, part):
    out = io.BytesIO(document("xlsx", [ROW]))
    with zipfile.ZipFile(out, "a") as archive:
        archive.writestr(part, b"<test/>")
    with pytest.raises(ImportFileError, match="UNSAFE_PACKAGE"):
        read(tmp_path, out.getvalue())
    assert not (tmp_path.parent / "escape.xml").exists()


def test_limits_duplicates_zip_bomb_and_rows(tmp_path, monkeypatch):
    out = io.BytesIO(document("xlsx", [ROW]))
    with zipfile.ZipFile(out, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/bomb.xml", b" " * 2_000_000)
    with pytest.raises(ImportFileError, match="ZIP_LIMIT"):
        read(tmp_path, out.getvalue())
    monkeypatch.setattr("app.imports.parser.ROWS", 1)
    with pytest.raises(ImportFileError, match="ROW_LIMIT"):
        read(tmp_path, document("xlsx", [ROW, ROW]))


@pytest.mark.parametrize(
    "value", ["=1+1", "+cmd", "-12", "@SUM(A1)", " \t=evil", "\rvalue", "\ufeff=evil"]
)
def test_export_formula_injection_is_neutralized(value):
    assert csv_safe(value).startswith("'")


async def test_real_isolated_parser_hash_verification_and_cancellation(tmp_path, settings):
    store = Store(settings.model_copy(update={"import_storage_dir": tmp_path / "private"}))
    key = "a" * 32
    raw = document("xlsx", [ROW])
    store.path(key).write_bytes(raw)

    async def check():
        pass

    output, metrics, work = await run_parser(
        store, key, "xlsx", hashlib.sha256(raw).hexdigest(), check
    )
    assert json.loads(output.read_text())["errors"] == []
    assert metrics["count"] == 1 and metrics["max_rss_kib"] < 256 * 1024
    assert metrics["limits"] == {
        "address_bytes": 256 * 1024 * 1024,
        "cpu_seconds": 60,
        "output_bytes": 64 * 1024 * 1024,
        "open_files": 32,
    }
    shutil.rmtree(work)
    with pytest.raises(ImportFileError, match="FILE_HASH"):
        await run_parser(store, key, "xlsx", "0" * 64, check)

    async def cancel():
        raise RuntimeError("cancel-test")

    with pytest.raises(RuntimeError, match="cancel-test"):
        await run_parser(store, key, "xlsx", hashlib.sha256(raw).hexdigest(), cancel)
    assert list(store.root.glob("work-*")) == []


async def test_parser_deadline_kills_subprocess(tmp_path, settings, monkeypatch):
    store = Store(settings.model_copy(update={"import_storage_dir": tmp_path / "private"}))
    key = "b" * 32
    raw = document("xlsx", [ROW])
    store.path(key).write_bytes(raw)
    monkeypatch.setattr("app.imports.runner.PARSER_SECONDS", 0.0001)

    async def check():
        pass

    with pytest.raises(ImportFileError, match="PARSER_LIMIT"):
        await run_parser(store, key, "xlsx", hashlib.sha256(raw).hexdigest(), check)
    assert not list(store.root.glob("work-*"))


def test_xlsx_duplicate_zip_entries_rejected(tmp_path):
    out = io.BytesIO(document("xlsx", [ROW]))
    with pytest.warns(UserWarning), zipfile.ZipFile(out, "a") as archive:
        archive.writestr("xl/workbook.xml", b"<test/>")
    with pytest.raises(ImportFileError, match="UNSAFE_PACKAGE"):
        read(tmp_path, out.getvalue())


@pytest.mark.parametrize(
    "path", ["/app/uploads", "/var/www/imports", "/usr/share/nginx/html/imports"]
)
def test_storage_never_uses_runtime_or_web_roots(settings, path):
    from app.core.errors import ApplicationError

    with pytest.raises(ApplicationError) as error:
        Store(settings.model_copy(update={"import_storage_dir": Path(path)}))
    assert error.value.code == "IMPORT_STORAGE_UNSAFE"


def test_storage_rejects_repository_tree_symlinks_and_public_permissions(tmp_path, settings):
    from app.core.errors import ApplicationError

    repo = Path(__file__).resolve().parents[2]
    with pytest.raises(ApplicationError):
        Store(
            settings.model_copy(update={"import_storage_dir": repo / "app" / "public" / "imports"})
        )
    target = tmp_path / "private"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ApplicationError):
        Store(settings.model_copy(update={"import_storage_dir": link}))
    target.chmod(0o755)
    with pytest.raises(ApplicationError):
        Store(settings.model_copy(update={"import_storage_dir": target}))
