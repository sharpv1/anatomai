"""Unprivileged parser child: no DB credentials, no network fetch, hard OS limits."""

import sys


def main() -> None:
    import resource

    # Set limits before loading XML/Pydantic; these work even without Docker cgroups.
    from app.imports.limits import OUTPUT_BYTES, PARSER_ADDRESS_BYTES, PARSER_SECONDS

    resource.setrlimit(resource.RLIMIT_AS, (PARSER_ADDRESS_BYTES, PARSER_ADDRESS_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (PARSER_SECONDS, PARSER_SECONDS))
    resource.setrlimit(resource.RLIMIT_FSIZE, (OUTPUT_BYTES, OUTPUT_BYTES))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    import hashlib
    import hmac
    import json
    import time
    from pathlib import Path

    from app.imports.errors import ImportFileError
    from app.imports.parser import parse

    source, output, summary, fmt, expected = sys.argv[1:]
    started = time.monotonic()
    count = 0
    code = None
    try:
        with Path(source).open("rb") as file:
            actual = hashlib.file_digest(file, "sha256").hexdigest()
        if not hmac.compare_digest(actual, expected):
            raise ImportFileError("FILE_HASH")
        with Path(output).open("x", encoding="utf-8") as target:
            for row in parse(Path(source), fmt):
                target.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                count += 1
    except ImportFileError as exc:
        code = exc.code
    except MemoryError:
        code = "PARSER_LIMIT"
    except Exception as exc:
        from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]

        code = "UNSAFE_XML" if isinstance(exc, DefusedXmlException) else "FILE_FORMAT"
    result = {
        "count": count,
        "error_code": code,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "limits": {
            "address_bytes": resource.getrlimit(resource.RLIMIT_AS)[0],
            "cpu_seconds": resource.getrlimit(resource.RLIMIT_CPU)[0],
            "output_bytes": resource.getrlimit(resource.RLIMIT_FSIZE)[0],
            "open_files": resource.getrlimit(resource.RLIMIT_NOFILE)[0],
        },
    }
    Path(summary).write_text(json.dumps(result), encoding="utf-8")
    raise SystemExit(1 if code else 0)


if __name__ == "__main__":
    main()
