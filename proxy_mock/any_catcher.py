from proxy_mock.app import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("any_catcher:app", port=5000, log_level="info", reload=True)
