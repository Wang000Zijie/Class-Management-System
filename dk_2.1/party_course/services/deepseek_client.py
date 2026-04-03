import json
import re
from urllib import error, request


def _extract_json(text: str) -> dict:
    if isinstance(text, dict):
        return text
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False)

    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("AI 返回中未找到 JSON 结构")
    return json.loads(match.group(0))


def _post_chat(base_url: str, api_key: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=40) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise ValueError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise ValueError(f"DeepSeek 请求失败: {exc}") from exc


def chat_json(api_key: str, base_url: str, model: str, system_prompt: str, user_prompt: str) -> dict:
    if not api_key:
        raise ValueError("未配置 DEEPSEEK_API_KEY")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    try:
        data = _post_chat(base_url, api_key, payload)
    except ValueError as exc:
        # Some model versions may not support response_format; retry once without it.
        if "response_format" in str(exc):
            payload.pop("response_format", None)
            data = _post_chat(base_url, api_key, payload)
        else:
            raise

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"DeepSeek 返回结构异常: {data}") from exc

    return _extract_json(content)