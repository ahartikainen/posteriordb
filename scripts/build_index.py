from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
DATA_DIR = DOCS_DIR / "data"

MODELS_INFO_DIR = ROOT / "posterior_database" / "models" / "info"
POSTERIORS_DIR = ROOT / "posterior_database" / "posteriors"
DATA_INFO_DIR = ROOT / "posterior_database" / "data" / "info"
REFERENCE_DRAWS_INFO_DIR = ROOT / "posterior_database" / "reference_posteriors" / "draws" / "info"
REFERENCES_BIB = ROOT / "posterior_database" / "references" / "references.bib"

RAW_BASE = "https://raw.githubusercontent.com/stan-dev/posteriordb/master"
BLOB_BASE = "https://github.com/stan-dev/posteriordb/blob/master"

MAX_CODE_PREVIEW_CHARS = 5000


def reset_output_dir() -> None:
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    for subdir in ["models", "posteriors", "data", "reference_draws", "references"]:
        (DATA_DIR / subdir).mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_read_text(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def truncate_code(text: str, max_chars: int = MAX_CODE_PREVIEW_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n... [truncated preview]"


def rel_posix(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def blob_url(rel_path: str | None) -> str | None:
    return f"{BLOB_BASE}/{rel_path}" if rel_path else None


def raw_url(rel_path: str | None) -> str | None:
    return f"{RAW_BASE}/{rel_path}" if rel_path else None


def normalize_keywords(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x) for x in value if x is not None]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def prefer_implementation_names() -> list[str]:
    return ["stan", "pymc", "cmdstan", "cmdstanr", "cmdstanpy"]


def pick_preferred_impl_name(implementations: dict[str, Any]) -> str | None:
    for preferred in prefer_implementation_names():
        if preferred in implementations and isinstance(implementations[preferred], dict):
            return preferred
    for name, value in implementations.items():
        if isinstance(value, dict):
            return name
    return None


def ensure_rel_path_under_posterior_database(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lstrip("/")
    if value.startswith("posterior_database/"):
        return value
    return f"posterior_database/{value}"


def ensure_zip_suffix_for_data_file(rel_path: str | None) -> str | None:
    if not rel_path:
        return None
    # data/data files are stored as .json.zip in posteriordb
    if rel_path.startswith("posterior_database/data/data/") and not rel_path.endswith(".zip"):
        return f"{rel_path}.zip"
    return rel_path


def summarize_data_section(data_section: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "has_data": False,
        "name": None,
        "path": None,
        "notes": [],
    }

    if isinstance(data_section, dict):
        summary["has_data"] = True
        summary["name"] = data_section.get("name")
        rel = (
            data_section.get("path")
            or data_section.get("file")
            or data_section.get("data_file")
        )
        rel = ensure_rel_path_under_posterior_database(rel)
        rel = ensure_zip_suffix_for_data_file(rel)
        summary["path"] = rel

        for key in ("description", "source", "url", "urls", "license", "licence"):
            value = data_section.get(key)
            if value:
                summary["notes"].append(f"{key}: {value}")
    elif data_section:
        summary["has_data"] = True

    return summary


def build_model_record(info_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    info = read_json(info_path)
    model_id = info_path.name.replace(".info.json", "")
    info_rel = rel_posix(info_path)

    implementations = info.get("model_implementations")
    if not isinstance(implementations, dict):
        # Backward-compatible fallback for docs that mention model_code
        implementations = info.get("model_code", {})
        if not isinstance(implementations, dict):
            implementations = {}

    preferred_impl_name = pick_preferred_impl_name(implementations)

    impl_entries: list[dict[str, Any]] = []
    code_previews: dict[str, str] = {}

    for impl_name, impl_payload in implementations.items():
        if isinstance(impl_payload, str):
            model_code_rel = impl_payload
        elif isinstance(impl_payload, dict):
            model_code_rel = impl_payload.get("model_code")
        else:
            continue

        full_rel = ensure_rel_path_under_posterior_database(model_code_rel)
        preview_text = None

        if full_rel:
            code_text = safe_read_text(ROOT / full_rel)
            if code_text is not None:
                preview_text = truncate_code(code_text)
                code_previews[impl_name] = preview_text

        impl_entries.append(
            {
                "name": impl_name,
                "path": full_rel,
                "github": blob_url(full_rel),
                "raw": raw_url(full_rel),
            }
        )

    item_payload = {
        "id": model_id,
        "name": info.get("name", model_id),
        "title": info.get("title"),
        "description": info.get("description", ""),
        "added_by": info.get("added_by"),
        "added_date": info.get("added_date"),
        "licence": info.get("licence") or info.get("license"),
        "keywords": normalize_keywords(info.get("keywords")),
        "implementation_priority": preferred_impl_name,
        "implementations": impl_entries,
        "code_preview": code_previews.get(preferred_impl_name) if preferred_impl_name else None,
        "code_previews": code_previews,
        "data_summary": summarize_data_section(info.get("data")),
        "links": {
            "info_github": blob_url(info_rel),
            "info_raw": raw_url(info_rel),
        },
        "full_info": info,
    }

    index_entry = {
        "id": model_id,
        "name": item_payload["name"],
        "description": item_payload["description"],
        "keywords": item_payload["keywords"],
        "implementation_priority": preferred_impl_name,
        "has_data": bool(item_payload["data_summary"].get("has_data")),
        "item_json": f"./data/models/{model_id}.json",
    }

    return index_entry, item_payload


def build_posterior_record(posterior_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    info = read_json(posterior_path)
    posterior_id = posterior_path.name.replace(".json", "")
    info_rel = rel_posix(posterior_path)

    item_payload = {
        "id": posterior_id,
        "name": info.get("name", posterior_id),
        "title": info.get("title"),
        "description": info.get("description", ""),
        "model_name": info.get("model_name"),
        "data_name": info.get("data_name"),
        "reference_posterior_name": info.get("reference_posterior_name"),
        "dimension": info.get("dimension"),
        "added_by": info.get("added_by"),
        "added_date": info.get("added_date"),
        "keywords": normalize_keywords(info.get("keywords")),
        "references": info.get("references", []),
        "links": {
            "posterior_github": blob_url(info_rel),
            "posterior_raw": raw_url(info_rel),
        },
        "full_info": info,
    }

    index_entry = {
        "id": posterior_id,
        "name": item_payload["name"],
        "description": item_payload["description"],
        "model_name": item_payload["model_name"],
        "data_name": item_payload["data_name"],
        "reference_posterior_name": item_payload["reference_posterior_name"],
        "keywords": item_payload["keywords"],
        "item_json": f"./data/posteriors/{posterior_id}.json",
    }

    return index_entry, item_payload


def build_data_record(info_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    info = read_json(info_path)
    data_id = info_path.name.replace(".info.json", "")
    info_rel = rel_posix(info_path)

    raw_script_rel = None
    raw_candidates = [
        f"posterior_database/data/data-raw/{data_id}/{data_id}.py",
        f"posterior_database/data/data-raw/{data_id}/{data_id}.r",
    ]
    for candidate in raw_candidates:
        if (ROOT / candidate).exists():
            raw_script_rel = candidate
            break

    data_file_rel = None
    for key in ("data_file", "file", "path"):
        value = info.get(key)
        if isinstance(value, str) and value.strip():
            data_file_rel = ensure_rel_path_under_posterior_database(value.strip())
            data_file_rel = ensure_zip_suffix_for_data_file(data_file_rel)
            break

    item_payload = {
        "id": data_id,
        "name": info.get("name", data_id),
        "title": info.get("title"),
        "description": info.get("description", ""),
        "added_by": info.get("added_by"),
        "added_date": info.get("added_date"),
        "keywords": normalize_keywords(info.get("keywords")),
        "references": info.get("references", []),
        "urls": info.get("urls") or info.get("url"),
        "data_file": data_file_rel,
        "raw_script": raw_script_rel,
        "links": {
            "info_github": blob_url(info_rel),
            "info_raw": raw_url(info_rel),
            "data_file_github": blob_url(data_file_rel),
            "data_file_raw": raw_url(data_file_rel),
            "raw_script_github": blob_url(raw_script_rel),
            "raw_script_raw": raw_url(raw_script_rel),
        },
        "full_info": info,
    }

    index_entry = {
        "id": data_id,
        "name": item_payload["name"],
        "description": item_payload["description"],
        "keywords": item_payload["keywords"],
        "item_json": f"./data/data/{data_id}.json",
    }

    return index_entry, item_payload


def build_reference_draw_record(info_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    info = read_json(info_path)
    draw_id = info_path.name.replace(".info.json", "")
    info_rel = rel_posix(info_path)

    draw_file_rel = f"posterior_database/reference_posteriors/draws/{draw_id}.json.zip"

    item_payload = {
        "id": draw_id,
        "name": info.get("name", draw_id),
        "title": info.get("title"),
        "description": info.get("description", ""),
        "added_by": info.get("added_by"),
        "added_date": info.get("added_date"),
        "keywords": normalize_keywords(info.get("keywords")),
        "inference": info.get("inference"),
        "diagnostics": info.get("diagnostics"),
        "checks_made": info.get("checks_made"),
        "comments": info.get("comments"),
        "versions": info.get("versions"),
        "links": {
            "info_github": blob_url(info_rel),
            "info_raw": raw_url(info_rel),
            "draw_file_github": blob_url(draw_file_rel),
            "draw_file_raw": raw_url(draw_file_rel),
        },
        "full_info": info,
    }

    index_entry = {
        "id": draw_id,
        "name": item_payload["name"],
        "description": item_payload["description"] or item_payload["comments"] or "",
        "keywords": item_payload["keywords"],
        "item_json": f"./data/reference_draws/{draw_id}.json",
    }

    return index_entry, item_payload


def parse_bibtex_entries(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    starts = list(re.finditer(r"(?m)^@", text))
    if not starts:
        return entries

    spans: list[tuple[int, int]] = []
    for i, match in enumerate(starts):
        start = match.start()
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        spans.append((start, end))

    for start, end in spans:
        chunk = text[start:end].strip()
        header = re.match(r"@(\w+)\s*{\s*([^,]+)\s*,", chunk, flags=re.DOTALL)
        if not header:
            continue

        entry_type = header.group(1).strip()
        citation_key = header.group(2).strip()

        fields: dict[str, str] = {}
        for field_match in re.finditer(
            r"(?mis)^\s*([a-zA-Z_][a-zA-Z0-9_\-]*)\s*=\s*(.+?)(?=,\s*[a-zA-Z_][a-zA-Z0-9_\-]*\s*=|\s*}$)",
            chunk,
        ):
            key = field_match.group(1).strip().lower()
            value = field_match.group(2).strip().rstrip(",")

            if value.startswith("{") and value.endswith("}"):
                value = value[1:-1].strip()
            elif value.startswith('"') and value.endswith('"'):
                value = value[1:-1].strip()

            fields[key] = value

        entries.append(
            {
                "citation_key": citation_key,
                "entry_type": entry_type,
                "title": fields.get("title"),
                "author": fields.get("author"),
                "year": fields.get("year"),
                "journal": fields.get("journal"),
                "booktitle": fields.get("booktitle"),
                "doi": fields.get("doi"),
                "url": fields.get("url"),
                "bibtex": chunk,
                "fields": fields,
            }
        )

    return entries


def build_reference_records() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if not REFERENCES_BIB.exists():
        return []

    text = REFERENCES_BIB.read_text(encoding="utf-8", errors="replace")
    bib_rel = rel_posix(REFERENCES_BIB)
    parsed_entries = parse_bibtex_entries(text)

    results: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for entry in parsed_entries:
        ref_id = entry["citation_key"]
        item_payload = {
            "id": ref_id,
            "citation_key": entry["citation_key"],
            "title": entry.get("title"),
            "author": entry.get("author"),
            "year": entry.get("year"),
            "entry_type": entry.get("entry_type"),
            "bibtex": entry.get("bibtex"),
            "links": {
                "bib_github": blob_url(bib_rel),
                "bib_raw": raw_url(bib_rel),
                "url": entry.get("url"),
                "doi": f"https://doi.org/{entry['doi']}" if entry.get("doi") else None,
            },
            "full_info": entry,
        }

        index_entry = {
            "id": ref_id,
            "name": ref_id,
            "title": entry.get("title"),
            "description": entry.get("title") or "",
            "citation_key": entry.get("citation_key"),
            "keywords": [x for x in [entry.get("author"), entry.get("year"), entry.get("entry_type")] if x],
            "item_json": f"./data/references/{ref_id}.json",
        }

        results.append((index_entry, item_payload))

    return results


def build_section(source_dir: Path, out_dir: Path, pattern: str, builder) -> list[dict[str, Any]]:
    index_entries: list[dict[str, Any]] = []
    if not source_dir.exists():
        return index_entries

    for path in sorted(source_dir.glob(pattern)):
        index_entry, item_payload = builder(path)
        write_json(out_dir / f"{index_entry['id']}.json", item_payload)
        index_entries.append(index_entry)

    return index_entries


def main() -> None:
    reset_output_dir()

    model_index = build_section(
        MODELS_INFO_DIR,
        DATA_DIR / "models",
        "*.info.json",
        build_model_record,
    )

    posterior_index = build_section(
        POSTERIORS_DIR,
        DATA_DIR / "posteriors",
        "*.json",
        build_posterior_record,
    )

    data_index = build_section(
        DATA_INFO_DIR,
        DATA_DIR / "data",
        "*.info.json",
        build_data_record,
    )

    reference_draw_index = build_section(
        REFERENCE_DRAWS_INFO_DIR,
        DATA_DIR / "reference_draws",
        "*.info.json",
        build_reference_draw_record,
    )

    reference_index: list[dict[str, Any]] = []
    for index_entry, item_payload in build_reference_records():
        write_json(DATA_DIR / "references" / f"{index_entry['id']}.json", item_payload)
        reference_index.append(index_entry)

    site_index = {
        "models": model_index,
        "posteriors": posterior_index,
        "data": data_index,
        "reference_draws": reference_draw_index,
        "references": reference_index,
    }

    write_json(DATA_DIR / "site-index.json", site_index)
    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")

    print(
        json.dumps(
            {
                "models": len(model_index),
                "posteriors": len(posterior_index),
                "data": len(data_index),
                "reference_draws": len(reference_draw_index),
                "references": len(reference_index),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
