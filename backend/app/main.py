from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.routes import router as api_router
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except Exception:
        pass

    # Warm up Ollama model at startup with tiny request (1 token)
    try:
        from app.llm.factory import get_llm
        llm = get_llm()
        if llm.provider == "ollama":
            import httpx
            with httpx.Client(timeout=30.0) as client:
                client.post(
                    f"{llm.base_url}/api/generate",
                    json={
                        "model": llm.model,
                        "prompt": "hi",
                        "options": {"num_predict": 1},
                        "keep_alive": "60m",
                    },
                )
    except Exception:
        pass

    yield


app = FastAPI(title="The Lenny Growth Assistant", lifespan=lifespan)

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_cors_headers(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin")
    headers = {}
    if origin and (origin in ALLOWED_ORIGINS or "*" in ALLOWED_ORIGINS):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Access-Control-Allow-Methods"] = "*"
        headers["Access-Control-Allow-Headers"] = "*"
    return headers


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code_map = {
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_409_CONFLICT: "CONFLICT",
        422: "UNPROCESSABLE_ENTITY",
    }
    code = code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": str(exc.detail)}},
        headers=_get_cors_headers(request),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    msg = errors[0].get("msg", "Validation error") if errors else "Validation error"
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": msg}},
        headers=_get_cors_headers(request),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_SERVER_ERROR", "message": str(exc)}},
        headers=_get_cors_headers(request),
    )


app.include_router(api_router)
