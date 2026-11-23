import argparse
import json
from pathlib import Path

from src.evaluation import evaluate_dataset, load_evaluation_dataset
from src.workflow import ArbitrationEngine

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the configured arbitration provider on a labeled dataset.")
    parser.add_argument("--dataset", type=Path, default=ROOT / "tests" / "evaluation_dataset.json")
    parser.add_argument("--output", type=Path, help="Optional path for a JSON report; keep reports containing private data out of Git.")
    args = parser.parse_args()
    dataset_path = args.dataset
    raw_dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    version = raw_dataset.get("version", "unspecified") if isinstance(raw_dataset, dict) else "unspecified"
    dataset = load_evaluation_dataset(dataset_path)
    report = evaluate_dataset(ArbitrationEngine(persist=False), dataset, dataset_version=version)
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
