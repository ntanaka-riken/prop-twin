#!/usr/bin/env python3
"""Convert the Claude Code session JSONL into a readable Markdown transcript.
usage: python3 make_markdown.py session_raw.jsonl transcript.md [--full]
  --full: tool inputs and results are written without truncation"""
import json, sys, datetime
FULL = "--full" in sys.argv

def short(x, n):
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, indent=1)
    return s if FULL or len(s) <= n else s[:n] + f" … ({len(s)} chars)"

def text_of(content):
    if isinstance(content, str):
        return content
    out = []
    for b in content or []:
        if isinstance(b, dict):
            if b.get("type") == "text":
                out.append(b.get("text", ""))
            elif b.get("type") == "tool_result":
                c = b.get("content")
                if isinstance(c, list):
                    c = "\n".join(x.get("text", "[image]") if isinstance(x, dict) else str(x) for x in c)
                out.append("<<TOOL_RESULT>>" + short(c or "", 1500))
            elif b.get("type") == "image":
                out.append("[image]")
    return "\n".join(out)

rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
md = ["# セッション記録:ESPr Developer / L293D デジタルツイン\n",
      "Claude Code セッション 4ccccbbb-9307-4e71-804f-1160f86304e6 の会話を読みやすく変換したものです。"
      + ("ツールの入出力は省略せずに全文を載せています。" if FULL else "ツールの入出力は長いものを省略しています。完全な記録は session_raw.jsonl と session-export.zip にあります。") + "\n"]
seen = set()
for o in rows:
    t = o.get("type")
    if t not in ("user", "assistant") or o.get("isSidechain"):
        continue
    u = o.get("uuid")
    if u in seen:
        continue
    seen.add(u)
    ts = o.get("timestamp", "")[:19].replace("T", " ")
    msg = o.get("message", {})
    content = msg.get("content")
    if t == "user":
        txt = text_of(content)
        if not txt.strip():
            continue
        if "<<TOOL_RESULT>>" in txt:
            for part in txt.split("<<TOOL_RESULT>>")[1:]:
                md.append(f"<details><summary>ツール結果 ({ts})</summary>\n\n````\n{part.strip()}\n````\n</details>\n")
            continue
        if "<system-reminder>" in txt and len(txt.replace("<system-reminder>", "").strip()) < 5:
            continue
        md.append(f"\n---\n\n## 👤 ユーザー ({ts})\n\n{txt.strip()}\n")
    else:
        for b in content or []:
            if b.get("type") == "text" and b.get("text", "").strip():
                md.append(f"\n### 🤖 Claude ({ts})\n\n{b['text'].strip()}\n")
            elif b.get("type") == "tool_use":
                inp = b.get("input", {})
                desc = inp.get("description") or inp.get("file_path") or inp.get("action") or ""
                body = inp.get("command") or inp.get("content") or inp
                md.append(f"<details><summary>ツール: {b.get('name')} — {str(desc)[:120]}</summary>\n\n````\n{short(body, 4000) if not FULL else (body if isinstance(body, str) else json.dumps(inp, ensure_ascii=False, indent=1))}\n````\n</details>\n")
open(sys.argv[2], "w").write("\n".join(md))
print("wrote", sys.argv[2], len(md), "blocks")
