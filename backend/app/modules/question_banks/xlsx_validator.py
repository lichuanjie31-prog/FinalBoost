import os
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath
from xml.etree import ElementTree

from fastapi import UploadFile

from ...common import fail


MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_ENTRY_BYTES = 40 * 1024 * 1024
MAX_ENTRIES = 2_000
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
UNSAFE_PARTS = ("vbaproject", "xl/embeddings/", "xl/activex/", "xl/externallinks/")


@dataclass(frozen=True)
class StagedXlsx:
    path: Path
    display_name: str
    size: int
    sha256: str


def safe_display_name(filename: str | None) -> str:
    name = PurePath((filename or "paper.xlsx").replace("\\", "/")).name
    name = "".join(ch for ch in name if ord(ch) >= 32).strip()
    if len(name) > 200:
        suffix = Path(name).suffix
        name = name[: 200 - len(suffix)] + suffix
    return name or "paper.xlsx"


def stage_upload(upload: UploadFile, temporary_dir: Path) -> StagedXlsx:
    import hashlib

    display_name = safe_display_name(upload.filename)
    if Path(display_name).suffix.lower() != ".xlsx":
        fail(415, "只支持 .xlsx 文件", 41510)
    temporary_dir.mkdir(parents=True, exist_ok=True)
    target = temporary_dir / os.urandom(16).hex()
    digest = hashlib.sha256()
    size = 0
    try:
        with target.open("xb") as output:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    fail(413, "XLSX 文件不能超过 20 MiB", 41310)
                digest.update(chunk)
                output.write(chunk)
        validate_xlsx(target)
        return StagedXlsx(target, display_name, size, digest.hexdigest())
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def _is_probably_encrypted_ole(path: Path) -> bool:
    with path.open("rb") as stream:
        data = stream.read(min(path.stat().st_size, 2 * 1024 * 1024))
    if not data.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        return False
    return (
        b"EncryptedPackage" in data
        or "EncryptedPackage".encode("utf-16le") in data
        or b"EncryptionInfo" in data
        or "EncryptionInfo".encode("utf-16le") in data
    )


def validate_xlsx(path: Path) -> None:
    if _is_probably_encrypted_ole(path):
        fail(422, "XLSX 文件已加密", 42211)
    if not zipfile.is_zipfile(path):
        with path.open("rb") as stream:
            if stream.read(4).startswith(b"PK"):
                fail(422, "XLSX 文件损坏或无法读取", 42210)
        fail(415, "文件不是真实的 XLSX", 41510)
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ENTRIES:
                fail(422, "XLSX 包含过多文件项", 42212)
            names = set()
            total = 0
            actual_total = 0
            for entry in entries:
                normalized = entry.filename.replace("\\", "/")
                pure = PurePosixPath(normalized)
                if pure.is_absolute() or ".." in pure.parts or normalized.startswith("/"):
                    fail(422, "XLSX 包含不安全路径", 42212)
                if entry.flag_bits & 0x1:
                    fail(422, "XLSX 文件已加密", 42211)
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    fail(422, "XLSX 包含不安全链接", 42212)
                if entry.file_size > MAX_ENTRY_BYTES:
                    fail(422, "XLSX 解压内容过大", 42212)
                total += entry.file_size
                if total > MAX_UNCOMPRESSED_BYTES:
                    fail(422, "XLSX 解压内容过大", 42212)
                if entry.compress_size and entry.file_size / entry.compress_size > 300:
                    fail(422, "XLSX 压缩比例异常", 42212)
                lowered = normalized.lower()
                if any(part in lowered for part in UNSAFE_PARTS):
                    fail(422, "XLSX 包含宏、外部链接或嵌入对象", 42212)
                if normalized in names:
                    fail(422, "XLSX 包含重复文件项", 42212)
                names.add(normalized)
                with archive.open(entry) as stream:
                    while True:
                        chunk = stream.read(1024 * 1024)
                        if not chunk:
                            break
                        actual_total += len(chunk)
                        if actual_total > MAX_UNCOMPRESSED_BYTES:
                            fail(422, "XLSX 解压内容过大", 42212)

            required = {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml"}
            if not required <= names:
                fail(422, "XLSX 文件损坏或缺少核心结构", 42210)
            worksheet_parts = [name for name in names if name.lower().startswith("xl/worksheets/") and name.lower().endswith(".xml")]
            if not worksheet_parts:
                fail(422, "XLSX 不包含工作表", 42213)

            def read_limited(name):
                with archive.open(name) as stream:
                    data = stream.read(MAX_ENTRY_BYTES + 1)
                if len(data) > MAX_ENTRY_BYTES:
                    fail(422, "XLSX 解压内容过大", 42212)
                return data

            content_types = read_limited("[Content_Types].xml")
            if b"macroEnabled" in content_types or b"vbaProject" in content_types:
                fail(422, "XLSX 包含宏或不安全结构", 42212)
            workbook = read_limited("xl/workbook.xml")
            if b"<!DOCTYPE" in workbook.upper() or b"<!ENTITY" in workbook.upper():
                fail(422, "XLSX 包含不安全 XML", 42212)
            root = ElementTree.fromstring(workbook)
            sheets = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "sheet"]
            if not sheets:
                fail(422, "XLSX 不包含工作表", 42213)
            for entry in entries:
                if entry.filename.lower().endswith(".rels"):
                    relationships = read_limited(entry)
                    lowered_relationships = relationships.lower()
                    if b'targetmode="external"' in lowered_relationships or b"targetmode='external'" in lowered_relationships:
                        fail(422, "XLSX 包含外部链接", 42212)
    except (zipfile.BadZipFile, zipfile.LargeZipFile):
        fail(422, "XLSX 文件损坏或无法读取", 42210)
    except ElementTree.ParseError:
        fail(422, "XLSX 文件损坏或无法读取", 42210)
    except (KeyError, OSError, EOFError, ValueError, RuntimeError, NotImplementedError):
        fail(422, "XLSX 文件损坏或无法读取", 42210)
