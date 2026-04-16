"""
Steins Gate API — FastAPI endpoints for Amadeus portfolio queries.
Implements the Steins Gate API Contract v0.2.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

app = FastAPI(title="Steins Gate", version="0.2.0", description="Read/query layer for Amadeus workspace")

WORKSPACE = Path(os.environ.get("AMADEUS_WORKSPACE", "./workspace"))
LOGS_DIR = Path(os.environ.get("AMADEUS_LOGS", "./logs"))

TYPE_DIRS = {
    "architecture": "architecture",
    "debug": "debug",
    "boilerplate": "boilerplate",
    "snippet": "snippets",
}

AGENT_MAP = {
    "architecture": "claude",
    "debug": "claude",
    "boilerplate": "codex",
    "snippet": "codex",
}


# ── Models ──────────────────────────────────────────────


class Artifact(BaseModel):
    id: str
    type: str
    agent: str
    slug: str
    path: str
    created_at: datetime
    size_bytes: int


class ArtifactDetail(Artifact):
    content: str


class ArtifactListResponse(BaseModel):
    count: int
    total: int
    artifacts: list[Artifact]


class SearchHit(BaseModel):
    line: int
    text: str
    context_before: list[str]
    context_after: list[str]


class SearchMatch(BaseModel):
    id: str
    type: str
    agent: str
    path: str
    hits: list[SearchHit]


class SearchResponse(BaseModel):
    pattern: str
    total_hits: int
    files_matched: int
    matches: list[SearchMatch]


class LogEntry(BaseModel):
    timestamp: str
    level: str
    message: str
    run_id: str
    source: str


class LogResponse(BaseModel):
    count: int
    entries: list[LogEntry]


class TypeStats(BaseModel):
    architecture: int = 0
    debug: int = 0
    boilerplate: int = 0
    snippet: int = 0


class AgentStats(BaseModel):
    claude: int = 0
    codex: int = 0


class StatsResponse(BaseModel):
    total: int
    total_size_bytes: int
    by_type: TypeStats
    by_agent: AgentStats
    oldest: Optional[datetime] = None
    newest: Optional[datetime] = None
    error_count: int


# ── Helpers ─────────────────────────────────────────────

ARTIFACT_PATTERN = re.compile(r"^(\d{8}_\d{6})_(.+)\.md$")


def parse_artifact(filepath: Path, artifact_type: str) -> Optional[Artifact]:
    match = ARTIFACT_PATTERN.match(filepath.name)
    if not match:
        return None
    ts_str, slug = match.groups()
    created = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
    return Artifact(
        id=ts_str,
        type=artifact_type,
        agent=AGENT_MAP[artifact_type],
        slug=slug,
        path=str(filepath.relative_to(WORKSPACE.parent)),
        created_at=created,
        size_bytes=filepath.stat().st_size,
    )


def scan_artifacts(
    type_filter: Optional[str] = None,
    agent_filter: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> list[Artifact]:
    artifacts = []
    for atype, dirname in TYPE_DIRS.items():
        if type_filter and atype != type_filter:
            continue
        if agent_filter and AGENT_MAP[atype] != agent_filter:
            continue
        dirpath = WORKSPACE / dirname
        if not dirpath.exists():
            continue
        for f in dirpath.glob("*.md"):
            art = parse_artifact(f, atype)
            if art is None:
                continue
            if since and art.created_at < since:
                continue
            if until and art.created_at > until:
                continue
            artifacts.append(art)
    artifacts.sort(key=lambda a: a.created_at, reverse=True)
    return artifacts


def find_artifact(artifact_id: str) -> Optional[tuple[Path, str]]:
    for atype, dirname in TYPE_DIRS.items():
        dirpath = WORKSPACE / dirname
        if not dirpath.exists():
            continue
        for f in dirpath.glob(f"{artifact_id}_*.md"):
            return f, atype
    return None


# ── Endpoints ───────────────────────────────────────────


@app.get("/artifacts", response_model=ArtifactListResponse)
def list_artifacts(
    type: Optional[str] = Query(None, description="Filter by task type"),
    agent: Optional[str] = Query(None, description="Filter by agent (claude/codex)"),
    since: Optional[datetime] = Query(None, description="Artifacts created after"),
    until: Optional[datetime] = Query(None, description="Artifacts created before"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = Query("date", description="Sort by: date, type, size"),
    reverse: bool = Query(False),
):
    all_artifacts = scan_artifacts(type, agent, since, until)

    if sort == "type":
        all_artifacts.sort(key=lambda a: a.type, reverse=reverse)
    elif sort == "size":
        all_artifacts.sort(key=lambda a: a.size_bytes, reverse=reverse)
    else:
        all_artifacts.sort(key=lambda a: a.created_at, reverse=not reverse)

    page = all_artifacts[offset : offset + limit]
    return ArtifactListResponse(count=len(page), total=len(all_artifacts), artifacts=page)


@app.get("/artifacts/{artifact_id}", response_model=ArtifactDetail)
def show_artifact(artifact_id: str):
    result = find_artifact(artifact_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_id} not found")
    filepath, atype = result
    art = parse_artifact(filepath, atype)
    content = filepath.read_text(encoding="utf-8")
    return ArtifactDetail(**art.model_dump(), content=content)


@app.get("/search", response_model=SearchResponse)
def search_artifacts(
    q: str = Query(..., description="Search pattern (regex supported)"),
    type: Optional[str] = Query(None),
    agent: Optional[str] = Query(None),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    case_sensitive: bool = Query(False),
    context: int = Query(2, ge=0, le=10),
    max_hits: int = Query(100, ge=1, le=1000),
):
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pattern = re.compile(q, flags)
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Invalid pattern: {e}")

    artifacts = scan_artifacts(type, agent, since, until)
    matches = []
    total_hits = 0

    for art in artifacts:
        filepath = WORKSPACE.parent / art.path
        lines = filepath.read_text(encoding="utf-8").splitlines()
        hits = []
        for i, line in enumerate(lines):
            if pattern.search(line):
                hits.append(SearchHit(
                    line=i + 1,
                    text=line,
                    context_before=lines[max(0, i - context) : i],
                    context_after=lines[i + 1 : i + 1 + context],
                ))
                total_hits += 1
                if total_hits >= max_hits:
                    break
        if hits:
            matches.append(SearchMatch(
                id=art.id, type=art.type, agent=art.agent, path=art.path, hits=hits
            ))
        if total_hits >= max_hits:
            break

    return SearchResponse(
        pattern=q, total_hits=total_hits, files_matched=len(matches), matches=matches
    )


@app.get("/logs", response_model=LogResponse)
def query_logs(
    level: Optional[str] = Query(None, description="Filter by level"),
    run: Optional[str] = Query(None, description="Filter by run timestamp"),
    since: Optional[datetime] = Query(None),
    tail: int = Query(100, ge=1, le=1000),
    errors: bool = Query(False, description="Show only errors"),
):
    log_pattern = re.compile(
        r"\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\]\s+\[(\w+)\]\s+(.*)"
    )
    entries = []

    for logfile in sorted(LOGS_DIR.glob("amadeus_*.log")):
        run_id = logfile.stem.replace("amadeus_", "")
        if run and run_id != run:
            continue
        for line in logfile.read_text(encoding="utf-8").splitlines():
            m = log_pattern.match(line)
            if not m:
                continue
            ts, lvl, msg = m.groups()
            if errors and lvl != "ERROR":
                continue
            if level and lvl != level.upper():
                continue
            if since:
                entry_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if entry_dt < since.replace(tzinfo=entry_dt.tzinfo):
                    continue
            entries.append(LogEntry(
                timestamp=ts, level=lvl, message=msg, run_id=run_id, source=logfile.name
            ))

    entries = entries[-tail:]
    return LogResponse(count=len(entries), entries=entries)


@app.get("/stats", response_model=StatsResponse)
def get_stats(
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
):
    artifacts = scan_artifacts(since=since, until=until)
    by_type = TypeStats()
    by_agent = AgentStats()
    total_size = 0

    for art in artifacts:
        setattr(by_type, art.type, getattr(by_type, art.type) + 1)
        setattr(by_agent, art.agent, getattr(by_agent, art.agent) + 1)
        total_size += art.size_bytes

    error_count = 0
    for logfile in LOGS_DIR.glob("amadeus_*.log"):
        error_count += logfile.read_text().count("[ERROR]")

    return StatsResponse(
        total=len(artifacts),
        total_size_bytes=total_size,
        by_type=by_type,
        by_agent=by_agent,
        oldest=min((a.created_at for a in artifacts), default=None),
        newest=max((a.created_at for a in artifacts), default=None),
        error_count=error_count,
    )
