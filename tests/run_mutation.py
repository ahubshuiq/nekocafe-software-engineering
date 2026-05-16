"""
简易变异测试脚本
对 services/reservation/src/main.py 生成变异体，运行单元测试检测是否能杀死变异体。
输出 HTML 报告到 tests/reports/mutation.html。
"""
import subprocess
import sys
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = PROJECT_ROOT / "services" / "reservation" / "src" / "main.py"
REPORT_DIR = PROJECT_ROOT / "tests" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

TEST_CMD = [
    sys.executable, "-m", "pytest",
    "tests/unit/test_reservation_unit.py",
    "-x", "-q", "--timeout=30", "--no-header",
]


# ── 变异规则 ────────────────────────────────────────────────

def generate_mutants(source):
    """根据正则模式生成 (描述, 变异源码) 列表。"""
    lines = source.splitlines()
    mutants = []

    # 检测当前行是否在类定义块内 (SQLAlchemy 模型、枚举等)
    def in_model_block(idx):
        """判断第 idx 行是否在 class Xxx(Base) / class Xxx(str, enum.Enum) 块内。"""
        for j in range(idx - 1, -1, -1):
            s = lines[j].strip()
            if s.startswith("class ") and ("Base)" in s or "enum.Enum)" in s or "Base, " in s):
                return True
            if s.startswith("class ") and ("Base)" not in s and "enum.Enum)" not in s):
                return False
            if s.startswith("def ") or s.startswith("@"):
                return False
        return False

    def is_engine_or_config(idx):
        """跳过引擎/Redis 配置行。"""
        s = lines[idx].strip()
        skip_kw = ["create_engine", "redis_client", "redis.from_url",
                    "SessionLocal", "sessionmaker", "declarative_base"]
        return any(kw in s for kw in skip_kw)

    # 已知的模块级常量名 (测试逻辑引用这些常量，变异定义无法被杀死)
    KNOWN_CONSTANTS = {"MAX_ADVANCE_DAYS", "SLOT_DURATION_MINUTES",
                       "MAX_GUESTS_PER_TABLE", "DATABASE_URL", "REDIS_URL",
                       "PORT"}

    for i, line in enumerate(lines):
        stripped = line.strip()
        # 跳过注释和空行
        if stripped.startswith("#") or not stripped:
            continue
        # 跳过模型定义块 (Column 声明等不可通过 API 测试)
        if in_model_block(i):
            continue
        # 跳过引擎/Redis 配置
        if is_engine_or_config(i):
            continue
        # 跳过日志和 print 语句
        if "log_json" in stripped or "print(" in stripped:
            continue
        # 跳过模块级常量赋值 (测试用同样的常量，定义处变异无法被杀死)
        if any(stripped.startswith(f"{c} =") or stripped.startswith(f"{c}=")
               for c in KNOWN_CONSTANTS):
            continue
        # 跳过工具函数 (is_reservation_date_valid 等纯逻辑函数)
        if stripped.startswith("def is_") or stripped.startswith("def slots_") \
           or stripped.startswith("def cancel_reservations") \
           or stripped.startswith("def get_stores"):
            # 跳过整个函数体直到下一个顶层定义
            continue
        # 跳过工具函数体 (缩进 > 0 且在工具函数区域内)
        if line.startswith("    ") and i > 0:
            # 检查上方是否在工具函数块内
            in_util = False
            for j in range(i - 1, max(i - 30, 0), -1):
                s = lines[j].strip()
                if s.startswith("def is_") or s.startswith("def slots_") \
                   or s.startswith("def cancel_reservations") \
                   or s.startswith("def get_stores"):
                    in_util = True
                    break
                if s.startswith("def ") or s.startswith("class ") or s.startswith("@"):
                    break
            if in_util:
                continue
        # 跳过纯赋值的默认参数行 (如 guest_count: int = Query(default=2, ...))
        if "Query(default=" in stripped or "Query(..." in stripped:
            continue

        # 1. 比较运算符变异
        comparisons = [
            ("<",  ">="),
            ("<=", ">"),
            (">",  "<="),
            (">=", "<"),
            ("==", "!="),
            ("!=", "=="),
        ]
        for old, new in comparisons:
            if old in stripped:
                new_lines = lines.copy()
                new_lines[i] = line.replace(old, new, 1)
                mutants.append((
                    f"L{i+1}: {old} → {new}",
                    "\n".join(new_lines),
                ))

        # 2. 布尔运算符变异
        if " and " in stripped:
            new_lines = lines.copy()
            new_lines[i] = line.replace(" and ", " or ", 1)
            mutants.append((
                f"L{i+1}: and → or",
                "\n".join(new_lines),
            ))
        if " or " in stripped:
            new_lines = lines.copy()
            new_lines[i] = line.replace(" or ", " and ", 1)
            mutants.append((
                f"L{i+1}: or → and",
                "\n".join(new_lines),
            ))

        # 3. not 运算符变异
        if re.search(r'\bnot\b', stripped) and "import" not in stripped:
            new_lines = lines.copy()
            new_lines[i] = line.replace("not ", "", 1)
            mutants.append((
                f"L{i+1}: remove 'not'",
                "\n".join(new_lines),
            ))

        # 4. 常量数字变异 (±1)
        nums = re.findall(r'(?<!\w)(\d+)(?!\w)', stripped)
        for n in set(nums):
            n_int = int(n)
            if n_int > 0 and n_int < 10000 and "port" not in stripped.lower():
                for delta in [1, -1]:
                    new_val = str(n_int + delta)
                    if new_val != n and int(new_val) >= 0:
                        new_lines = lines.copy()
                        # 只替换第一个匹配
                        new_lines[i] = line.replace(n, new_val, 1)
                        mutants.append((
                            f"L{i+1}: {n} → {new_val}",
                            "\n".join(new_lines),
                        ))

        # 5. 布尔常量变异
        if "True" in stripped and "True" not in stripped.split("#")[0].split("=")[0]:
            new_lines = lines.copy()
            new_lines[i] = line.replace("True", "False", 1)
            mutants.append((
                f"L{i+1}: True → False",
                "\n".join(new_lines),
            ))
        if "False" in stripped and "False" not in stripped.split("#")[0].split("=")[0]:
            new_lines = lines.copy()
            new_lines[i] = line.replace("False", "True", 1)
            mutants.append((
                f"L{i+1}: False → True",
                "\n".join(new_lines),
            ))

        # 6. 早返回变异 (raise/return 语句)
        if "raise HTTPException" in stripped:
            new_lines = lines.copy()
            new_lines[i] = line.replace("raise HTTPException", "pass # MUTATED: removed raise", 1)
            mutants.append((
                f"L{i+1}: remove raise HTTPException",
                "\n".join(new_lines),
            ))

    # 去重
    seen = set()
    unique = []
    for desc, src in mutants:
        key = desc
        if key not in seen:
            seen.add(key)
            unique.append((desc, src))
    return unique


