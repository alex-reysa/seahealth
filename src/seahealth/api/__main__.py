"""``python -m seahealth.api`` — run the FastAPI stub on port 8000."""
import uvicorn


def main() -> None:
    uvicorn.run("seahealth.api.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
