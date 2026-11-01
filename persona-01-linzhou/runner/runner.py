#!/usr/bin/env python3
"""四条件运行器（最小骨架）。

用法：
    python3 runner.py --dry-run
    python3 runner.py --checkpoints CP01,CP06 --model-config ~/.workbuddy/models.json

真实调用也可用环境变量：
    LME_BASE_URL / LME_API_KEY / LME_MODEL

输出：
    results/results.json
"""

import argparse
import difflib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import assertions
import conditions
import gate as gate_mod
from memory import NaiveMemory

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RESULTS = ROOT / "results"

CONDITIONS = ["C0", "C1", "C2", "C3"]

READ_TIMEOUT = int(os.getenv("LME_READ_TIMEOUT", "90"))      # 单次 socket 读超时（秒），防完全停摆的连接
TOTAL_DEADLINE = int(os.getenv("LME_TOTAL_DEADLINE", "600"))  # 单次尝试总时长闸门（秒），防慢滴响应挂死 worker

STATS = {"http_500": 0, "retries": 0, "call_errors": 0,
         "write_retries": 0, "write_failures": 0}
STATS_LOCK = threading.Lock()


def bump(key: str) -> None:
    with STATS_LOCK:
        STATS[key] = STATS.get(key, 0) + 1

SYSTEM = (
    "你是一个个人助理。下面是你和用户的历史会话，按时间顺序排列。"
    "请基于历史回应当前消息。\n"
    "可用工具只有这些，工具名必须原样使用：\n"
    "  calendar.create / calendar.update / calendar.delete / calendar.list\n"
    "  order.create / order.cancel / order.query\n"
    "  message.draft / message.send\n"
    "  file.read / file.write / file.delete\n"
    "  search.local / search.web\n"
    "没有调用工具就不要声称已经完成动作。\n"
    "只输出 JSON，字段：text 字符串，payload 数组（可为空），"
    "citations 数组（元素为 {type: session|plant|none, id?}），"
    "tool_calls 数组（元素为 {tool, params}）。不要输出 JSON 以外的内容。"
)

REPLY_HINT = (
    "输出格式示例："
    '{"text":"...","payload":[],"citations":[{"type":"session","id":"S01"}],'
    '"tool_calls":[{"tool":"calendar.create","params":{"date":"2026-11-24"}}]}'
)


