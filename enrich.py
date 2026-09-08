"""Look up a highlighted word or phrase in context, via an LLM.

Only runs for highlights tagged 生词. The key is read from <store>/.jot-api-key
or the ANTHROPIC_API_KEY / OPENAI_API_KEY environment variables; the provider is
inferred from the key prefix. With no key, lookups are skipped and the note is
left as-is.

Override the model by putting a model id in <store>/.jot-model.
"""

import os
from pathlib import Path

DEFAULT_MODEL = {
    "anthropic": "claude-opus-5",
    "openai": "gpt-4o-mini",
}

SYSTEM = """你是帮助中文母语者学英语的助手。用户在读英文文章时划出了一个词或短语,你给出贴合上下文的解释。

输出纯 Markdown,不要开场白、不要结尾、不要代码块:

- **词** /音标/ *词性* — 中文释义(15 字以内)
- 划出的是短语就整体解释一行;是多个生词就每个一行
- 习语/俚语要点明
- 最后单独一行:**这句话里:** 用一句中文说它在给定上下文中的具体意思

只解释划出的部分,不要翻译整句,不要举额外例句。"""


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def credentials(store: Path) -> tuple[str, str]:
    """Return (provider, key). Provider is inferred from the key prefix."""
    key = _read(Path(store) / ".jot-api-key")
    key = key or os.environ.get("ANTHROPIC_API_KEY", "").strip()
    key = key or os.environ.get("OPENAI_API_KEY", "").strip()
    if key.startswith("sk-ant-"):
        return "anthropic", key
    if key.startswith("sk-"):
        return "openai", key
    return "", ""


def model_for(store: Path, provider: str) -> str:
    return _read(Path(store) / ".jot-model") or DEFAULT_MODEL[provider]


def available(store: Path) -> bool:
    provider, _ = credentials(store)
    if not provider:
        return False
    try:
        __import__(provider)
    except ImportError:
        return False
    return True


def prompt(term: str, context: str, title: str) -> str:
    parts = ["划出的内容:" + term.strip()]
    if context.strip() and context.strip() != term.strip():
        parts.append("所在段落:" + context.strip())
    if title.strip():
        parts.append("文章标题:" + title.strip())
    return "\n".join(parts)


def _anthropic(key: str, model: str, user: str) -> str:
    import anthropic

    response = anthropic.Anthropic(api_key=key).messages.create(
        model=model,
        max_tokens=1000,
        system=SYSTEM,
        # Adaptive thinking is on by default for this model; low effort keeps a
        # short vocabulary lookup fast and cheap without turning it off.
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": user}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("模型拒绝回答")
    return "".join(b.text for b in response.content if b.type == "text").strip()


def _openai(key: str, model: str, user: str) -> str:
    import openai

    response = openai.OpenAI(api_key=key).chat.completions.create(
        model=model,
        max_completion_tokens=1000,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def lookup(term: str, context: str, title: str, store: Path) -> str:
    """Return Markdown for the definition, or raise."""
    provider, key = credentials(store)
    if not provider:
        raise RuntimeError("没有配置 API key")

    model = model_for(store, provider)
    user = prompt(term, context, title)
    text = (_anthropic if provider == "anthropic" else _openai)(key, model, user)
    if not text:
        raise RuntimeError("空回复")
    return text
