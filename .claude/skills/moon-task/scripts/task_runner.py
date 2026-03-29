#!/usr/bin/env python3
"""
moon-task: Lightweight TASK.md Workflow Interpreter

Usage:
    python task_runner.py <TASK.md> [options]

Options:
    --var KEY=VALUE    Set/override a variable (repeatable)
    --from CELL_ID     Start execution from a specific cell
    --dry-run, -n      Parse and display cells without executing
    --list, -l         List all cells and exit
    --quiet, -q        Suppress output (only exit code)

Variable system (three syntaxes, one dict):
    {{KEY}}           In cell code body AND cond= attribute — template substitution
    variables["KEY"]  In python cells — runtime dict access

Built-in variables (always available):
    TASK_FILE         Absolute path of the TASK.md file
    TASK_DIR          Directory containing the TASK.md file
    LAST_CELL         ID of the last executed cell (updated after each real execution)
    LAST_RC           Exit code of the last executed cell (string)
    LAST_STDOUT       Stdout of the last executed cell (TASK_* lines stripped)
    LAST_STDERR       Stderr of the last executed cell
    ALL_VARS          All current variables as KEY=VALUE lines (injected before each cell, long values truncated)
"""

import re
import sys
import subprocess
import os
import time
import textwrap
import platform
import argparse
import io
import threading
import contextlib
import shlex
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from pathlib import Path

# Guard for pythonw.exe (no console window): sys.stdout/stderr are None
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

# Suppress console windows when launched from a windowless process (e.g. pythonw.exe)
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0

# ─── ANSI Colors ──────────────────────────────────────────────────────────────

_IS_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
_C = lambda c, t: f"\033[{c}m{t}\033[0m" if _IS_TTY else t
GREEN  = lambda t: _C("32", t)
RED    = lambda t: _C("31", t)
YELLOW = lambda t: _C("33", t)
CYAN   = lambda t: _C("36", t)
DIM    = lambda t: _C("2",  t)
BOLD   = lambda t: _C("1",  t)

# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class Cell:
    index:      int
    lang:       str
    code:       str
    id:         str = ""
    title:      str = ""
    on_fail:    str = "stop"   # stop | skip | <cell-id>
    on_success: str = "next"   # next | stop | <cell-id>
    cond:       str = ""       # $VAR==value | $VAR!=value | $VAR (truthy)
    timeout:    int = 300
    args:       str = ""       # extra CLI args forwarded verbatim to the backend interpreter
    line_no:    int = 0

    def __post_init__(self):
        if not self.id:
            self.id = f"cell-{self.index}"
        self.lang = self.lang.lower()


@dataclass
class CellResult:
    cell_id:     str
    status:      str           # success | failed | skipped | stopped
    stdout:      str = ""
    stderr:      str = ""
    return_code: int = 0
    directives:  Dict[str, str] = field(default_factory=dict)
    duration:    float = 0.0
    error_msg:   str = ""

# ─── Parser ───────────────────────────────────────────────────────────────────

_FRONTMATTER_RE = re.compile(r'^---\r?\n(.*?)\r?\n---\r?\n', re.DOTALL)

# Match fenced code blocks; info string must start with a non-space char
_CELL_RE = re.compile(
    r'^```(\S[^\n]*?)\s*\n(.*?)^```[ \t]*$',
    re.MULTILINE | re.DOTALL
)

# Match key=value, key="value", key='value' in info string
_ATTR_RE = re.compile(r'(\w+)=(?:"([^"]*?)"|\'([^\']*?)\'|([^\s]+))')


def _parse_attrs(info: str) -> Tuple[str, Dict[str, str]]:
    """Parse 'shell id=setup title="My Step"' → ('shell', {'id': 'setup', ...})"""
    parts = info.split(None, 1)
    lang = parts[0].lower() if parts else ""
    attrs: Dict[str, str] = {}
    if len(parts) > 1:
        for m in _ATTR_RE.finditer(parts[1]):
            key = m.group(1)
            val = m.group(2) if m.group(2) is not None else \
                  m.group(3) if m.group(3) is not None else \
                  m.group(4)
            attrs[key] = val
    return lang, attrs