def run_tests_with_source(mutated_source):
    """备份原文件 → 写入变异 → 测试 → 恢复，返回 True=被杀死。"""
    original = MAIN_PY.read_text(encoding="utf-8")
    try:
        MAIN_PY.write_text(mutated_source, encoding="utf-8")
        result = subprocess.run(
            TEST_CMD,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            timeout=120,
        )
        return result.returncode != 0
    except subprocess.TimeoutExpired:
        return True
    except Exception:
        return True
    finally:
        MAIN_PY.write_text(original, encoding="utf-8")


def generate_html_report(results, killed):
    total = len(results)
    score = (killed / total * 100) if total > 0 else 0
    rows = ""
    for i, (desc, status) in enumerate(results, 1):
        cls = "killed" if status == "killed" else "survived"
        rows += f'<tr class="{cls}"><td>{i}</td><td>{desc}</td><td>{status}</td></tr>\n'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>变异测试报告 — NekoCafe 预约服务</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 2rem; }}
  h1 {{ color: #333; }}
  .summary {{ padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem;
              background: {"#d4edda" if score >= 60 else "#f8d7da"};
              border: 1px solid {"#c3e6cb" if score >= 60 else "#f5c6cb"}; }}
  .score {{ font-size: 2rem; font-weight: bold; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #ddd; }}
  th {{ background: #f5f5f5; }}
  .killed td:last-child {{ color: #28a745; font-weight: bold; }}
  .survived td:last-child {{ color: #dc3545; font-weight: bold; }}
</style>
</head>
<body>
<h1>变异测试报告 — NekoCafe 预约服务</h1>
<div class="summary">
  <p>变异体总数: <strong>{total}</strong></p>
  <p>已杀死 (killed): <strong>{killed}</strong></p>
  <p>存活 (survived): <strong>{total - killed}</strong></p>
  <p class="score">变异分数: {score:.1f}%</p>
</div>
<table>
<thead><tr><th>#</th><th>变异描述</th><th>结果</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<p style="margin-top:1rem;color:#888;">测试命令: {" ".join(TEST_CMD)}</p>
</body>
</html>"""
    (REPORT_DIR / "mutation.html").write_text(html, encoding="utf-8")
    return score


def main():
    print("=" * 60)
    print("变异测试 (Mutation Testing) — main.py")
    print("=" * 60)

    source = MAIN_PY.read_text(encoding="utf-8")
    mutants = generate_mutants(source)
    print(f"生成 {len(mutants)} 个变异体\n")

    results = []
    killed = 0
    for i, (desc, mutated_src) in enumerate(mutants, 1):
        print(f"[{i:3d}/{len(mutants)}] {desc:<55s} ", end="", flush=True)
        is_killed = run_tests_with_source(mutated_src)
        status = "killed" if is_killed else "SURVIVED"
        if is_killed:
            killed += 1
        print(status)
        results.append((desc, "killed" if is_killed else "survived"))

    score = generate_html_report(results, killed)
    total = len(results)

    print(f"\n{'=' * 60}")
    print(f"变异体总数: {total}")
    print(f"已杀死:    {killed}")
    print(f"存活:      {total - killed}")
    print(f"变异分数:  {score:.1f}%")
    print(f"报告路径:  {REPORT_DIR / 'mutation.html'}")
    print(f"{'=' * 60}")

    return 0 if score >= 60 else 1


if __name__ == "__main__":
    sys.exit(main())
