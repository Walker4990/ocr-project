"""사용법: python -m doculens_samples [--count 40] [--seed 0] [--out samples/golden]"""
import argparse
import sys
from pathlib import Path

from doculens_samples.batch import generate_golden, validate_golden


def main() -> int:
    parser = argparse.ArgumentParser(description="합성 거래명세서 골든셋 생성")
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--handwritten", type=int, default=10, help="추가할 손글씨 모사 장수")
    default_out = Path(__file__).resolve().parent.parent / "golden"
    parser.add_argument("--out", type=Path, default=default_out)
    args = parser.parse_args()

    generate_golden(args.out, count=args.count, seed=args.seed, handwritten_count=args.handwritten)
    problems = validate_golden(args.out)
    for problem in problems:
        print(problem, file=sys.stderr)
    total = args.count + args.handwritten
    print(
        f"{total}장 생성 완료(인쇄체 {args.count}, 손글씨 모사 {args.handwritten}): "
        f"{args.out} (문제 {len(problems)}건)"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