def _parse_frontmatter(content: str) -> Tuple[Dict, str]:
    """Extract YAML frontmatter. Returns (meta_dict, body_after_frontmatter)."""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}, content

    raw = m.group(1)
    meta: Dict = {}

    try:
        import yaml
        meta = yaml.safe_load(raw) or {}
    except ImportError:
        # Minimal fallback parser for flat key: value + vars block
        in_vars = False
        for line in raw.splitlines():
            if line.rstrip() == "vars:":
                in_vars = True
                meta.setdefault("vars", {})
                continue
            if in_vars:
                if line.startswith("  ") and ":" in line:
                    k, _, v = line.strip().partition(":")
                    meta["vars"][k.strip()] = v.strip().partition(" #")[0].strip()
                elif not line.startswith(" "):
                    in_vars = False
            if ":" in line and not line.startswith(" "):
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip().partition(" #")[0].strip()

    return meta, content[m.end():]


def parse_task_md(content: str) -> Tuple[Dict, List[Cell]]:
    """Parse TASK.md content → (frontmatter_dict, list_of_cells)"""
    meta, body = _parse_frontmatter(content)

    cells: List[Cell] = []
    idx = 0
    body_offset = len(content) - len(body)

    for m in _CELL_RE.finditer(body):
        info = m.group(1).strip()
        code = m.group(2)
        line_no = content[: m.start() + body_offset].count("\n") + 1

        lang, attrs = _parse_attrs(info)

        # Blocks with no lang specifier — skip (cannot be addressed or jumped to)
        if lang == "":
            continue

        cell = Cell(
            index      = idx,
            lang       = lang,
            code       = code,
            id         = attrs.get("id", f"cell-{idx}"),
            title      = attrs.get("title", ""),
            on_fail    = attrs.get("on_fail",    "stop"),
            on_success = attrs.get("on_success", "next"),
            cond       = attrs.get("cond",       ""),
            timeout    = int(attrs.get("timeout", 300)),
            args       = attrs.get("args", ""),
            line_no    = line_no,
        )
        cells.append(cell)
        idx += 1

    return meta, cells

# ─── Variables ────────────────────────────────────────────────────────────────

_VAR_RE = re.compile(r'\{\{(\w+)\}\}')


def substitute_vars(text: str, variables: Dict[str, str]) -> Tuple[str, List[str]]:
    """Replace {{KEY}} tokens with values from variables dict.
    Returns (substituted_text, list_of_missing_keys)."""
    missing: List[str] = []

    def replace(m: re.Match) -> str:
        key = m.group(1)
        if key in variables:
            return variables[key]
        missing.append(key)
        return m.group(0)  # keep original {{KEY}} with warning

    return _VAR_RE.sub(replace, text), missing


def eval_cond(cond: str, variables: Dict[str, str]) -> bool:
    """Evaluate cond= attribute using {{KEY}} syntax (same as code body substitution).

    Supported forms:
      {{KEY}}==value   — equal
      {{KEY}}!=value   — not equal
      {{KEY}}          — truthy (non-empty, not "false"/"0"/"no"/"none")

    Returns False → cell is skipped (next cell; on_fail/on_success not triggered,
    LAST_* not updated).
    """
    expanded, _ = substitute_vars(cond, variables)
    for op, fn in [("!=", str.__ne__), ("==", str.__eq__)]:
        if op in expanded:
            left, _, right = expanded.partition(op)
            return fn(left.strip(), right.strip())
    return bool(expanded) and expanded.lower() not in ("false", "0", "none", "no", "")


