#!/usr/bin/env python3
"""Build a public copy without modifying evaluation source artifacts."""

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".json", ".md", ".py", ".txt", ".html", ".log"}
EXCLUDED_PARTS = {"__pycache__"}
EXCLUDED_NAMES = {".DS_Store"}
URL_PATTERN = re.compile(r"https://doc\.weixin\.qq\.com/[^\s)>\]\"']+")
SESSION_PATTERN = re.compile(r"agent-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
SYNTHETIC_NOTICE = (
    "> 数据声明：本文件中的林舟及其经历、对话和工具环境均为虚构的合成评测数据，"
    "不对应真实个人或真实业务记录。\n\n"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sanitize(text: str, workspace: Path) -> tuple[str, dict[str, int]]:
    counts = {
        "local_path": text.count(str(workspace)),
        "enterprise_document_url": len(URL_PATTERN.findall(text)),
        "runtime_session_ref": len(SESSION_PATTERN.findall(text)),
    }
    text = text.replace(str(workspace), "<workspace>")
    text = URL_PATTERN.sub("<removed-enterprise-document-link>", text)
    text = SESSION_PATTERN.sub("<runtime-session-ref>", text)
    return text, counts


def source_files(source: Path) -> list[Path]:
    return sorted(
        path for path in source.rglob("*")
        if path.is_file()
        and path.name not in EXCLUDED_NAMES
        and not EXCLUDED_PARTS.intersection(path.relative_to(source).parts)
        and path.suffix != ".pyc"
    )


def publish(source: Path, workspace: Path, extra_files: list[Path]) -> dict:
    files = []
    totals = dict.fromkeys(("local_path", "enterprise_document_url", "runtime_session_ref"), 0)
    for path in [*source_files(source), *extra_files]:
        relative = path.relative_to(source) if path.is_relative_to(source) else Path(path.name)
        if relative == Path("README.md"):
            # The public README is maintained here; do not overwrite it
            # with the source snapshot or keep a legacy copy.
            continue
        destination = REPO_ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_hash = digest(path)
        transformed = False
        if path.suffix.lower() in TEXT_SUFFIXES:
            original_text = path.read_text(encoding="utf-8")
            text, counts = sanitize(original_text, workspace)
            if relative.as_posix() == "persona-01-linzhou/profile.md":
                text = SYNTHETIC_NOTICE + text
            transformed = text != original_text
            encoded = text.encode("utf-8")
            if not destination.exists() or destination.read_bytes() != encoded:
                destination.write_bytes(encoded)
            for key, value in counts.items():
                totals[key] += value
        elif not destination.exists() or digest(destination) != source_hash:
            destination.write_bytes(path.read_bytes())
        if relative.suffix == ".json":
            json.loads(destination.read_text(encoding="utf-8"))
        files.append({
            "path": relative.as_posix(),
            "bytes": destination.stat().st_size,
            "source_sha256": source_hash,
            "published_sha256": digest(destination),
            "publication_transformed": transformed,
        })
    return {
        "schema": "personal-agent-benchmark-publication-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "synthetic_data": True,
        "source_modified": False,
        "transforms": totals,
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--extra-file", type=Path, action="append", default=[])
    args = parser.parse_args()
    source = args.source_root.expanduser().resolve()
    workspace = args.workspace_root.expanduser().resolve()
    if not source.is_dir() or not workspace.is_dir():
        raise ValueError("Source and workspace roots must be existing directories")
    if source == REPO_ROOT or source in REPO_ROOT.parents or REPO_ROOT in source.parents:
        raise ValueError("Publication source must be outside the repository")
    extra_files = [path.expanduser().resolve() for path in args.extra_file]
    if any(not path.is_file() for path in extra_files):
        raise ValueError("Every extra file must exist")
    report = publish(source, workspace, extra_files)
    destination = REPO_ROOT / "docs" / "publication-manifest.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "files"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
