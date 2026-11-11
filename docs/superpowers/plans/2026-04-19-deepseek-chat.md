# DeepSeek Lesson Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a globally accessible AI chat popover that answers simulator questions by retrieving relevant lesson sections via a two-step DeepSeek call chain, with source pills that navigate to the cited lesson.

**Architecture:** A pre-built JSON index maps each lesson section to a one-sentence summary. At query time the backend makes two DeepSeek calls — one to select relevant sections from the index, one to answer using the retrieved markdown content. The frontend renders a fixed-position panel toggled from the tab bar that persists across tab switches.

**Tech Stack:** Python FastAPI, `cryptography` (Fernet), `httpx`, DeepSeek chat API (`deepseek-chat` model), vanilla JS

---

### Task 1: Add dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add cryptography and httpx**

Edit `requirements.txt` to add:

```
pandas
matplotlib
numpy
seaborn
scipy
fastapi
uvicorn
pyinstaller
cryptography
httpx
```

- [ ] **Step 2: Install**

```bash
pip install cryptography httpx
```

Expected: installs without errors.

- [ ] **Step 3: Verify imports**

```bash
python -c "from cryptography.fernet import Fernet; import httpx; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "feat: add cryptography and httpx dependencies for chat service"
```

---

### Task 2: Encryption tooling

**Files:**
- Create: `tools/encrypt_api_key.py`
- Modify: `.gitignore`
- Create: `config/deepseek_key.enc` (after running the tool — gitignored)

- [ ] **Step 1: Generate a Fernet secret key**

Run this once and copy the printed output. You will paste it into two files in the steps below — it must be identical in both.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Example output (yours will differ):
```
ZmDfcTF7_60GgEnJbHzGiulxEy3jrGW-8tQPrktFWvw=
```

Keep this value somewhere safe. If you lose it you cannot decrypt existing `.enc` files.

- [ ] **Step 2: Create tools/encrypt_api_key.py**

Replace `<YOUR_GENERATED_KEY>` with the key you just generated (as a plain string, no `b""`prefix — the file encodes it).

```python
import sys
from pathlib import Path

from cryptography.fernet import Fernet

FERNET_SECRET = b"<YOUR_GENERATED_KEY>"


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python tools/encrypt_api_key.py <deepseek-api-key>")
        sys.exit(1)
    plain = sys.argv[1].strip().encode()
    token = Fernet(FERNET_SECRET).encrypt(plain)
    out = Path(__file__).resolve().parents[1] / "config" / "deepseek_key.enc"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(token)
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Gitignore the config directory**

Add to `.gitignore`:

```
config/
```

- [ ] **Step 4: Run the tool with a placeholder key to verify it works**

```bash
python tools/encrypt_api_key.py sk-placeholder-key-for-testing
```

Expected: `Saved to <repo>/config/deepseek_key.enc`

Verify the file exists:

```bash
ls config/deepseek_key.enc
```

- [ ] **Step 5: Verify round-trip decrypt manually**

```bash
python -c "
from cryptography.fernet import Fernet
key = b'<YOUR_GENERATED_KEY>'
enc = open('config/deepseek_key.enc', 'rb').read()
print(Fernet(key).decrypt(enc).decode())
"
```

Expected: `sk-placeholder-key-for-testing`

- [ ] **Step 6: Commit the tool (not the key file)**

```bash
git add tools/encrypt_api_key.py .gitignore
git commit -m "feat: add API key encryption tool and gitignore config dir"
```

---

### Task 3: Build lesson index

**Files:**
- Create: `tools/build_lesson_index.py`
- Create: `docs/lessons/index.json` (after running the tool)

- [ ] **Step 1: Create tools/build_lesson_index.py**

```python
import json
import re
import sys
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

    for line in text.splitlines():
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


def summarize(section: dict, api_key: str) -> str:
    prompt = (
        "Summarize this section from a Formula Student lap time simulator knowledge base "
        "in one sentence. Be specific about what the section covers. "
        "Do not start with 'This section'.\n\n"
        f"Section: {section['section']}\n\n{section['content'][:1500]}"
    )
    resp = httpx.post(
        DEEPSEEK_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": DEEPSEEK_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 80,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python tools/build_lesson_index.py <deepseek-api-key>")
        sys.exit(1)
    api_key = sys.argv[1]

    entries = []
    for md_file in sorted(LESSONS_DIR.glob("*.md")):
        if md_file.name in SKIP_FILES:
            continue
        print(f"Processing {md_file.name}...")
        for sec in split_sections(md_file.read_text(encoding="utf-8"), md_file.name):
            print(f"  -> {sec['section']}")
            summary = summarize(sec, api_key)
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
```

- [ ] **Step 2: Run the tool with your real DeepSeek API key**

```bash
python tools/build_lesson_index.py sk-your-real-deepseek-key
```

Expected output (example):
```
Processing Aero-Model.md...
  -> Aerodynamics Model Intro
  -> ...