def parse_directives(output: str) -> Tuple[str, Dict[str, str]]:
    """Extract TASK_VERB: args lines from stdout output.

    Returns (clean_output_without_directive_lines, directives_dict).
    TASK_VAR may appear multiple times; all are joined with newlines under key "VAR".
    """
    directives: Dict[str, str] = {}
    var_lines: List[str] = []
    clean: List[str] = []

    for line in (output or "").splitlines():
        mm = re.match(r'^TASK_([A-Z_]+):\s*(.*)', line.rstrip())
        if mm:
            verb, args = mm.group(1), mm.group(2).strip()
            if verb == "VAR":
                var_lines.append(args)
            else:
                directives[verb] = args
        else:
            clean.append(line)

    if var_lines:
        directives["VAR"] = "\n".join(var_lines)

    return "\n".join(clean), directives

# ─── Cell Executors ───────────────────────────────────────────────────────────

def _run_shell(code: str, lang: str, timeout: int, cwd: str) -> Tuple[str, str, int]:
    is_win = platform.system() == "Windows"

    if lang in ("powershell", "ps1"):
        # Prepend UTF-8 console setup so output is always UTF-8
        utf8_prefix = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", utf8_prefix + code]
        use_shell = False
    elif lang == "cmd":
        # chcp 65001 switches cmd codepage to UTF-8
        cmd = f"chcp 65001 >nul 2>&1 & {code}"
        use_shell = True
    elif is_win and lang in ("shell", "bash", "sh"):
        bash_paths = [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ]
        bash = next((p for p in bash_paths if os.path.exists(p)), None)
        if bash:
            cmd = [bash, "-c", code]
            use_shell = False
        else:
            cmd = code
            use_shell = True
    else:
        cmd = code
        use_shell = True

    try:
        result = subprocess.run(
            cmd,
            shell=use_shell,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
            cwd=cwd,
            creationflags=_NO_WINDOW,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", f"Timeout after {timeout}s", 124
    except Exception as e:
        return "", str(e), 1


def _run_python(code: str, timeout: int, variables: Dict[str, str]) -> Tuple[str, str, int]:
    """Execute Python code in-process.

    The 'variables' dict is injected into the exec namespace as 'variables',
    allowing both {{KEY}} template substitution (pre-exec) and
    variables.get("KEY") runtime access within the same cell.
    """
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    rc_holder = [0]

    namespace: Dict = {
        "variables": variables.copy(),
        "__builtins__": __builtins__,
    }

    def _target():
        try:
            with contextlib.redirect_stdout(stdout_buf), \
                 contextlib.redirect_stderr(stderr_buf):
                exec(compile(code, "<cell>", "exec"), namespace)  # noqa: S102
        except SystemExit as e:
            rc_holder[0] = e.code if isinstance(e.code, int) else 1
        except Exception:
            import traceback
            stderr_buf.write(traceback.format_exc())
            rc_holder[0] = 1

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        return "", f"Timeout after {timeout}s", 124

    return stdout_buf.getvalue(), stderr_buf.getvalue(), rc_holder[0]


# ─── AI CLI Adapters ──────────────────────────────────────────────────────────
# Each adapter: fn(prompt, timeout, cwd) → (stdout, stderr, rc)

def _ai_claude(prompt: str, timeout: int, cwd: str, extra: List[str] = []) -> Tuple[str, str, int]:
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text"] + extra,
        capture_output=True, text=True, timeout=timeout, cwd=cwd,
        stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW,
    )
    return result.stdout, result.stderr, result.returncode


def _ai_gemini(prompt: str, timeout: int, cwd: str, extra: List[str] = []) -> Tuple[str, str, int]:
    result = subprocess.run(
        ["gemini", "-p", prompt] + extra,
        capture_output=True, text=True, timeout=timeout, cwd=cwd,
        stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW,
    )
    return result.stdout, result.stderr, result.returncode


def _ai_moon(prompt: str, timeout: int, cwd: str, extra: List[str] = []) -> Tuple[str, str, int]:
    result = subprocess.run(
        ["moon", "-p", prompt] + extra,
        capture_output=True, text=True, timeout=timeout, cwd=cwd,
        stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW,
    )
    return result.stdout, result.stderr, result.returncode


