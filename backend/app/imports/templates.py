"""Text-only, blank OOXML templates. No example medical content."""

import io
import zipfile
from xml.etree.ElementTree import Element, SubElement, tostring

P = "http://schemas.openxmlformats.org/package/2006/relationships"
C = "http://schemas.openxmlformats.org/package/2006/content-types"
X = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MINIMAL_HEADERS = ["Дисциплина", "Тема", "Вопрос", "Ответ A", "Ответ B", "Правильный ответ"]


def document(
    fmt: str, rows: list[list[str]] | None = None, headers: list[str] | None = None
) -> bytes:
    matrix = [headers or MINIMAL_HEADERS, *(rows or [])]
    output = io.BytesIO()
    main = "xl/workbook.xml" if fmt == "xlsx" else "word/document.xml"
    mime = "application/vnd.openxmlformats-officedocument."
    types = Element("Types", xmlns=C)
    SubElement(
        types,
        "Default",
        Extension="rels",
        ContentType="application/vnd.openxmlformats-package.relationships+xml",
    )
    SubElement(types, "Default", Extension="xml", ContentType="application/xml")
    SubElement(
        types,
        "Override",
        PartName="/" + main,
        ContentType=mime
        + (
            "spreadsheetml.sheet.main+xml"
            if fmt == "xlsx"
            else "wordprocessingml.document.main+xml"
        ),
    )
    relationships = Element("Relationships", xmlns=P)
    SubElement(relationships, "Relationship", Id="rId1", Type=R + "/officeDocument", Target=main)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("_rels/.rels", tostring(relationships))
        if fmt == "xlsx":
            SubElement(
                types,
                "Override",
                PartName="/xl/worksheets/sheet1.xml",
                ContentType=mime + "spreadsheetml.worksheet+xml",
            )
            book = Element("workbook", xmlns=X, attrib={"xmlns:r": R})
            SubElement(
                SubElement(book, "sheets"),
                "sheet",
                name="Questions",
                sheetId="1",
                attrib={"r:id": "rId1"},
            )
            archive.writestr(main, tostring(book))
            rels = Element("Relationships", xmlns=P)
            SubElement(
                rels,
                "Relationship",
                Id="rId1",
                Type=R + "/worksheet",
                Target="worksheets/sheet1.xml",
            )
            archive.writestr("xl/_rels/workbook.xml.rels", tostring(rels))
            sheet = Element("worksheet", xmlns=X)
            data = SubElement(sheet, "sheetData")
            for index, values in enumerate(matrix, 1):
                row = SubElement(data, "row", r=str(index))
                for i, value in enumerate(values):
                    cell = SubElement(row, "c", r=f"{chr(65 + i)}{index}", t="inlineStr")
                    SubElement(SubElement(cell, "is"), "t").text = str(value)
            archive.writestr("xl/worksheets/sheet1.xml", tostring(sheet))
        else:
            doc = Element("w:document", attrib={"xmlns:w": W})
            table = SubElement(SubElement(doc, "w:body"), "w:tbl")
            for values in matrix:
                row = SubElement(table, "w:tr")
                for value in values:
                    cell = SubElement(row, "w:tc")
                    SubElement(SubElement(SubElement(cell, "w:p"), "w:r"), "w:t").text = str(value)
            archive.writestr(main, tostring(doc))
        archive.writestr("[Content_Types].xml", tostring(types))
    return output.getvalue()
