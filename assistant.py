"""Handing a dictation to Claude Code as a command, and pasting back its answer.

`claude -p` runs the same session an interactive window would open: the same
skills, the same MCP servers, the same account. So a dictation does not have to
end as text on the screen. It can be a question to answer or a job to carry out,
and what comes back is pasted exactly where the transcript would have been.

Its output is read as it arrives rather than waited out. A command that reaches
for the calendar or the web takes long enough that a still indicator is
indistinguishable from a hang, so every tool it picks up is named in the corner
while it works.
"""

import json
import os
import shutil
import subprocess
import threading
import time

import config as cfg
from i18n import t

SESSION_FILE = cfg.DATA_DIR / "assistant.json"

# What to say in the indicator for a tool, keyed by name. Anything unlisted is
# named as it comes, which is better than a generic "working" for the tools that
# arrive from an MCP server nobody wrote this table for.
TOOL_LABELS = {
    "Bash": "Running a command…",
    "BashOutput": "Running a command…",
    "Read": "Reading…",
    "Glob": "Looking through files…",
    "Grep": "Searching the files…",
    "Edit": "Editing a file…",
    "Write": "Writing a file…",
    "NotebookEdit": "Editing a file…",
    "WebSearch": "Searching the web…",
    "WebFetch": "Reading a web page…",
    "Task": "Handing it to a subagent…",
    "TodoWrite": "Planning…",
}


class AssistantError(Exception):
    pass


class Cancelled(Exception):
    pass


# --- the conversation -----------------------------------------------------
#
# One conversation is kept across dictations, so "and move that to tomorrow"
# means something. It is dropped once it has sat unused for long enough: an
# hour later the next command is almost certainly a new subject, and dragging
# the old one along costs tokens and invites the model to answer the wrong
# question.

def read_session(max_age_seconds):
    """The session to continue, or "" when there is none worth continuing."""
    try:
        with open(SESSION_FILE, encoding="utf-8") as fh:
            row = json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return ""
    session = str(row.get("session", ""))
    if not session:
        return ""
    if max_age_seconds and time.time() - row.get("ts", 0) > max_age_seconds:
        return ""
    return session


def write_session(session):
    try:
        cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(SESSION_FILE, "w", encoding="utf-8") as fh:
            json.dump({"session": session, "ts": time.time()}, fh)
    except OSError:
        pass


def clear_session():
    try:
        SESSION_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def session_age():
    """Seconds since the stored conversation was last used, or None."""
    try:
        with open(SESSION_FILE, encoding="utf-8") as fh:
            row = json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return time.time() - row.get("ts", 0) if row.get("session") else None


# --- the call -------------------------------------------------------------

def working_dir(conf):
    wanted = conf["assistant_dir"].strip()
    if wanted and os.path.isdir(os.path.expanduser(wanted)):
        return os.path.expanduser(wanted)
    return os.path.expanduser("~")


def ask(prompt, conf, on_stage=None, should_stop=None):
    """Run the prompt through Claude Code. Returns (answer, warning).

    `warning` is set when the answer arrived but something about the run should
    be seen anyway, a denied tool above all: the reply still reads like a normal
    one, and only the denial explains why it did not do what it was asked to.
    """
    if not shutil.which("claude"):
        raise AssistantError(t(
            "claude not found. Install Claude Code and make sure `claude` is on "
            "your PATH."
        ))

    session = read_session(conf["assistant_session_minutes"] * 60)
    try:
        return _run(prompt, conf, session, on_stage, should_stop)
    except _SessionGone:
        # The conversation it pointed at is not there any more: the history was
        # cleared, or it was started somewhere else. Say nothing and start over,
        # because from the outside this is just the first command of the day.
        clear_session()
        return _run(prompt, conf, "", on_stage, should_stop)


class _SessionGone(Exception):
    pass


