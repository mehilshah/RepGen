import os

from repgen import reproduce


def main():
    # define inputs
    bug_report_source = "https://github.com/example/repo/issues/1"
    repo_source = "https://github.com/example/repo"
    backend = "openai"
    model = "gpt-4o"
    api_key = os.environ.get("OPENAI_API_KEY", "your-api-key-here")

    print("Running RepGen reproduction...")

    try:
        # Simple one-function usage
        code_snippet = reproduce(
            bug_report_source=bug_report_source,
            repo_source=repo_source,
            backend=backend,
            model=model,
            api_key=api_key,
        )

        print("\n=== Generated Reproduction Script ===\n")
        print(code_snippet)
        print("\n=====================================\n")

    except Exception as e:
        print("Error: {}".format(e))


if __name__ == "__main__":
    main()