Done. 52 sections -> docs/lessons/index.json
```

- [ ] **Step 3: Inspect the output**

```bash
python -c "import json; d=json.load(open('docs/lessons/index.json')); print(len(d), 'sections'); print(json.dumps(d[0], indent=2))"
```

Expected: at least 30 sections, each with `file`, `section`, `summary`, `heading_level`.

- [ ] **Step 4: Commit both the tool and the index**

```bash
git add tools/build_lesson_index.py docs/lessons/index.json
git commit -m "feat: add lesson index build tool and generated section index"
```

---

### Task 4: Chat service backend

**Files:**
- Create: `tests/test_chat_service.py`
- Create: `src/app/services/chat_service.py`
- Modify: `src/app/schemas.py`
- Modify: `src/app/web.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_chat_service.py`:

```python
import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.services.chat_service import FERNET_SECRET, _decrypt_key, _load_index, _load_section_content


def test_decrypt_key_roundtrip(tmp_path):
    enc_path = tmp_path / "test.enc"
    enc_path.write_bytes(Fernet(FERNET_SECRET).encrypt(b"sk-test-key-abc"))
    assert _decrypt_key(enc_path) == "sk-test-key-abc"


def test_load_index_returns_required_fields(tmp_path):
    index = [{"file": "Tyre-Model.md", "section": "Where base_mu fits", "summary": "A summary.", "heading_level": 2}]
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    result = _load_index(index_path)
    assert isinstance(result, list)
    assert result[0]["file"] == "Tyre-Model.md"
    assert result[0]["section"] == "Where base_mu fits"


def test_load_section_content_returns_nonempty_text():
    content = _load_section_content("Tyre-Model.md", "Where base_mu fits")
    assert "base_mu" in content
    assert len(content) > 20
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_chat_service.py -v
```

Expected: 3 errors — `ImportError: cannot import name 'FERNET_SECRET'`

- [ ] **Step 3: Create src/app/services/chat_service.py**

Replace `<YOUR_GENERATED_KEY>` with the same key you used in `tools/encrypt_api_key.py`.

```python
import json
import re
from pathlib import Path

import httpx
from cryptography.fernet import Fernet

from app.paths import repo_root

FERNET_SECRET = b"<YOUR_GENERATED_KEY>"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"


def _key_path() -> Path:
    return repo_root() / "config" / "deepseek_key.enc"


def _index_path() -> Path:
    return repo_root() / "docs" / "lessons" / "index.json"


def _lessons_dir() -> Path:
    return repo_root() / "docs" / "lessons"


def _decrypt_key(key_path: Path | None = None) -> str:
    path = key_path or _key_path()
    return Fernet(FERNET_SECRET).decrypt(path.read_bytes()).decode()


def _load_index(index_path: Path | None = None) -> list[dict]:
    path = index_path or _index_path()
    return json.loads(path.read_text(encoding="utf-8"))


def _load_section_content(file: str, section: str) -> str:
    md = (_lessons_dir() / file).read_text(encoding="utf-8")
    in_section = False
    buf: list[str] = []
    for line in md.splitlines():
        m = re.match(r'^#{1,3}\s+(.+)', line)
        if m:
            if in_section:
                break
            if m.group(1).strip() == section:
                in_section = True
        elif in_section:
            buf.append(line)
    return "\n".join(buf).strip()