def _run(prompt, conf, session, on_stage, should_stop):
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose",
        "--model", conf["assistant_model"],
        "--permission-mode", conf["assistant_permission_mode"],
        "--append-system-prompt", conf.assistant_prompt(),
    ]
    if session:
        cmd += ["--resume", session]

    try:
        proc = subprocess.Popen(
            cmd, cwd=working_dir(conf), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
    except OSError as exc:
        raise AssistantError(t("Could not run claude: {error}", error=exc)) from exc

    answer, warning, new_session, failure = "", "", "", ""
    # Reading the stream blocks between lines, and a model that thinks for a
    # minute sends none. So the clock and the stop button are watched from the
    # side, and they end the run by killing the process: that closes the stream
    # and the loop below falls out of its own accord.
    ended = {"cancelled": False, "timed_out": False}
    watchdog = threading.Thread(
        target=_watch,
        args=(proc, time.monotonic() + conf["assistant_timeout"], should_stop, ended),
        daemon=True,
    )
    watchdog.start()

    try:
        for line in proc.stdout:
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            kind = event.get("type")
            if kind == "system" and event.get("subtype") == "init":
                new_session = event.get("session_id", "") or new_session
            elif kind == "assistant" and on_stage:
                for label in _labels(event):
                    on_stage(label)
            elif kind == "result":
                new_session = event.get("session_id", "") or new_session
                answer = (event.get("result") or "").strip()
                if event.get("is_error"):
                    failure = answer or t("Claude ended with an error.")
                    answer = ""
                warning = _denial_warning(event)
    finally:
        stderr = _finish(proc)
        watchdog.join(timeout=1)

    if ended["cancelled"]:
        raise Cancelled()
    if ended["timed_out"]:
        raise AssistantError(t(
            "Claude did not finish within {seconds} seconds.",
            seconds=conf["assistant_timeout"],
        ))
    if proc.returncode != 0 and not answer:
        if session and _session_missing(stderr):
            raise _SessionGone()
        raise AssistantError(_first_line(stderr) or failure or t(
            "claude exited with code {code}.", code=proc.returncode
        ))
    if failure:
        raise AssistantError(failure)
    if not answer:
        raise AssistantError(t("Claude answered with nothing."))

    if new_session:
        write_session(new_session)
    return answer, warning


def _watch(proc, deadline, should_stop, ended):
    while proc.poll() is None:
        if should_stop is not None and should_stop():
            ended["cancelled"] = True
            break
        if time.monotonic() > deadline:
            ended["timed_out"] = True
            break
        time.sleep(0.25)
    if ended["cancelled"] or ended["timed_out"]:
        _kill(proc)


def _labels(event):
    """The indicator lines for one assistant message, in the order they happen."""
    out = []
    for block in event.get("message", {}).get("content", []) or []:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        name = block.get("name", "")
        if name in TOOL_LABELS:
            out.append(t(TOOL_LABELS[name]))
        elif name == "Skill":
            skill = (block.get("input") or {}).get("skill", "")
            out.append(t("Using {name}…", name=skill or "a skill"))
        elif name.startswith("mcp__"):
            parts = name.split("__")
            out.append(t("Using {name}…", name=parts[1] if len(parts) > 1 else name))
        elif name:
            out.append(t("Using {name}…", name=name))
    return out


def _denial_warning(event):
    denials = event.get("permission_denials") or []
    if not denials:
        return ""
    names = []
    for denial in denials:
        name = denial.get("tool_name") if isinstance(denial, dict) else str(denial)
        if name and name not in names:
            names.append(name)
    return t("Claude was not allowed to use: {tools}", tools=", ".join(names))


def _session_missing(stderr):
    lowered = stderr.lower()
    return "session" in lowered and ("not found" in lowered or "no conversation" in lowered)


def _kill(proc):
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


def _finish(proc):
    try:
        stderr = proc.stderr.read() or ""
    except (OSError, ValueError):
        stderr = ""
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    for stream in (proc.stdout, proc.stderr):
        try:
            stream.close()
        except OSError:
            pass
    return stderr


def _first_line(text):
    lines = [line for line in (text or "").splitlines() if line.strip()]
    return lines[-1].strip() if lines else ""