_AI_ADAPTERS = {
    "claude": _ai_claude,
    "gemini": _ai_gemini,
    "moon":   _ai_moon,
}
_AI_AUTO_ORDER = ["claude", "gemini", "moon"]


def _run_ai(prompt: str, timeout: int, cwd: str, args: str = "") -> Tuple[str, str, int]:
    """Execute an AI cell.

    Resolution order:
      1. MOON_AI env var  — explicit CLI name or path
      2. Auto-detect      — try claude → gemini → moon

    args: extra CLI flags forwarded verbatim to the AI backend
          (e.g. '--dangerouslySkipPermissions' or '--allowedTools Bash,Read,Edit').
    """
    extra: List[str] = shlex.split(args) if args.strip() else []

    # Unset CLAUDECODE for the duration of AI subprocess calls so that
    # claude/moon can be invoked even inside a parent Claude Code session.
    _claudecode = os.environ.pop("CLAUDECODE", None)
    try:
        explicit = os.environ.get("MOON_AI", "").strip()

        # Collect per-backend failure reasons for diagnostics
        failures: List[str] = []

        def _try(name: str, adapter) -> Optional[Tuple[str, str, int]]:
            try:
                out, err, rc = adapter(prompt, timeout, cwd, extra)
                if rc == 0 or out:
                    return out, err, rc
                # Found but returned error with no stdout — record reason and skip
                reason = err.strip() or f"exit code {rc}"
                failures.append(f"{name}: {reason}")
                return None
            except FileNotFoundError:
                failures.append(f"{name}: not found in PATH")
                return None
            except subprocess.TimeoutExpired:
                return "", f"AI cell timeout after {timeout}s", 124

        if explicit:
            known = explicit.lower()
            if known in _AI_ADAPTERS:
                result = _try(known, _AI_ADAPTERS[known])
            else:
                def _custom(p, t, c, ex=[]):
                    r = subprocess.run(
                        [explicit, "-p", p] + ex,
                        capture_output=True, text=True, timeout=t, cwd=c,
                        creationflags=_NO_WINDOW,
                    )
                    return r.stdout, r.stderr, r.returncode
                result = _try(explicit, _custom)

            if result is not None:
                return result
            detail = failures[-1] if failures else "not found or returned error"
            return "", f"MOON_AI='{explicit}': {detail}", 1

        for name in _AI_AUTO_ORDER:
            result = _try(name, _AI_ADAPTERS[name])
            if result is not None:
                return result

        detail = "; ".join(failures) if failures else "none tried"
        return (
            "",
            "No AI backend available.\n"
            f"  Tried: {detail}\n"
            "  Fix: set MOON_AI=claude/gemini/moon, or ensure a CLI is in PATH.",
            1,
        )
    finally:
        if _claudecode is not None:
            os.environ["CLAUDECODE"] = _claudecode

# ─── TaskRunner ───────────────────────────────────────────────────────────────

