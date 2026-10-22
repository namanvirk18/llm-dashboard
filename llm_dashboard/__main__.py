import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "llm_dashboard.main:create_app",
        factory=True,
        host="127.0.0.1",
        port=int(os.environ.get("LLM_DASH_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