def _call_deepseek(messages: list[dict], api_key: str, max_tokens: int = 600) -> str:
    resp = httpx.post(
        DEEPSEEK_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": DEEPSEEK_MODEL, "messages": messages, "max_tokens": max_tokens},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def chat(question: str, history: list[dict]) -> dict:
    api_key = _decrypt_key()
    index = _load_index()

    index_lines = "\n".join(
        f'- "{e["file"]} > {e["section"]}": {e["summary"]}' for e in index
    )
    retrieval_prompt = (
        "You are a retrieval filter for a Formula Student lap time simulator knowledge base.\n"
        "Given the user question and the list of available sections, return a JSON array of "
        "section identifiers in the format \"filename > section name\" that are relevant.\n"
        "Return only the JSON array, nothing else.\n\n"
        f"Sections:\n{index_lines}\n\nQuestion: {question}"
    )
    raw = _call_deepseek(
        [{"role": "user", "content": retrieval_prompt}], api_key, max_tokens=300
    )

    try:
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        selected = json.loads(cleaned)
        if not isinstance(selected, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        selected = [f"{e['file']} > {e['section']}" for e in index]

    index_map = {f"{e['file']} > {e['section']}": e for e in index}
    matched = [index_map[k] for k in selected if k in index_map]
    if not matched:
        matched = index[:6]

    context = "\n\n---\n\n".join(
        f"## {e['file']} > {e['section']}\n{_load_section_content(e['file'], e['section'])}"
        for e in matched
    )
    system = (
        "You are a tutor for a Formula Student lap time simulator. "
        "Use the reference notes below as your primary source of truth. "
        "Reason beyond the notes when needed but say so explicitly. "
        "Be concise and precise. Do not use em dashes or semicolons.\n\n"
        f"Reference notes:\n\n{context}"
    )
    messages = [
        {"role": "system", "content": system},
        *history,
        {"role": "user", "content": question},
    ]
    answer = _call_deepseek(messages, api_key, max_tokens=600)

    return {
        "answer": answer,
        "sources": [{"file": e["file"], "section": e["section"]} for e in matched],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_chat_service.py -v
```

Expected:
```
tests/test_chat_service.py::test_decrypt_key_roundtrip PASSED
tests/test_chat_service.py::test_load_index_returns_required_fields PASSED
tests/test_chat_service.py::test_load_section_content_returns_nonempty_text PASSED
3 passed
```

- [ ] **Step 5: Add schemas to src/app/schemas.py**

```python
from typing import Any

from pydantic import BaseModel, Field


class LapRunRequest(BaseModel):
    parameter_overrides: dict[str, Any] = Field(default_factory=dict)
    track_file_path: str | None = None


class LiftCoastRequest(BaseModel):
    power_limits_kw: list[float] = Field(default_factory=lambda: [10, 20, 30, 40, 50])
    energy_target_kwh: float = 0.5
    dt: float = 0.05
    parameter_overrides: dict[str, Any] = Field(default_factory=dict)


class ChatSource(BaseModel):
    file: str
    section: str


class ChatRequest(BaseModel):
    question: str
    history: list[dict] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]
```

- [ ] **Step 6: Add the chat endpoint to src/app/web.py**

```python
from pathlib import Path

from cryptography.fernet import InvalidToken
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.schemas import LapRunRequest, LiftCoastRequest, ChatRequest
from app.services.lap_service import metadata, run_lap
from app.services.lift_coast_service import run_lift_coast
from app.services.chat_service import chat


def create_app() -> FastAPI:
    app = FastAPI(title="LGR Sim Workbench", version="0.1.0")

    static_root = Path(__file__).resolve().parent / "static"
    lessons_root = Path(__file__).resolve().parents[2] / "docs" / "lessons"
    app.mount("/static", StaticFiles(directory=str(static_root)), name="static")
    app.mount("/lessons", StaticFiles(directory=str(lessons_root)), name="lessons")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_root / "index.html")

    workspace_root = Path(__file__).resolve().parents[2]

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/workspace")
    def get_workspace() -> dict:
        return {"root": str(workspace_root).replace("\\", "/")}

    @app.get("/api/metadata")
    def get_metadata() -> dict:
        return metadata()

    @app.post("/api/lap/run")
    def run_lap_endpoint(req: LapRunRequest) -> dict:
        return run_lap(parameter_overrides=req.parameter_overrides, track_file_path=req.track_file_path)

    @app.post("/api/lift-coast/run")
    def run_lift_coast_endpoint(req: LiftCoastRequest) -> dict:
        return run_lift_coast(
            power_limits_kw=req.power_limits_kw,
            energy_target_kwh=req.energy_target_kwh,
            dt=req.dt,
            parameter_overrides=req.parameter_overrides,
        )

    @app.post("/api/chat")
    def chat_endpoint(req: ChatRequest) -> dict:
        try:
            return chat(question=req.question, history=req.history)
        except (FileNotFoundError, InvalidToken):
            raise HTTPException(status_code=503, detail="Chat is not configured.")

    return app
```

- [ ] **Step 7: Smoke test the endpoint**

Start the server:

```bash
powershell.exe -File tools/app/launch_sim_bt.ps1
```

Then in another terminal, replace the key first with a real one:

```bash
python tools/encrypt_api_key.py sk-your-real-deepseek-key
```

Test the endpoint (adjust port as needed):

```bash
curl -s -X POST http://127.0.0.1:3001/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"What is base_mu?\", \"history\": []}" | python -m json.tool
```

Expected: JSON with `answer` (non-empty string) and `sources` (list of objects with `file` and `section`).

- [ ] **Step 8: Commit**

```bash
git add tests/test_chat_service.py src/app/services/chat_service.py src/app/schemas.py src/app/web.py
git commit -m "feat: add DeepSeek two-step chat service and /api/chat endpoint"
```

---

### Task 5: Frontend popover

**Files:**
- Modify: `src/app/static/index.html`
- Modify: `src/app/static/styles.css`
- Modify: `src/app/static/app.js`

- [ ] **Step 1: Add Ask button and chat panel to index.html**

Replace the existing `<nav class="tab-bar">` block and add the chat panel before `</body>`:

```html
  <nav class="tab-bar">
    <button class="tab active" data-tab="base-sim">Base Simulator</button>
    <button class="tab" data-tab="tyres">Tyres</button>
    <button class="tab" data-tab="aero">Aerodynamics</button>
    <button class="tab" data-tab="powertrain">Powertrain</button>
    <button class="tab" data-tab="energy">Energy Management</button>
    <button class="tab" data-tab="validation">Validation</button>
    <button class="tab" data-tab="lessons">Lesson Guide</button>
    <button id="askBtn" class="ask-btn">Ask</button>
  </nav>
```

Add the chat panel just before `</body>`:

```html
  <div id="chatPanel" class="chat-panel hidden">
    <div class="chat-panel-header">
      <span class="panel-label" style="margin-bottom:0">Lesson Assistant</span>
      <button id="chatClose" class="chat-close-btn">Close</button>
    </div>
    <div class="chat-messages" id="chatMessages"></div>
    <div class="chat-input-bar">
      <input type="text" id="chatQuestion" placeholder="Ask about the simulator..." />
      <button id="chatSubmit">Send</button>
    </div>
  </div>
```

- [ ] **Step 2: Add CSS for the panel to styles.css**

Append to the end of `styles.css`:

```css
/* Ask toggle button */
.ask-btn {
  margin-left: auto;
  align-self: center;
  background: transparent;
  border: 1px solid #A7AEB6;
  border-radius: 3px;
  color: #A7AEB6;
  padding: 5px 14px;
  font-family: 'Inter', sans-serif;
  font-size: 0.7rem;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}
.ask-btn.active {
  background: #006B5C;
  color: #F4F6F8;
  border-color: #006B5C;
}

/* Chat panel */
.chat-panel {
  position: fixed;
  right: 0;
  width: 380px;
  background: #FFFFFF;
  border-left: 1px solid #A7AEB6;
  display: flex;
  flex-direction: column;
  z-index: 500;
  transform: translateX(0);
  transition: transform 0.2s ease;
}
.chat-panel.hidden {
  transform: translateX(100%);
}
.chat-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid #E8ECF0;
  flex-shrink: 0;
}
.chat-close-btn {
  background: none;
  border: none;
  font-family: 'Inter', sans-serif;
  font-size: 0.65rem;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: #A7AEB6;
  cursor: pointer;
  padding: 4px 8px;
}
.chat-close-btn:hover { color: #101215; }

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.chat-msg {
  max-width: 88%;
  font-size: 0.8rem;
  line-height: 1.55;
  padding: 8px 10px;
  border: 1px solid #E8ECF0;
}
.chat-msg.user {
  align-self: flex-end;
  background: #101215;
  color: #F4F6F8;
  border-color: #101215;
}
.chat-msg.assistant {
  align-self: flex-start;
  background: #FFFFFF;
  color: #101215;
}
.chat-sources {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}
.chat-source-pill {
  font-family: 'Inter', sans-serif;
  font-size: 0.62rem;
  letter-spacing: 0.5px;
  color: #A7AEB6;
  background: #E8ECF0;
  border: 1px solid #A7AEB6;
  padding: 2px 7px;
  cursor: pointer;
  text-transform: uppercase;
}
.chat-source-pill:hover {
  background: #006B5C;
  color: #F4F6F8;
  border-color: #006B5C;
}
.chat-input-bar {
  display: flex;
  gap: 6px;
  padding: 10px 12px;
  border-top: 1px solid #E8ECF0;
  flex-shrink: 0;
}
.chat-input-bar input[type="text"] {
  flex: 1;
}
#chatSubmit {
  background: #006B5C;
  color: #F4F6F8;
  padding: 6px 12px;
  font-size: 0.7rem;
  letter-spacing: 1px;
}
#chatSubmit:disabled {
  background: #E8ECF0;
  color: #A7AEB6;
  cursor: not-allowed;
}
```

- [ ] **Step 3: Add chat JS to app.js**

Delete the existing `// ── Boot` section at the bottom of `app.js` (the last 6 lines) and replace the entire end of the file with the following block, which includes both the chat panel code and an updated boot section:

```js
// ── Chat Panel ───────────────────────────────────────────────────────────────

let chatHistory = [];

function positionChatPanel() {
  const tabBar = document.querySelector('.tab-bar');
  const top = tabBar.getBoundingClientRect().bottom;
  const panel = document.getElementById('chatPanel');
  panel.style.top = top + 'px';
  panel.style.height = `calc(100vh - ${top}px)`;
}

function toggleChatPanel(forceOpen) {
  const panel = document.getElementById('chatPanel');
  const btn = document.getElementById('askBtn');
  const open = forceOpen !== undefined ? forceOpen : panel.classList.contains('hidden');
  panel.classList.toggle('hidden', !open);
  btn.classList.toggle('active', open);
  if (open) document.getElementById('chatQuestion').focus();
}

function appendChatMessage(role, content, sources) {
  const thread = document.getElementById('chatMessages');
  const msg = document.createElement('div');
  msg.className = `chat-msg ${role}`;
  msg.textContent = content;

  if (sources && sources.length > 0) {
    const pillRow = document.createElement('div');
    pillRow.className = 'chat-sources';
    sources.forEach(src => {
      const pill = document.createElement('span');
      pill.className = 'chat-source-pill';
      pill.textContent = src.section;
      pill.title = src.file;
      pill.addEventListener('click', () => navigateToLesson(src.file));
      pillRow.appendChild(pill);
    });
    msg.appendChild(pillRow);
  }

  thread.appendChild(msg);
  thread.scrollTop = thread.scrollHeight;
  return msg;
}

function navigateToLesson(file) {
  toggleChatPanel(false);
  const lessonsTab = document.querySelector('.tab[data-tab="lessons"]');
  if (lessonsTab) lessonsTab.click();
  const item = document.querySelector(`.lesson-item[data-src="${file}"]`);
  if (item) item.click();
}

async function sendChatMessage() {
  const input = document.getElementById('chatQuestion');
  const btn = document.getElementById('chatSubmit');
  const question = input.value.trim();
  if (!question) return;

  input.value = '';
  input.disabled = true;
  btn.disabled = true;

  appendChatMessage('user', question);
  const loading = appendChatMessage('assistant', '...');

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history: chatHistory }),
    });

    loading.remove();

    if (res.status === 503) {
      appendChatMessage('assistant', 'Chat is not configured. Contact your distributor for a key file.');
    } else if (!res.ok) {
      appendChatMessage('assistant', 'Something went wrong. Try again.');
    } else {
      const data = await res.json();
      appendChatMessage('assistant', data.answer, data.sources);
      chatHistory.push({ role: 'user', content: question });
      chatHistory.push({ role: 'assistant', content: data.answer });
    }
  } catch {
    loading.remove();
    appendChatMessage('assistant', 'Could not reach the server. Try again.');
  } finally {
    input.disabled = false;
    btn.disabled = false;
    input.focus();
  }
}

// ── Boot ────────────────────────────────────────────────────────────────────

document.getElementById('runLapBtn').addEventListener('click', runLap);
document.getElementById('askBtn').addEventListener('click', () => toggleChatPanel());
document.getElementById('chatClose').addEventListener('click', () => toggleChatPanel(false));
document.getElementById('chatSubmit').addEventListener('click', sendChatMessage);
document.getElementById('chatQuestion').addEventListener('keydown', e => {
  if (e.key === 'Enter') sendChatMessage();
});

initTabs();
initLessons();
loadMetadata();
positionChatPanel();
```

- [ ] **Step 4: Restart the server**

```bash
powershell.exe -File tools/app/launch_sim_bt.ps1
```

- [ ] **Step 5: Test in browser**

Open the app URL. Verify:

1. "Ask" button is visible at the far right of the tab bar.
2. Clicking "Ask" slides the panel in from the right.
3. Switching tabs does not close the panel.
4. Clicking "Close" or "Ask" again slides the panel out.
5. Typing a question and pressing Enter or Send sends it.
6. A user message bubble appears right-aligned in carbon black.
7. A `...` bubble appears while the request is in flight.
8. The assistant reply appears left-aligned with source pills below it.
9. Clicking a source pill closes the panel, switches to Lesson Guide, and loads the cited lesson.

- [ ] **Step 6: Commit**

```bash
git add src/app/static/index.html src/app/static/styles.css src/app/static/app.js
git commit -m "feat: add DeepSeek chat popover with two-step retrieval and lesson navigation"
```
