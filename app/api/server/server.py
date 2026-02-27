"""
FastAPI server for hosting local LLMs via llama.cpp (Vulkan GPU support)

Endpoints:
  POST /api/generate - Text generation
  GET  /health       - System status

Models (place in ./models/):
  - qwen2.5-1.5b-instruct-q8_0.gguf  (lightweight)
  - Qwen2.5-14B-Instruct-Q5_K_M.gguf (heavy, optional)

Run:
  cd app/api/server
  fastapi run server.py --port 8000
"""

import logging
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional
from api.controllers.fact_check import router as fact_check_router

import psutil
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from llama_cpp import Llama
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

USERNAME = "admin"
PASSWORD = "your_secure_password_here"

security = HTTPBasic()


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, USERNAME)
    correct_password = secrets.compare_digest(credentials.password, PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


class GenerateRequest(BaseModel):
    prompt: str
    system: str = "You are a helpful assistant"
    model: str = "heavy"        # "lightweight" or "heavy"
    max_tokens: int = 2000
    temperature: float = 0.2
    top_p: float = 0.9
    top_k: int = 50
    repeat_penalty: float = 1.1


class GenerateResponse(BaseModel):
    response: str
    model_used: str
    tokens_generated: int
    processing_time_ms: float


class HealthResponse(BaseModel):
    status: str
    models_loaded: List[str]
    cpu_percent: float
    ram_used_gb: float
    ram_total_gb: float


class ModelManager:
    def __init__(self):
        self.lightweight_model: Optional[Llama] = None
        self.heavy_model: Optional[Llama] = None
        self.models_loaded: List[str] = []
        self.models_path = Path("./models")
        self.models_path.mkdir(exist_ok=True)

    def _find_model(self, model_type: str) -> Optional[Path]:
        gguf_files = list(self.models_path.glob("*.gguf"))
        if not gguf_files:
            return None

        if model_type == "lightweight":
            for f in gguf_files:
                if "1.5b" in f.name.lower() or "lightweight" in f.name.lower():
                    return f

        if model_type == "heavy":
            for f in gguf_files:
                if "14b" in f.name.lower() or "heavy" in f.name.lower():
                    return f

        return gguf_files[0]

    def _load(self, model_path: Path) -> Llama:
        return Llama(
            model_path=str(model_path),
            n_ctx=16384,
            n_threads=psutil.cpu_count(logical=True),
            n_gpu_layers=-1,
            verbose=False,
            chat_format="chatml",
            seed=42,
        )

    def load_models(self):
        gguf_files = list(self.models_path.glob("*.gguf"))
        if not gguf_files:
            raise FileNotFoundError("No GGUF models found in ./models directory")

        for f in gguf_files:
            logger.info(f"  - {f.name} ({f.stat().st_size / (1024**3):.2f} GB)")

        lightweight_path = self._find_model("lightweight")
        heavy_path = self._find_model("heavy")

        if lightweight_path:
            logger.info(f"Loading lightweight model: {lightweight_path.name}")
            self.lightweight_model = self._load(lightweight_path)
            self.models_loaded.append(lightweight_path.name)

        if heavy_path and heavy_path != lightweight_path:
            logger.info(f"Loading heavy model: {heavy_path.name}")
            self.heavy_model = self._load(heavy_path)
            self.models_loaded.append(heavy_path.name)
        else:
            logger.info("No separate heavy model - reusing lightweight")
            self.heavy_model = self.lightweight_model

    def generate(self, prompt: str, system: str, model_name: str,
                 max_tokens: int, temperature: float,
                 top_p: float, top_k: int, repeat_penalty: float) -> str:
        model = self.lightweight_model if model_name == "lightweight" else self.heavy_model

        if model is None:
            raise RuntimeError(f"Model '{model_name}' not loaded")

        output = model.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            repeat_penalty=repeat_penalty,
        )

        return output["choices"][0]["message"]["content"].strip()


model_manager = ModelManager()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting server - loading models.")
    model_manager.load_models()
    logger.info("Server ready!")
    yield


app = FastAPI(title="Local LLM Server", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(fact_check_router)

@app.get("/health", response_model=HealthResponse)
async def health_check():
    ram = psutil.virtual_memory()
    return HealthResponse(
        status="healthy" if model_manager.models_loaded else "degraded",
        models_loaded=model_manager.models_loaded,
        cpu_percent=psutil.cpu_percent(interval=1),
        ram_used_gb=ram.used / (1024**3),
        ram_total_gb=ram.total / (1024**3),
    )


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest, username: str = Depends(verify_credentials)):
    start_time = time.time()

    response = model_manager.generate(
        prompt=request.prompt,
        system=request.system,
        model_name=request.model,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p,
        top_k=request.top_k,
        repeat_penalty=request.repeat_penalty,
    )

    return GenerateResponse(
        response=response,
        model_used=request.model,
        tokens_generated=len(response.split()),
        processing_time_ms=(time.time() - start_time) * 1000,
    )


@app.get("/")
async def root():
    return {
        "service": "Local LLM Server",
        "version": "1.0.0",
        "models_loaded": model_manager.models_loaded,
        "status": "ready" if model_manager.models_loaded else "loading",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")