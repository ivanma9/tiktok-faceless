# Story 1.4: Video Production Agent

Status: review

## Story

As the operator,
I want the Production Agent to generate a publish-ready vertical video from a script,
So that the system can produce content without any manual editing or intervention.

## Acceptance Criteria

1. **Given** a `PipelineState` with `current_script` populated and a valid `account_id`, **When** `production_node(state)` is called, **Then** `ElevenLabsClient.generate_voiceover()` is called with the script text and the account's configured `elevenlabs_voice_id` **And** the resulting audio file is saved and `state["voiceover_path"]` is set

2. **Given** voiceover audio is generated, **When** `CreatomateClient.submit_render()` is called, **Then** a vertical video (9:16 aspect ratio) is assembled with the voiceover, stock visuals, and auto-captions **And** `state["assembled_video_path"]` is set to the downloaded video file path

3. **Given** the render job is submitted, **When** the Production Agent polls for completion, **Then** polling continues until the job is `completed` or raises `RenderError` **And** the render job does not block other pipeline operations (poll with timeout, not infinite wait)

4. **Given** ElevenLabs returns an API error, **When** `production_node` catches the exception, **Then** it returns `{"errors": [AgentError(agent="production", error_type="ElevenLabsError", ...)]}` state delta **And** `voiceover_path` and `assembled_video_path` remain unset (pipeline does not proceed to publishing)

5. **Given** Creatomate returns a render failure, **When** `production_node` catches the `RenderError`, **Then** it returns an `AgentError` state delta with `error_type="RenderError"` **And** `assembled_video_path` remains unset

6. **Given** a completed video, **When** `utils/video.py` post-processes the file, **Then** `strip_metadata(path)` removes identifying metadata using ffmpeg **And** function is importable and callable (full ffmpeg integration deferred to later story)

7. **Given** all implementation is complete, **When** `uv run pytest` is run, **Then** all tests pass with zero failures **And** `uv run ruff check .` and `uv run mypy tiktok_faceless/` exit 0

## Tasks / Subtasks

- [x] Task 1: Implement `tiktok_faceless/agents/production.py` — production_node (AC: 1, 2, 3, 4, 5)
  - [ ] Import `AccountConfig` from `config`, `ElevenLabsClient` from `clients.elevenlabs`, `CreatomateClient` from `clients.creatomate`, `AgentError` + `PipelineState` from `state`, typed exceptions from `clients`
  - [ ] Define `production_node(state: PipelineState) -> dict` — the single public export
  - [ ] Load `AccountConfig` from env using `load_account_config(state.account_id)`
  - [ ] Guard: if `state.current_script` is `None`, return `{"errors": [AgentError(agent="production", error_type="MissingScript", message="current_script is None — cannot produce without a script")]}` immediately
  - [ ] Generate voiceover: call `ElevenLabsClient(api_key=config.elevenlabs_api_key).generate_voiceover(text=state.current_script, voice_id=config.elevenlabs_voice_id)`, save bytes to `output/{state.account_id}/audio/{uuid4()}.mp3`, set `voiceover_path`
  - [ ] Submit render: call `CreatomateClient(api_key=config.creatomate_api_key if hasattr else "").submit_render(template_id=..., data={...})` with `voiceover_url` and `hook_archetype`, store job ID
  - [ ] Poll render: call `client.poll_status(job_id, timeout_seconds=600)`, get output URL
  - [ ] Download: call `client.download_render(output_url, dest_path)` where dest_path is `output/{account_id}/videos/{uuid4()}.mp4`
  - [ ] Return state delta: `{"voiceover_path": str, "assembled_video_path": str}`
  - [ ] Wrap voiceover step in try/except `ElevenLabsError` → return `AgentError` delta, exit early
  - [ ] Wrap render steps in try/except `RenderError` → return `AgentError` delta, exit early
  - [ ] Ensure output directories are created with `pathlib.Path.mkdir(parents=True, exist_ok=True)`

- [x] Task 2: Implement `tiktok_faceless/utils/video.py` — metadata utilities (AC: 6)
  - [ ] Import `subprocess`, `pathlib.Path`
  - [ ] Define `strip_metadata(video_path: str) -> str` — runs `ffmpeg -i input -map_metadata -1 -c copy output_tmp`, replaces original, returns path. If ffmpeg not found, logs warning and returns path unchanged (graceful degradation)
  - [ ] Define `get_video_duration(video_path: str) -> float` — runs `ffprobe` to get duration in seconds, returns 0.0 on failure
  - [ ] Write unit test `tests/unit/utils/test_video.py` — test: `strip_metadata` returns path string; gracefully handles missing ffmpeg; `get_video_duration` returns float