class TaskRunner:
    """Parses and executes a TASK.md workflow file."""

    def __init__(
        self,
        task_file: str,
        initial_vars: Optional[Dict[str, str]] = None,
        dry_run: bool = False,
        only_cell: Optional[str] = None,
        start_from: Optional[str] = None,
        verbose: bool = True,
    ):
        self.task_file  = Path(task_file).resolve()
        self.cwd        = str(self.task_file.parent)
        self.variables: Dict[str, str] = {
            "TASK_FILE":   str(self.task_file),
            "TASK_DIR":    str(self.task_file.parent),
            # LAST_* built-ins — empty until first cell executes
            "LAST_CELL":   "",
            "LAST_RC":     "",
            "LAST_STDOUT": "",
            "LAST_STDERR": "",
        }
        if initial_vars:
            self.variables.update(initial_vars)

        self.cells:    List[Cell]       = []
        self.results:  List[CellResult] = []
        self.cell_map: Dict[str, Cell]  = {}
        self.dry_run   = dry_run
        self.only_cell  = only_cell
        self.start_from = start_from
        self.verbose    = verbose

    def _log(self, *args, **kwargs):
        if self.verbose:
            print(*args, **kwargs)

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self) -> Dict:
        """Parse TASK.md, return frontmatter dict."""
        content = self.task_file.read_text(encoding="utf-8")
        meta, self.cells = parse_task_md(content)
        self.cell_map = {c.id: c for c in self.cells}

        # Frontmatter vars: don't override --var or built-ins supplied by caller
        for k, v in (meta.get("vars") or {}).items():
            self.variables.setdefault(str(k), str(v))

        if not self.cells:
            raise ValueError("No executable cells found in TASK.md")
        return meta

    def run(self) -> List[CellResult]:
        meta = self.load()

        start_idx = 0
        target_id = self.only_cell or self.start_from
        if target_id:
            found = next(
                (i for i, c in enumerate(self.cells) if c.id == target_id), None
            )
            if found is None:
                flag = "--cell" if self.only_cell else "--from"
                raise ValueError(f"{flag} cell '{target_id}' not found")
            start_idx = found

        name = meta.get("name", self.task_file.stem)
        self._log(f"\n{BOLD(name)}  {DIM(str(len(self.cells)) + ' cells')}")
        self._log(DIM(f"  {self.task_file}") + "\n")

        idx = start_idx
        t0  = time.time()

        while idx < len(self.cells):
            cell = self.cells[idx]
            result, jump = self._exec_cell(cell)
            self.results.append(result)

            if self.only_cell:
                break  # --cell: stop after this single cell

            if jump == "__stop__":
                break
            if jump:
                target = next(
                    (i for i, c in enumerate(self.cells) if c.id == jump), None
                )
                if target is None:
                    self._log(RED(f"\n  ERROR: jump target '{jump}' not found — stopping"))
                    break
                idx = target
            else:
                idx += 1

        self._print_summary(time.time() - t0)
        return self.results

    # ── Cell Execution ────────────────────────────────────────────────────────

    def _exec_cell(self, cell: Cell) -> Tuple[CellResult, Optional[str]]:
        # ── Condition check — skip without updating LAST_* ──
        if cell.cond:
            if not eval_cond(cell.cond, self.variables):
                self._print_header(cell, skipped=True)
                return CellResult(cell_id=cell.id, status="skipped"), None

        self._print_header(cell)

        # ── Inject ALL_VARS built-in: all current variables as KEY=VALUE lines ──
        #    Long values (>200 chars) are truncated to keep prompts readable.
        _MAX_VAR_LEN = 200
        _skip = {"ALL_VARS", "LAST_STDOUT", "LAST_STDERR"}
        self.variables["ALL_VARS"] = "\n".join(
            f"{k}={v[:_MAX_VAR_LEN] + ('...' if len(v) > _MAX_VAR_LEN else '')}"
            for k, v in self.variables.items()
            if k not in _skip
        )

        # ── Template substitution: {{KEY}} → value ──
        code, missing = substitute_vars(cell.code, self.variables)
        for key in missing:
            self._log(DIM("  ⚠ variable '{{" + key + "}}' not set"))

        # ── Dry run ──
        if self.dry_run:
            self._log(DIM(f"  [dry-run] {cell.lang} ({len(code.splitlines())} lines)"))
            return CellResult(cell_id=cell.id, status="success"), None

        # ── Execute ──
        t0 = time.time()
        stdout, stderr, rc = self._dispatch(cell, code)
        duration = time.time() - t0

        # ── Parse directives from stdout ──
        clean_out, directives = parse_directives(stdout)

        # ── Auto-inject LAST_* built-in variables ──
        # These are set here (after real execution) so subsequent cells can reference:
        #   {{LAST_RC}}, {{LAST_STDERR}}, {{LAST_STDOUT}}, {{LAST_CELL}}
        #   as well as $LAST_RC, $LAST_STDERR in cond= attributes.
        _trunc = int(os.environ.get("MOON_TASK_OUTPUT_LIMIT", "1024"))
        self.variables["LAST_CELL"]   = cell.id
        self.variables["LAST_RC"]     = str(rc)
        self.variables["LAST_STDOUT"] = clean_out[:_trunc]
        self.variables["LAST_STDERR"] = stderr[:_trunc]

        # ── Display clean output ──
        if clean_out.strip():
            for line in clean_out.rstrip().splitlines():
                self._log("  " + line)
        if stderr.strip():
            for line in stderr.rstrip().splitlines():
                self._log("  " + RED(line))

        # ── Apply TASK_VAR directives ──
        for pair in (directives.pop("VAR", "") or "").splitlines():
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                k, v = k.strip(), v.strip()
                self.variables[k] = v
                self._log(DIM(f"  ${k}") + f" = {v}")

        # ── Show flow directive hints ──
        if "JUMP" in directives:
            self._log(CYAN(f"  -> {directives['JUMP']}"))
        if "FAIL" in directives:
            self._log(RED(f"  ! {directives['FAIL']}"))
        if "SKIP" in directives:
            self._log(DIM("  skip"))

        # ── Determine outcome status ──
        if "FAIL" in directives:
            status, error_msg = "failed", directives.get("FAIL", "TASK_FAIL signalled")
        elif rc != 0:
            status, error_msg = "failed", f"exit code {rc}"
        elif "STOP" in directives:
            status, error_msg = "stopped", directives.get("STOP", "")
        else:
            status, error_msg = "success", ""

        # TASK_SKIP overrides status (not a failure, just skipped; doesn't update LAST_*)
        if "SKIP" in directives:
            status = "skipped"
            # Roll back LAST_* since we're treating this as skipped
            self.variables["LAST_CELL"]   = ""
            self.variables["LAST_RC"]     = ""
            self.variables["LAST_STDOUT"] = ""
            self.variables["LAST_STDERR"] = ""

        result = CellResult(
            cell_id=cell.id, status=status,
            stdout=clean_out, stderr=stderr,
            return_code=rc, directives=directives,
            duration=duration, error_msg=error_msg,
        )
        self._print_footer(result)

        # ── Routing ──
        jump: Optional[str] = None
        if status == "stopped":
            return result, "__stop__"
        if "JUMP" in directives:
            jump = directives["JUMP"]
        elif status == "failed":
            of = cell.on_fail
            if of == "stop":
                jump = "__stop__"
            elif of == "skip":
                jump = None          # → next cell
            else:
                jump = of            # → named cell
        elif status == "success":
            os_ = cell.on_success
            if os_ == "next":
                jump = None
            elif os_ == "stop":
                jump = "__stop__"
            else:
                jump = os_

        return result, jump

    def _dispatch(self, cell: Cell, code: str) -> Tuple[str, str, int]:
        lang = cell.lang
        if lang in ("shell", "sh", "bash", "cmd", "bat", "powershell", "ps1"):
            return _run_shell(code, lang, cell.timeout, self.cwd)
        if lang in ("python", "py"):
            return _run_python(code, cell.timeout, self.variables)
        if lang == "ai":
            return _run_ai(code, cell.timeout, self.cwd, cell.args)
        if lang in ("note", "md", "markdown", "text"):
            return code.strip(), "", 0
        # Unknown lang — skip with warning
        self._log(YELLOW(f"  ⚠ unknown lang '{lang}' — skipping"))
        return "", "", 0

    # ── Display Helpers ───────────────────────────────────────────────────────

    def _print_header(self, cell: Cell, skipped: bool = False):
        raw_title, _ = substitute_vars(cell.title, self.variables) if cell.title else (cell.title, [])
        title = f"  {raw_title}" if raw_title else ""
        lang  = DIM(f" ({cell.lang})")
        if skipped:
            cond = DIM(f"  cond: {cell.cond}") if cell.cond else ""
            self._log(DIM(f"[{cell.id}]{title}") + lang + cond)
        else:
            self._log(CYAN(f"[{cell.id}]") + title + lang)

    def _print_footer(self, r: CellResult):
        t = DIM(f"  {r.duration:.1f}s")
        if r.status == "success":
            self._log(GREEN("  ok") + t)
        elif r.status == "failed":
            self._log(RED(f"  fail: {r.error_msg}") + t)
        elif r.status == "stopped":
            msg = f": {r.error_msg}" if r.error_msg else ""
            self._log(YELLOW(f"  stop{msg}") + t)
        elif r.status == "skipped":
            self._log(DIM("  skip"))

    def _print_summary(self, elapsed: float):
        ok  = sum(1 for r in self.results if r.status == "success")
        err = sum(1 for r in self.results if r.status == "failed")
        skp = sum(1 for r in self.results if r.status == "skipped")
        self._log(
            f"\n{GREEN(str(ok) + ' ok')}  "
            f"{(RED if err else DIM)(str(err) + ' fail')}  "
            f"{DIM(str(skp) + ' skip')}  "
            f"{DIM(f'{elapsed:.1f}s')}"
        )

