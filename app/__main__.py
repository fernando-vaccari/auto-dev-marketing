import os
import uvicorn

if __name__ == "__main__":
    host = os.getenv("APP_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost", "::1"} and not os.getenv("APP_PASSWORD"):
        raise SystemExit("Defina APP_PASSWORD antes de expor o servidor na rede.")
    uvicorn.run("app.main:create_app", factory=True, host=host,
                port=int(os.getenv("APP_PORT", "8000")), workers=1,
                proxy_headers=False, access_log=False)