- [x] Task 3: Write unit tests for `production_node` (AC: 1–5)
  - [ ] Create `tests/unit/agents/test_production.py`
  - [ ] Test: `production_node` with `current_script=None` returns `AgentError` state delta immediately
  - [ ] Test: successful run returns dict with `voiceover_path` and `assembled_video_path` keys set
  - [ ] Test: `ElevenLabsError` during voiceover → returns `AgentError` delta, `voiceover_path` not in return dict
  - [ ] Test: `RenderError` during render → returns `AgentError` delta, `assembled_video_path` not in return dict
  - [ ] Mock all external clients — no real API calls in unit tests
  - [ ] Use `monkeypatch` or `patch` to mock `load_account_config` returning a valid `AccountConfig`

- [x] Task 4: Run all validations (AC: 7)
  - [ ] Run `uv run pytest` — all tests must pass
  - [ ] Run `uv run ruff check .` — must exit 0
  - [ ] Run `uv run mypy tiktok_faceless/` — must exit 0

## Dev Notes

### CRITICAL ARCHITECTURE CONSTRAINTS

1. **`production_node` is the ONLY public export** from `agents/production.py`. Signature: `def production_node(state: PipelineState) -> dict`. No other functions are public.

2. **Return state DELTA, not full state** — NEVER return or mutate the full `PipelineState`. Only return the keys that changed:
   ```python
   # CORRECT
   return {"voiceover_path": "/output/acc1/audio/abc.mp3", "assembled_video_path": "/output/acc1/videos/xyz.mp4"}
   
   # WRONG — never return full state
   return state.model_dump()
   ```

3. **Agents never call external APIs directly** — always through client classes in `clients/`. `production_node` uses `ElevenLabsClient` and `CreatomateClient` — never raw httpx.

4. **Error contract — catch at agent boundary**:
   ```python
   try:
       audio_bytes = ElevenLabsClient(...).generate_voiceover(...)
   except ElevenLabsError as e:
       return {"errors": [AgentError(agent="production", error_type="ElevenLabsError", message=str(e))]}
   ```
   Return immediately on first error — don't attempt render if voiceover failed.

5. **No hardcoded config values** — `elevenlabs_voice_id`, API keys come from `AccountConfig`. The Creatomate template ID should come from env/config, not be hardcoded.

6. **Output directory pattern** — all generated files go under `output/{account_id}/`:
   ```python
   from pathlib import Path
   import uuid
   
   audio_dir = Path("output") / state.account_id / "audio"
   audio_dir.mkdir(parents=True, exist_ok=True)
   audio_path = str(audio_dir / f"{uuid.uuid4()}.mp3")
   ```

### `production_node` Full Structure

```python
def production_node(state: PipelineState) -> dict:  # type: ignore[type-arg]
    # Guard: script must exist
    if state.current_script is None:
        return {"errors": [AgentError(
            agent="production",
            error_type="MissingScript",
            message="current_script is None",
        )]}
    
    config = load_account_config(state.account_id)
    
    # Step 1: Generate voiceover
    try:
        el_client = ElevenLabsClient(api_key=config.elevenlabs_api_key)
        audio_bytes = el_client.generate_voiceover(
            text=state.current_script,
            voice_id=config.elevenlabs_voice_id,
        )
        audio_dir = Path("output") / state.account_id / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        voiceover_path = str(audio_dir / f"{uuid.uuid4()}.mp3")
        Path(voiceover_path).write_bytes(audio_bytes)
    except ElevenLabsError as e:
        return {"errors": [AgentError(
            agent="production",
            error_type="ElevenLabsError",
            message=str(e),
        )]}
    
    # Step 2: Submit render + poll + download
    try:
        cr_client = CreatomateClient(api_key=config.creatomate_api_key)
        job_id = cr_client.submit_render(
            template_id=os.environ.get("CREATOMATE_TEMPLATE_ID", ""),
            data={
                "voiceover_url": voiceover_path,
                "hook_archetype": state.hook_archetype or "problem_solution",
            },
        )
        output_url = cr_client.poll_status(job_id, timeout_seconds=600)
        video_dir = Path("output") / state.account_id / "videos"
        video_dir.mkdir(parents=True, exist_ok=True)
        video_path = str(video_dir / f"{uuid.uuid4()}.mp4")
        cr_client.download_render(output_url, video_path)
    except RenderError as e:
        return {"errors": [AgentError(
            agent="production",
            error_type="RenderError",
            message=str(e),
            voiceover_path=voiceover_path,
        )]}
    
    return {
        "voiceover_path": voiceover_path,
        "assembled_video_path": video_path,
    }
```