# ─── CLI ──────────────────────────────────────────────────────────────────────

def _parse_var_arg(v: str) -> Tuple[str, str]:
    if "=" not in v:
        print(f"Warning: ignoring --var '{v}' (expected KEY=VALUE)", file=sys.stderr)
        return "", ""
    k, val = v.split("=", 1)
    return k.strip(), val.strip()


def main():
    parser = argparse.ArgumentParser(
        prog="moon-task",
        description="moon-task: TASK.md Workflow Interpreter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python task_runner.py workflow.TASK.md
              python task_runner.py workflow.TASK.md --var ENV=prod --var VERSION=1.2
              python task_runner.py workflow.TASK.md --from download --dry-run
              python task_runner.py workflow.TASK.md --cell detect-version
              python task_runner.py workflow.TASK.md --list
        """),
    )
    parser.add_argument("task_file", help="Path to .TASK.md file")
    parser.add_argument("--var", "-v", action="append", metavar="KEY=VALUE",
                        help="Set/override a variable (repeatable)")
    parser.add_argument("--from", dest="start_from", metavar="CELL_ID",
                        help="Start execution from this cell ID")
    parser.add_argument("--cell", dest="only_cell", metavar="CELL_ID",
                        help="Run only this single cell and exit")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Parse and display cells without executing")
    parser.add_argument("--list", "-l", action="store_true",
                        help="List cell metadata and exit")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress all output (exit code reflects success/failure)")

    args = parser.parse_args()
    task_file = Path(args.task_file)

    if not task_file.exists():
        print(f"Error: file not found: {task_file}", file=sys.stderr)
        sys.exit(2)

    initial_vars: Dict[str, str] = {}
    for v in args.var or []:
        k, val = _parse_var_arg(v)
        if k:
            initial_vars[k] = val

    runner = TaskRunner(
        task_file   = str(task_file),
        initial_vars= initial_vars,
        dry_run     = args.dry_run or args.list,
        only_cell   = args.only_cell,
        start_from  = args.start_from,
        verbose     = not args.quiet,
    )

    # ── --list mode ──
    if args.list:
        meta = runner.load()
        name = meta.get("name", task_file.stem)
        print(f"\n{BOLD(name)}  —  {DIM(str(task_file))}")
        print(f"{'ID':<22} {'LANG':<12} {'ON_FAIL':<10} {'ON_OK':<10} {'COND':<24} TITLE")
        print("─" * 90)
        for c in runner.cells:
            print(
                f"  {c.id:<20} {c.lang:<12} {c.on_fail:<10} {c.on_success:<10} "
                f"{(c.cond or '—'):<24} {c.title}"
            )
        print()
        sys.exit(0)

    # ── Execute ──
    try:
        results = runner.run()
        failed  = any(r.status == "failed" for r in results)
        sys.exit(1 if failed else 0)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
