"""Create a local review archive from an explicit allowlist; never bundle credentials."""

import argparse
import hashlib
import os
import posixpath
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = (
    "src",
    "tests",
    "scripts",
    "config",
    "docs",
    "eval",
    "reports",
    "deliverables",
)
EXTENSIONS = {
    ".py",
    ".ps1",
    ".sql",
    ".css",
    ".js",
    ".md",
    ".json",
    ".jsonl",
    ".csv",
    ".txt",
    ".yml",
    ".pptx",
}
RUNS = (
    "native_import_final.json",
    "native_import_repeat.json",
    "development_lexical_20260916.json",
    "development_paid_20260916.json",
    "development_paid_quotes_20260916.json",
    "development_paid_context_20260916.json",
    "development_paid_citation_first_20260916.json",
    "live_biogas.json",
    "live_ccs_scoped.json",
    "live_no_evidence.json",
    "native_import_reviewed_20260916.json",
    "native_import_reviewed_repeat_20260916.json",
    "native_import_v0_2_20260916.json",
    "native_import_v0_2_repeat_final_20260916.json",
    "source_revision_validation_final_20260916.json",
    "development_reviewed_paid_20260916.json",
    "development_reviewed_paid_final_20260916.json",
    "development_v0_2_lexical_20260916.json",
    "native_import_v0_2_published_20260916.json",
    "native_import_v0_2_published_repeat_20260916.json",
    "source_revision_v0_2_20260916.json",
    "development_v0_2_current_lexical_20260916.json",
    "native_import_v0_2_final_20260916.json",
    "native_import_v0_2_repeat_20260916.json",
    "native_preflight_intervals_20260916.json",
    "source_revision_validation_20260916.json",
    "development_language_guard_20260916.json",
    "development_claim_contract_20260916.json",
    "pdf265_preflight_20260916.json",
    "native_import_pdf265_20260916.json",
    "native_import_pdf265_repeat_20260916.json",
    "pdf265_publication_validation_20260916.json",
    "pdf265_recovery_paid_smoke_20260916.json",
    "quote_context_corpus_20260916.json",
    "pdf265_quote_context_paid_20260916.json",
    "development_quote_context_20260916.json",
    "clean_import_source_v0_2_4_20260916.json",
    "clean_import_wheel_v0_2_4_20260916.json",
    "backup_restore_v0_2_4_20260916.json",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    files = [
        ROOT / n
        for n in (
            "pyproject.toml",
            "uv.lock",
            ".env.example",
            ".gitignore",
            ".gitattributes",
        )
    ]
    files.extend(ROOT.glob("*.md"))
    for folder in FOLDERS:
        files.extend(
            p
            for p in (ROOT / folder).rglob("*")
            if p.is_file() and p.suffix in EXTENSIONS and "__pycache__" not in p.parts
        )
    files.extend(ROOT / "outputs" / name for name in RUNS)
    entries = {}
    secret = os.environ.get("OPENAI_API_KEY", "")
    for file in sorted(set(files)):
        relative = file.relative_to(ROOT).as_posix()
        data = file.read_bytes()
        if (secret and secret.encode() in data) or re.search(
            rb"sk-(?:proj-)?[a-zA-Z0-9_-]{30,}", data
        ):
            raise RuntimeError(
                f"Credential-like content found in {relative}; archive not created"
            )
        entries[relative] = data
    # Adapt links only when their exact target is included in this archive.
    # Original workspace reports and links to private, unbundled sources stay intact.
    local_link = re.compile(r"\]\(<" + re.escape(ROOT.as_posix()) + r"/([^>]+)>\)")
    for name, data in list(entries.items()):
        if not name.endswith(".md"):
            continue

        def portable_link(match):
            target_name = match.group(1)
            if target_name not in entries:
                return match.group(0)
            relative_target = posixpath.relpath(
                target_name, posixpath.dirname(name) or "."
            )
            return f"](<{relative_target}>)"

        entries[name] = local_link.sub(portable_link, data.decode("utf-8")).encode(
            "utf-8"
        )
    entries["CONTENTS.sha256"] = (
        "\n".join(
            f"{hashlib.sha256(data).hexdigest()}  {name}"
            for name, data in entries.items()
        )
        + "\n"
    ).encode()
    target = args.output.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents an accidental overwrite of a previous handoff.
    with ZipFile(target, "x", ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    with ZipFile(target) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(entries)
        assert all(archive.read(name) == data for name, data in entries.items())
    sha = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(
        f"{sha}  {target.name}\n", encoding="utf-8"
    )
    print(
        f"Created {target.name}: {len(entries)} entries, {target.stat().st_size} bytes, SHA-256 {sha}"
    )


if __name__ == "__main__":
    main()
