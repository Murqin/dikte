"""OpenAI (transcription) and OpenRouter (cleanup) calls, stdlib only."""

import json
import mimetypes
import os
import secrets
import urllib.error
import urllib.request

from i18n import t

USER_AGENT = "dikte/1.0 (+https://github.com/yusufipk/dikte)"
OPENROUTER_URL = "https://openrouter.ai/api/v1"

# Only whisper-1 returns segment-level timestamps.
TIMESTAMP_MODEL = "whisper-1"


class ApiError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def explain(exc, service):
    """Turn an HTTP status into something the user can act on."""
    if exc.status in (401, 403):
        return ApiError(t("{service} rejected the API key (HTTP {code}). Open "
                          "Settings and check it.", service=service, code=exc.status),
                        exc.status)
    if exc.status == 402:
        return ApiError(t("{service} says the account is out of credit (HTTP 402).",
                          service=service), exc.status)
    if exc.status == 429:
        return ApiError(t("{service} is rate limiting you (HTTP 429). Try again in "
                          "a moment.", service=service), exc.status)
    return ApiError(f"{service}: {exc}", exc.status)


def _request(url, data, headers, timeout=120):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise ApiError(f"HTTP {exc.code}: {_extract_error(body)}", exc.code) from exc
    except urllib.error.URLError as exc:
        raise ApiError(t("Could not connect: {reason}", reason=exc.reason)) from exc
    except json.JSONDecodeError as exc:
        raise ApiError(t("Could not parse the response: {error}", error=exc)) from exc


def _extract_error(body):
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body[:300]
    err = payload.get("error")
    if isinstance(err, dict):
        return err.get("message") or json.dumps(err)[:300]
    if isinstance(err, str):
        return err
    return body[:300]


def _multipart(fields, file_field, file_path):
    """Build a multipart/form-data body; returns (body, content-type)."""
    boundary = "----dikte" + secrets.token_hex(16)
    out = bytearray()
    for name, value in fields:
        if value is None or value == "":
            continue
        out += f"--{boundary}\r\n".encode()
        out += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        out += str(value).encode("utf-8") + b"\r\n"

    filename = os.path.basename(file_path)
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    with open(file_path, "rb") as fh:
        payload = fh.read()
    out += f"--{boundary}\r\n".encode()
    out += (
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
        f"Content-Type: {ctype}\r\n\r\n"
    ).encode()
    out += payload + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def _transcribe_request(wav_path, api_key, model, language, prompt, base_url,
                        response_format, granularity=None, timeout=300):
    if not api_key:
        raise ApiError(t("OpenAI API key is empty. Add it in Settings."))
    fields = [("model", model), ("response_format", response_format)]
    if language and language != "auto":
        fields.append(("language", language))
    if prompt:
        fields.append(("prompt", prompt))
    if granularity:
        fields.append(("timestamp_granularities[]", granularity))
    body, ctype = _multipart(fields, "file", wav_path)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": ctype,
        "User-Agent": USER_AGENT,
    }
    try:
        return _request(
            f"{base_url.rstrip('/')}/audio/transcriptions", body, headers, timeout=timeout
        )
    except ApiError as exc:
        raise explain(exc, "OpenAI") from None


def transcribe(wav_path, api_key, model="gpt-4o-transcribe", language="", prompt="",
               base_url="https://api.openai.com/v1", timeout=300):
    data = _transcribe_request(
        wav_path, api_key, model, language, prompt, base_url, "json", timeout=timeout
    )
    text = (data.get("text") or "").strip()
    if not text:
        raise ApiError(t("Transcript came back empty."))
    return text


def transcribe_segments(wav_path, api_key, language="", prompt="",
                        base_url="https://api.openai.com/v1", timeout=300):
    """[(start_seconds, text)] using whisper-1's verbose response."""
    data = _transcribe_request(
        wav_path, api_key, TIMESTAMP_MODEL, language, prompt, base_url,
        "verbose_json", granularity="segment", timeout=timeout,
    )
    segments = data.get("segments") or []
    out = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if text:
            out.append((float(seg.get("start") or 0.0), text))
    if not out:
        text = (data.get("text") or "").strip()
        if not text:
            raise ApiError(t("Transcript came back empty."))
        out = [(0.0, text)]
    return out


def cleanup(text, api_key, model, system_prompt, base_url=OPENROUTER_URL, timeout=180):
    if not api_key:
        raise ApiError(t("OpenRouter API key is empty. Add it in Settings."))
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"<transcript>\n{text}\n</transcript>"},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "HTTP-Referer": "https://github.com/yusufipk/dikte",
        "X-Title": "Dikte",
    }
    try:
        data = _request(
            f"{base_url.rstrip('/')}/chat/completions",
            json.dumps(payload).encode("utf-8"),
            headers,
            timeout=timeout,
        )
    except ApiError as exc:
        raise explain(exc, "OpenRouter") from None
    choices = data.get("choices") or []
    if not choices:
        raise ApiError(_extract_error(json.dumps(data)))
    content = ((choices[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise ApiError(t("The cleanup model returned an empty reply."))
    return content


def _get_json(url, headers, timeout=20):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise ApiError(f"HTTP {exc.code}: {_extract_error(body)}", exc.code) from exc
    except urllib.error.URLError as exc:
        raise ApiError(t("Could not connect: {reason}", reason=exc.reason)) from exc
    except json.JSONDecodeError as exc:
        raise ApiError(t("Could not parse the response: {error}", error=exc)) from exc


def openrouter_key_status(api_key):
    """Check the key against OpenRouter's own /key endpoint."""
    if not api_key:
        raise ApiError(t("OpenRouter API key is empty. Add it in Settings."))
    try:
        data = _get_json(f"{OPENROUTER_URL}/key",
                         {"Authorization": f"Bearer {api_key}", "User-Agent": USER_AGENT})
    except ApiError as exc:
        raise explain(exc, "OpenRouter") from None
    info = data.get("data") or {}
    limit, usage = info.get("limit"), info.get("usage")
    if limit is None:
        return t("Key works, no spending limit set.")
    return t("Key works. Used {usage} of {limit}.",
             usage=round(float(usage or 0), 3), limit=round(float(limit), 3))


def openrouter_models(api_key=""):
    """Model ids available on OpenRouter (no key required)."""
    headers = {"User-Agent": USER_AGENT}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = _get_json(f"{OPENROUTER_URL}/models", headers)
    return sorted(m["id"] for m in data.get("data", []) if m.get("id"))


def openai_models(api_key, base_url="https://api.openai.com/v1"):
    if not api_key:
        raise ApiError(t("OpenAI API key is empty. Add it in Settings."))
    try:
        data = _get_json(
            f"{base_url.rstrip('/')}/models",
            {"Authorization": f"Bearer {api_key}", "User-Agent": USER_AGENT},
        )
    except ApiError as exc:
        raise explain(exc, "OpenAI") from None
    ids = [m["id"] for m in data.get("data", []) if m.get("id")]
    audio = [i for i in ids if "transcribe" in i or "whisper" in i]
    return sorted(audio or ids)