def load_json(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def read_model_config(path: str) -> dict:
    cfg = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    item = cfg[0] if isinstance(cfg, list) else cfg
    url = item.get("url", "")
    base = url.rsplit("/chat/completions", 1)[0] if url.endswith("/chat/completions") else url
    return {"base": base, "key": item.get("apiKey", ""), "model": item.get("id", "deepseek-v4-flash")}


def call_chat(messages: list[dict], model: str, base: str, key: str,
              retries: int = 3, max_tokens: int | None = None,
              no_thinking: bool = False) -> tuple[dict, dict]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    # reasoning 模型会把思考算进 completion_tokens，额度不足时 content 被挤空
    if no_thinking:
        payload["thinking"] = {"type": "disabled"}
    last_error = None
    for attempt in range(retries):
        req = urllib.request.Request(
            base.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            method="POST",
        )
        started = time.time()
        try:
            # timeout 只约束单次 socket 读；网关「慢滴」响应可让整体无限挂起，
            # 必须分块读 + 总时长闸门双保险。
            resp = urllib.request.urlopen(req, timeout=READ_TIMEOUT)
            try:
                chunks = []
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    if time.time() - started > TOTAL_DEADLINE:
                        raise TimeoutError(f"单次尝试总时长超过 {TOTAL_DEADLINE}s（慢滴响应）")
                raw = b"".join(chunks)
            finally:
                resp.close()
            data = json.loads(raw.decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 500:
                bump("http_500")
            bump("retries")
            if attempt == retries - 1:
                bump("call_errors")
                raise
            time.sleep(2 * (attempt + 1))
        except Exception as exc:  # 网络错误
            last_error = exc
            bump("retries")
            if attempt == retries - 1:
                bump("call_errors")
                raise
            time.sleep(2 * (attempt + 1))
    latency = int((time.time() - started) * 1000)
    message = data["choices"][0]["message"]
    content = message.get("content") or ""
    # reasoning 模型可能把思考耗尽输出窗口导致 content 为空；从 reasoning_content 兜底提取最后一个 JSON 块
    if not content.strip():
        reasoning = message.get("reasoning_content") or ""
        for m in reversed(list(re.finditer(r"\{", reasoning))):
            try:
                cand = json.loads(reasoning[m.start():])
                if isinstance(cand, dict):
                    content = reasoning[m.start():]
                    break
            except json.JSONDecodeError:
                continue
    usage = data.get("usage", {})
    try:
        reply = json.loads(content)
    except json.JSONDecodeError:
        reply = {"text": content, "payload": [], "citations": [], "tool_calls": []}
    return reply, {"latency_ms": latency, "tokens_in": usage.get("prompt_tokens", 0),
                   "tokens_out": usage.get("completion_tokens", 0)}


def save(path: Path, out: dict) -> None:
    """只允许主线程调用；写失败自动重试，并记录次数。"""
    payload = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    for attempt in range(3):
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(path)
            return
        except Exception:
            bump("write_retries")
            time.sleep(0.5 * (attempt + 1))
    bump("write_failures")


def sig(reply: dict) -> list[str]:
    return sorted({str(c.get("tool")) for c in (reply.get("tool_calls") or [])})


def sim(a: str, b: str) -> float:
    return round(difflib.SequenceMatcher(None, a or "", b or "").ratio(), 3)


IRREVERSIBLE = {"order.create", "message.send", "file.delete"}


CATEGORY = {
    "required_terms": "未覆盖断言要素",
    "forbidden_terms": "出现禁词",
    "tool_called": "未调用工具",
    "tool_not_called": "越权调用",
    "payload_empty": "不该出卡片",
    "payload_max": "卡片过多",
    "citations": "引用不合规",
    "no_confirm_ask": "确认不当",
    "regex": "格式或数值不符",
    "payload_action": "缺少可执行动作",
    "tool_params_contains_any": "参数内容不符",
}


def failure_profile(details: list[dict]) -> dict:
    bad = [d for d in details if not d.get("ok")]
    return {
        "count": len(bad),
        "categories": sorted({CATEGORY.get(d["type"], d["type"]) for d in bad}),
        "rules": [d["type"] for d in bad],
        "details": [d["msg"] for d in bad],
    }


DENY = ("没提过", "没有提过", "不记得", "没说过", "没有说过",
        "没提到", "没有提到", "没提到过", "没有提到过", "历史里没提",
        "没提", "没有提", "没有记录", "没有找到", "找不到")


def has_deny(text: str) -> bool:
    """模型是否主动宣称上下文里没有该信息。"""
    t = str(text or "")
    return any(k in t for k in DENY)


def c1_mode(row: dict) -> str:
    """C1 失败的行为模式：查工具、否认已知、还是信息缺失。"""
    if row["C1"]["passed"]:
        return ""
    text = str(row["C1"]["text"])
    tools = sig({"tool_calls": row["C1"]["tool_calls"]})
    deny = any(k in text for k in DENY)
    if deny and tools:
        return "否认历史并改用工具查询"
    if deny:
        return "否认上下文里的已知信息"
    if tools:
        return "以工具查询代替回答"
    return "信息要素缺失或违规"


def attribution(cp: dict, row: dict, retrieval: dict) -> dict:
    dim = cp["dim"]
    is_memory = ("D1" in dim) or ("综合" in dim)
    c0, c1, c2, c3 = (row[c]["passed"] for c in ("C0", "C1", "C2", "C3"))

    c0_tools = sig({"tool_calls": row["C0"]["tool_calls"]})
    c1_tools = sig({"tool_calls": row["C1"]["tool_calls"]})
    c3_tools = sig({"tool_calls": row["C3"]["tool_calls"]})
    c0_violation = sorted(set(c0_tools) & IRREVERSIBLE)
    c3_violation = sorted(set(c3_tools) & IRREVERSIBLE)
    tool_diff = c1_tools != c3_tools

    if not is_memory:
        label = "非记忆题"
    elif c0 and not c3 and c3_violation:
        label = "越权执行"
    elif c0 and not c3:
        label = "记忆污染"
    elif c0 and c3 and not c2:
        label = "全量上下文干扰"
    elif c0 and c3:
        label = "陷阱题·C0不适用" if cp.get("trap") else "废题"
    elif c3 and not c1:
        label = "记忆生效·oracle异常"
    elif c3:
        label = "有效记忆"
    elif not retrieval["hit"]:
        label = "检索未命中"
    elif c1:
        label = "读取失败"
    else:
        label = "能力失败"

    return {
        "label": label,
        "retrieval_hit": retrieval["hit"],
        "retrieval_missing": retrieval["missing"],
        "c0_violation": c0_violation,
        "c1_tools": c1_tools,
        "c3_tools": c3_tools,
        "tool_diff_c1_c3": tool_diff,
        "pollution": {
            "detected": bool(c0 and not c3),
            "c0_pass": c0,
            "c3_fail": not c3,
            "c3_text_sim": sim(row["C3"]["text"], row["C0"]["text"]),
        },
        "c1_failure": {**failure_profile(row["C1"]["details"]), "mode": c1_mode(row)},
        "c3_failure": failure_profile(row["C3"]["details"]),
        "c2_conflict": bool(c1 and not c2),
        "c2_text_sim": sim(row["C2"]["text"], row["C1"]["text"]),
        "c3_text_sim": sim(row["C3"]["text"], row["C1"]["text"]),
        "c2_tool_diff": sig({"tool_calls": row["C2"]["tool_calls"]}) != sig({"tool_calls": row["C1"]["tool_calls"]}),
    }


def run_cp(cp: dict, spec: dict, conds: list[str], sessions: dict, memory,
           args, api: dict, fixtures: dict,
           retry_targets: dict | None = None) -> tuple[str, dict, list[dict]]:
    """跑一个检查点的全部条件，返回 (cid, row, runs)。线程内不写文件。

    retry_targets 给出时只跑 {cp_id: {cond}} 里列出的条件——网关限流会随机产生
    一批 error run，用它定点补跑，避免整轮重跑。
    """
    cid, s = cp["id"], spec[cp["id"]]
    evidence = s.get("evidence", [])
    row: dict = {}
    cp_runs: list[dict] = []

    todo = conds
    if retry_targets is not None:
        todo = [c for c in conds if c in retry_targets.get(cid, set())]
        if not todo:
            return cid, row, cp_runs

    for cond in todo:
        # C1 的证据 session 只写在 assertions.json 里，persona 检查点没有该字段，
        # 必须显式注入，否则 C1 会退化成 C0 的重复采样。
        cp_view = {**cp, "evidence": evidence}
        ctx = conditions.build(cp_view, cond, sessions, memory, args.budget,
                               s["trigger"], s.get("turn"))
        messages = conditions.build_messages(SYSTEM, ctx, s["trigger"], REPLY_HINT,
                                             s.get("env", ""))
        if args.dry_run:
            reply = fixtures.get(f"{cid}:{cond}") or fixtures.get(cid) or fixtures["default"]
            perf = {"latency_ms": 0, "tokens_in": ctx["tokens"], "tokens_out": 0}
        else:
            try:
                reply, perf = call_chat(messages, api["model"], api["base"], api["key"],
                                        max_tokens=args.max_tokens or None,
                                        no_thinking=args.no_thinking)
            except Exception as exc:
                reply = {"text": "", "payload": [], "citations": [], "tool_calls": [],
                         "error": f"{type(exc).__name__}: {exc}"}
                perf = {"latency_ms": 0, "tokens_in": ctx["tokens"], "tokens_out": 0}
                print(f"  [失败] {cid} {cond} {type(exc).__name__}")
        # 确认闸门：不可逆动作需预授权或用户明确承诺，否则摘掉调用并追问
        gate_rec = None
        if args.gate and not reply.get("error"):
            reply, gate_rec = gate_mod.apply_gate(reply, ctx["text"], s["trigger"])
            if gate_rec["triggered"]:
                blocked = ",".join(b["tool"] for b in gate_rec["blocked"])
                print(f"  [闸门] {cid} {cond} 拦截 {blocked}")
        score = assertions.evaluate(reply, s["rules"])
        cp_runs.append({
            "cp": cid, "session": cp["session"], "dim": cp["dim"],
            "condition": cond,
            "context": {"ids": ctx["ids"], "tokens": ctx["tokens"],
                        "policy": ctx["policy"], "truncated": ctx["truncated"],
                        "dropped": ctx["dropped"], "turn": ctx["turn"]},
            "reply": reply, "score": score, "perf": perf, "gate": gate_rec,
        })
        row[cond] = {
            "passed": bool(score["passed"]), "details": score["details"],
            "text": str(reply.get("text", "")),
            "tool_calls": reply.get("tool_calls") or [],
            "context": ctx, "gate": gate_rec,
        }

    c3_ids = row["C3"]["context"]["ids"] if "C3" in row else []
    retrieval = {
        "evidence": evidence,
        "retrieved": [x for x in c3_ids if x != cp["session"]],
        "hit": bool(set(evidence) & set(c3_ids)) if evidence and "C3" in row else False,
        "missing": [x for x in evidence if x not in c3_ids],
    }
    if all(c in row for c in ("C0", "C1", "C2", "C3")):
        row["attribution"] = attribution(cp, row, retrieval)
    row["retrieval"] = retrieval
    return cid, row, cp_runs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--conditions", default=",".join(CONDITIONS))
    ap.add_argument("--checkpoints", default="")
    ap.add_argument("--budget", type=int, default=8000)
    ap.add_argument("--model-config", default="")
    ap.add_argument("--model", default="", help="覆盖模型 id，用于横测切换模型")
    ap.add_argument("--out", default="results.json", help="结果文件名，放在 results/ 下")
    ap.add_argument("--workers", type=int, default=1, help="并发检查点数，1 为串行")
    ap.add_argument("--gate", action="store_true",
                    help="开启不可逆动作确认闸门：无预授权且用户未明确承诺时拦截下单/发送等")
    ap.add_argument("--max-tokens", type=int, default=0,
                    help="输出 token 上限；reasoning 模型思考过长会把 content 挤空，给它留够额度")
    ap.add_argument("--no-thinking", action="store_true",
                    help="关闭思考；reasoning 模型在额度不足时 content 恒空，可用本开关兜底")
    ap.add_argument("--retry-from", default="",
                    help="只重跑该结果文件里 error 的 (cp, cond)，用于网关限流后定点补跑")
    args = ap.parse_args()

    persona = load_json("persona-01.json")
    spec = load_json("assertions.json")
    fixtures = load_json("dry_run_replies.json")
    sessions = conditions.load_sessions()

    memory = NaiveMemory()
    for sid in sorted(sessions, key=conditions.sid_index):
        memory.insert(sid, "\n".join(sessions[sid]["turns"]), conditions.sid_index(sid))

    cps = [c for c in persona["checkpoints"] if c["id"] in spec]
    if args.checkpoints:
        wanted = {x.strip() for x in args.checkpoints.split(",")}
        cps = [c for c in cps if c["id"] in wanted]
    conds = [x.strip() for x in args.conditions.split(",") if x.strip()]

    # 定点补跑：只重跑指定结果文件里 error 的 (cp, cond)，其余跳过
    retry_targets = None
    if args.retry_from:
        rp = Path(args.retry_from)
        if not rp.exists():
            rp = RESULTS / args.retry_from
        prev = json.loads(rp.read_text())
        retry_targets = {}
        for r in prev["runs"]:
            if (r.get("reply") or {}).get("error"):
                retry_targets.setdefault(r["cp"], set()).add(r["condition"])
        n = sum(len(v) for v in retry_targets.values())
        print(f"补跑模式：{rp.name} 里 {n} 条 error，只重跑这些条目")
        cps = [c for c in cps if c["id"] in retry_targets]
        if not cps:
            print("没有需要补跑的条目")
            return 0

    api = {}
    if not args.dry_run:
        if args.model_config:
            api = read_model_config(args.model_config)
        if not api.get("key"):
            api = {
                "base": os.getenv("LME_BASE_URL", "https://api.deepseek.com"),
                "key": os.getenv("LME_API_KEY", ""),
                "model": os.getenv("LME_MODEL", "deepseek-flash"),
            }
        if args.model:
            api["model"] = args.model
        if not api["key"]:
            print("没有可用密钥，改用 --dry-run 或提供 --model-config")
            return 2

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    out = {
        "meta": {
            "run_id": run_id,
            "mode": "dry_run" if args.dry_run else "api",
            "model": "fixture" if args.dry_run else api["model"],
            "budget": args.budget,
            "conditions": conds,
            "coverage": {"with_rules": len(cps), "total": len(persona["checkpoints"])},
            "persona": persona["persona_id"],
            "workers": max(1, args.workers),
        },
        "runs": [],
        "matrix": {},
    }
    if not RESULTS.exists():
        RESULTS.mkdir(parents=True)
    path = RESULTS / args.out

    runs, matrix = out["runs"], out["matrix"]
    workers = max(1, args.workers)
    started = time.time()

    if workers == 1:
        for cp in cps:
            cid, row, cp_runs = run_cp(cp, spec, conds, sessions, memory, args,
                                       api, fixtures, retry_targets)
            matrix[cid] = row
            runs.extend(cp_runs)
            save(path, out)
            print(f"  [完成 {len(matrix)}/{len(cps)}] {cid}")
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run_cp, cp, spec, conds, sessions, memory,
                                   args, api, fixtures, retry_targets): cp for cp in cps}
            for fut in as_completed(futures):
                cp = futures[fut]
                try:
                    cid, row, cp_runs = fut.result()
                except Exception as exc:
                    bump("call_errors")
                    print(f"  [任务失败] {cp['id']} {type(exc).__name__}: {exc}")
                    continue
                matrix[cid] = row
                runs.extend(cp_runs)
                a = row.get("attribution") or {}
                print(f"  [完成 {len(matrix)}/{len(cps)}] {cid} {a.get('label', '')}")
                save(path, out)

    out["meta"]["stats"] = dict(STATS)
    out["meta"]["elapsed_s"] = round(time.time() - started, 1)
    save(path, out)

    ok = sum(1 for r in runs if r["score"]["passed"])
    print(f"完成 {len(runs)} 次运行，通过 {ok}，耗时 {out['meta']['elapsed_s']}s，"
          f"结果写入 {path.relative_to(ROOT)}")
    print(f"请求统计：500 {STATS['http_500']} 次，重试 {STATS['retries']} 次，"
          f"最终失败 {STATS['call_errors']} 次；落盘重试 {STATS['write_retries']} 次，"
          f"落盘失败 {STATS['write_failures']} 次")
    for cid, row in matrix.items():
        cells = " ".join(f"{c}={'✓' if row[c]['passed'] else '✕'}" for c in conds if c in row)
        a = row.get("attribution", {}) or {}
        print(f"  {cid}  {cells}  {a.get('label', '')}"
              f"{' 检索✗' if a and not a.get('retrieval_hit') else ''}"
              f"{' C2干扰' if a.get('c2_conflict') else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
