from __future__ import annotations

from splitter.api import create_app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000, access_log=False)
