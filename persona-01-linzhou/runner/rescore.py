#!/usr/bin/env python3
"""用当前断言规则重判已保存的回复，不需要重新调用模型。

断言改了口径、或归因规则变了之后，用这个脚本把历史结果重算一遍。
用法：
    python3 rescore.py            # 重判 results/ 下所有结果文件
    python3 rescore.py --dry      # 只报告变化，不写回
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import assertions  # noqa: E402
import runner  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--only", default="", help="只重判指定文件名，例如 results.json")
    ap.add_argument("--dir", default="", help="结果目录，相对 persona 根目录，默认 results/")
    args = ap.parse_args()

    persona = json.loads((ROOT / "data" / "persona-01.json").read_text(encoding="utf-8"))
    cpmap = {c["id"]: c for c in persona["checkpoints"]}
    spec = json.loads((ROOT / "data" / "assertions.json").read_text(encoding="utf-8"))

    src_dir = ROOT / args.dir if args.dir else RESULTS
    files = [f for f in sorted(src_dir.glob("results*.json")) if f.name != "all.json"]
    if args.only:
        files = [f for f in files if f.name == args.only]
        if not files:
            print(f"没有找到 {args.only}")
            return 2
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        before = sum(1 for r in data.get("runs", []) if r["score"]["passed"])
        changed = []
        for run in data.get("runs", []):
            cid = run["cp"]
            if cid not in spec:
                continue
            new = assertions.evaluate(run["reply"], spec[cid]["rules"])
            if bool(new["passed"]) != bool(run["score"]["passed"]):
                changed.append((cid, run["condition"], run["score"]["passed"], new["passed"]))
            run["score"] = new
            row = data["matrix"].get(cid, {})
            if run["condition"] in row:
                row[run["condition"]]["passed"] = bool(new["passed"])
                row[run["condition"]]["details"] = new["details"]

        for cid, row in data.get("matrix", {}).items():
            if all(k in row for k in ("C0", "C1", "C2", "C3")) and cid in cpmap:
                row["attribution"] = runner.attribution(cpmap[cid], row, row["retrieval"])

        after = sum(1 for r in data.get("runs", []) if r["score"]["passed"])
        print(f"{path.name}: 通过 {before} → {after}" + (f"，变化 {len(changed)} 处" if changed else ""))
        for c in changed:
            print(f"  {c[0]} {c[1]}: {'✓' if c[2] else '✕'} → {'✓' if c[3] else '✕'}")
        if not args.dry:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
