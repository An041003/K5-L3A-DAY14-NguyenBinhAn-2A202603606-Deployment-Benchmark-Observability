"""Add missing topic documents without changing golden data or evaluator."""
from pathlib import Path
import argparse
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'06-lab-complete/benchmark-observability'
MARKER = '# DAY14_KB_FIX_V1'
ENTRIES = '''    # DAY14_KB_FIX_V1
    (["jwt", "json web token"],
     "JWT là token có chữ ký, chứa claims như vai trò và thời điểm hết hạn. Server kiểm tra chữ ký và expiry; API key thường là một bí mật tĩnh cần đối chiếu và rotate."),
    (["kubernetes hpa", "hpa", "horizontal pod autoscaler"],
     "Kubernetes HPA thay đổi số replica dựa trên CPU, memory hoặc custom metrics như RPS và queue depth; nó đối chiếu giá trị quan sát với target đã cấu hình."),
'''
def apply(path: Path):
    data = path.read_text(encoding='utf-8')
    if MARKER in data:
        return
    anchor = 'KNOWLEDGE_BASE: list[tuple[list[str], str]] = [\n'
    if data.count(anchor) != 1:
        raise RuntimeError(f'Unexpected upstream KB format: {path}')
    path.write_text(data.replace(anchor, anchor+ENTRIES, 1), encoding='utf-8')
    print(f'Patched: {path.relative_to(ROOT)}')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Check fix is installed')
    args = parser.parse_args()
    for name in ['develop','production']:
        path = BASE/name/'utils/mock_llm.py'
        if args.check:
            assert MARKER in path.read_text(encoding='utf-8'), path
        else:
            apply(path)
if __name__ == '__main__': main()
