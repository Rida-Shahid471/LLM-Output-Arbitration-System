import argparse
from src.config import settings
from src.logging_config import setup_logging
from src.workflow import ArbitrationEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a candidate LLM answer.")
    parser.add_argument("--prompt", help="Original user prompt")
    parser.add_argument("--answer", help="Candidate LLM answer")
    args = parser.parse_args()
    setup_logging(settings.log_level)
    if bool(args.prompt) != bool(args.answer):
        parser.error("--prompt and --answer must be supplied together.")
    if not args.prompt:
        args.prompt = "What is the capital of Australia?"
        args.answer = "The capital of Australia is Sydney."
    result = ArbitrationEngine().arbitrate(args.prompt, args.answer)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