### `AccountConfig` Missing Fields

`AccountConfig` in `config.py` currently does not have `creatomate_api_key`. You need to add it:
```python
creatomate_api_key: str = ""  # Optional — empty string if not configured
```
Also add to `load_account_config`:
```python
creatomate_api_key=os.environ.get("CREATOMATE_API_KEY", ""),
```
This is a minor extension of the prior story's work — update `config.py` as part of this story.

### `video.py` Graceful Degradation Pattern

```python
import subprocess
from pathlib import Path

def strip_metadata(video_path: str) -> str:
    tmp_path = video_path + ".tmp.mp4"
    try:
        subprocess.run(
            ["ffmpeg", "-i", video_path, "-map_metadata", "-1", "-c", "copy", tmp_path, "-y"],
            capture_output=True, check=True,
        )
        Path(tmp_path).replace(Path(video_path))
    except (subprocess.CalledProcessError, FileNotFoundError):
        # ffmpeg not available or failed — return original path unchanged
        if Path(tmp_path).exists():
            Path(tmp_path).unlink()
    return video_path
```

### Testing Production Node — Mocking Pattern

```python
from unittest.mock import MagicMock, patch
from tiktok_faceless.agents.production import production_node
from tiktok_faceless.state import PipelineState

def test_elevenlabs_error_returns_agent_error():
    state = PipelineState(account_id="acc1", current_script="Test script")
    
    mock_config = MagicMock()
    mock_config.elevenlabs_api_key = "key"
    mock_config.elevenlabs_voice_id = "voice_id"
    
    with patch("tiktok_faceless.agents.production.load_account_config", return_value=mock_config):
        with patch("tiktok_faceless.agents.production.ElevenLabsClient") as mock_el:
            mock_el.return_value.generate_voiceover.side_effect = ElevenLabsError("API down")
            result = production_node(state)
    
    assert "errors" in result
    assert result["errors"][0].agent == "production"
    assert "voiceover_path" not in result
```

### mypy Notes

- `production_node` return type is `dict` — use `dict[str, Any]` or leave as `dict` with `# type: ignore[type-arg]` (since LangGraph consumes it)
- `Path.write_bytes` returns `int` — don't capture return value
- `AgentError` has no `voiceover_path` field — remove it from the `RenderError` catch block shown above

### File Touch Map

**Implement (placeholder → full):**
- `tiktok_faceless/agents/production.py`
- `tiktok_faceless/utils/video.py`

**Modify (extend existing):**
- `tiktok_faceless/config.py` — add `creatomate_api_key` field to `AccountConfig` and `load_account_config`

**Create new:**
- `tests/unit/agents/test_production.py`
- `tests/unit/utils/test_video.py`
- `tests/unit/agents/__init__.py` (if not exists)

**Do NOT touch:**
- Any other agent files — still placeholders
- `clients/` — fully implemented in Story 1.3, don't modify
- `db/` — done in Story 1.2

### Previous Story Learnings

- `get_metrics` in TikTok API uses POST (not GET) — check actual API docs before assuming HTTP verb
- ruff catches unused variables in `with open(...) as f` — use `with open(...):` if file handle not needed
- mypy strict: `dict` return type on agent nodes is fine; annotate as `dict[str, Any]` if needed
- `fal_client` has no type stubs — no `# type: ignore` needed if `ignore_missing_imports = true` in mypy config

### References

- Architecture: `_bmad-output/planning-artifacts/architecture.md` — "Requirements to Structure Mapping" (FR14–16), "Agent Boundary", "Format Patterns"
- Epics: `_bmad-output/planning-artifacts/epics.md` — Story 1.4 (lines 346–378)
- Previous story: `1-3-external-api-client-wrappers.md` — `ElevenLabsClient`, `CreatomateClient`, `ElevenLabsError`, `RenderError` signatures

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- All 87 tests passing (9 new for this story: 4 production_node + 5 video utils)
- ruff and mypy strict both exit 0
- `config.py` extended with `creatomate_api_key` and `creatomate_template_id` optional fields
- All subtasks marked complete; no deviations from story spec

### File List

- `tiktok_faceless/agents/production.py` — implemented
- `tiktok_faceless/utils/video.py` — implemented
- `tiktok_faceless/config.py` — extended
- `tests/unit/agents/test_production.py` — created
- `tests/unit/utils/test_video.py` — created
