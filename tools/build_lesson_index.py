import json
import re
import sys
import time
from pathlib import Path

import httpx

LESSONS_DIR = Path(__file__).resolve().parents[1] / "docs" / "lessons"
OUT_PATH = LESSONS_DIR / "index.json"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
SKIP_FILES = {"README.md"}


def split_sections(text: str, filename: str) -> list[dict]:
    sections = []
    heading = None
    level = 0
    buf: list[str] = []
    in_fence = False

    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if in_fence:
            buf.append(line)
            continue
        m = re.match(r'^(#{1,3})\s+(.+)', line)
        if m:
            if heading:
                sections.append({
                    "file": filename,
                    "section": heading,
                    "heading_level": level,
                    "content": "\n".join(buf).strip(),
                })
            heading = m.group(2).strip()
            level = len(m.group(1))
            buf = []
        else:
            buf.append(line)

    if heading:
        sections.append({
            "file": filename,
            "section": heading,
            "heading_level": level,
            "content": "\n".join(buf).strip(),
        })

    return [s for s in sections if s["content"]]


def local_summary(section: dict) -> str:
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', section["content"])
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'[`*_#>$]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return f"Covers {section['section']}."
    return text[:280].rstrip()


def summarize(section: dict, api_key: str) -> str:
    prompt = (
        "Summarize this section from a Formula Student lap time simulator knowledge base "
        "in one sentence. Be specific about what the section covers. "
        "Do not start with 'This section'.\n\n"
        f"Section: {section['section']}\n\n{section['content'][:1500]}"
    )
    last_exc = None
    for attempt in range(4):
        try:
            resp = httpx.post(
                DEEPSEEK_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": DEEPSEEK_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 80,
                },
                timeout=45,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt == 3:
                break
            time.sleep(2 ** attempt)
    raise last_exc


def main() -> None:
    args = sys.argv[1:]
    resume = "--resume" in args
    use_local = "--local" in args
    use_key_file = "--key-file" in args
    args = [a for a in args if a != "--resume"]
    args = [a for a in args if a != "--local"]
    args = [a for a in args if a != "--key-file"]
    if use_local:
        api_key = ""
    elif use_key_file:
        if args:
            print("Usage: python tools/build_lesson_index.py [--resume] [--local] --key-file")
            sys.exit(1)
        key_path = Path(__file__).resolve().parents[1] / "config" / "deepseek_key"
        api_key = key_path.read_text(encoding="utf-8").strip()
    elif len(args) == 1:
        api_key = args[0]
    else:
        print("Usage: python tools/build_lesson_index.py [--resume] [--local] (--key-file | <deepseek-api-key>)")
        sys.exit(1)

    already_indexed: set[tuple[str, str]] = set()
    entries: list[dict] = []
    if resume and OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        entries = existing
        already_indexed = {(e["file"], e["section"]) for e in existing}
        print(f"Resuming from existing index ({len(entries)} sections already indexed).")

    for md_file in sorted(LESSONS_DIR.glob("*.md")):
        if md_file.name in SKIP_FILES:
            continue
        print(f"Processing {md_file.name}...")
        for sec in split_sections(md_file.read_text(encoding="utf-8"), md_file.name):
            if (sec["file"], sec["section"]) in already_indexed:
                print(f"  -> {sec['section']} (skipped)")
                continue
            print(f"  -> {sec['section']}")
            if use_local:
                summary = local_summary(sec)
            else:
                try:
                    summary = summarize(sec, api_key)
                except httpx.HTTPError as exc:
                    OUT_PATH.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
                    print(f"\nAborted after {len(entries)} sections. Partial index saved to {OUT_PATH}")
                    raise SystemExit(1) from exc
            entries.append({
                "file": sec["file"],
                "section": sec["section"],
                "summary": summary,
                "heading_level": sec["heading_level"],
            })

    OUT_PATH.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDone. {len(entries)} sections -> {OUT_PATH}")


if __name__ == "__main__":
    main()
