from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
import asyncio
import fcntl
import hashlib
import hmac
import io
import os
import secrets
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, ConfigDict

from .automation import Automation, next_run
from .config import Settings
from .content import ContentError, generate_content, render_image
from .db import Database
from .meta import MetaError
from .reels.api import router as reels_router
from .reels.service import ReelService
from .reels.tools import ReelError
from .publisher import Publisher

WEB = Path(__file__).parent / "web"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Brand(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    segment: str = Field(min_length=1, max_length=100)
    audience: str = Field(min_length=1, max_length=200)
    tone: str = Field(min_length=1, max_length=100)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    cta: str = Field(min_length=1, max_length=200)
    signature: str = Field(max_length=100, default="")


class Generate(StrictModel):
    topic: str = Field(min_length=3, max_length=300)
    objective: str = Field(pattern=r"^(educate|engage|sell)$", default="educate")


class PostEdit(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    caption: str = Field(min_length=1, max_length=2200)
    alt_text: str = Field(min_length=1, max_length=1000)
    regenerate_image: bool = False


class Approval(StrictModel):
    approved: bool


class Schedule(Approval):
    scheduled_at: datetime


class Login(StrictModel):
    password: str = Field(max_length=1024)


class AutomationConfig(StrictModel):
    enabled: bool
    time: str = Field(pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    days: list[int] = Field(min_length=1, max_length=7)
    topics: list[str] = Field(min_length=1, max_length=14)
    objective: str = Field(pattern=r'^(educate|engage|sell)$')
    approved: bool = False


def create_app(settings=None, *, scheduler=True, meta=None, reels_worker=True):
    config = settings or Settings.from_env()
    config.validate()
    db = Database(config.data_dir)
    media = config.data_dir / "media"
    media.mkdir(exist_ok=True)
    publisher = Publisher(config, db, meta=meta)
    publisher.automator = Automation(config, db, publisher)
    key_path = config.data_dir / "session.key"
    try:
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        session_key = key_path.read_bytes()
    else:
        with os.fdopen(fd, "wb") as file:
            session_key = secrets.token_bytes(32)
            file.write(session_key)
    session_key = hmac.new(session_key, config.password.encode(), hashlib.sha256).digest()
    reels = ReelService(config)
    attempts = defaultdict(deque)

    @asynccontextmanager
    async def lifespan(app):
        lock = None
        task = None
        if scheduler:
            lock = (config.data_dir / "worker.lock").open("a")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock.close()
                raise RuntimeError("Já existe um processo usando DATA_DIR. Execute com um único worker.") from None
            db.recover_interrupted()
            task = asyncio.create_task(publisher.run())
        try:
            if config.password and reels_worker:
                await reels.start()
            yield
        finally:
            await reels.close()
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if lock:
                lock.close()

    app = FastAPI(title="Auto Posts", version="1.0.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db, app.state.publisher, app.state.settings = db, publisher, config

    app.state.reels = reels
    app.include_router(reels_router(reels))

    @app.exception_handler(ReelError)
    async def reels_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    def signed_session():
        stamp = str(int(time.time()))
        signature = hmac.new(session_key, stamp.encode(), hashlib.sha256).hexdigest()
        return f"{stamp}.{signature}"

    def authenticated(request):
        if not config.password:
            return True
        try:
            stamp, signature = request.cookies.get("session", "").split(".")
            age = time.time() - int(stamp)
            expected = hmac.new(session_key, stamp.encode(), hashlib.sha256).hexdigest()
            return 0 <= age < 43200 and hmac.compare_digest(signature, expected)
        except (ValueError, TypeError):
            return False

    @app.middleware("http")
    async def security(request, call_next):
        path = request.url.path
        if (path == "/api/reels" or path.startswith("/api/reels/")) and not config.password:
            return JSONResponse({"detail": "Configure APP_PASSWORD e entre no painel para usar o Estúdio de Reels."}, status_code=503)
        public = path in {"/health", "/login", "/api/login"} or path.startswith(("/media/", "/static/"))
        if not public and not authenticated(request):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Entre para continuar."}, status_code=401)
            return RedirectResponse("/login", status_code=303)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            allowed = {str(request.base_url).rstrip("/")}
            if config.public_url:
                allowed.add(config.public_url)
            if origin and origin not in allowed:
                return JSONResponse({"detail": "Origem da solicitação recusada."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' blob: data:; script-src 'self'; style-src 'self'; connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if path.startswith("/api/") or path in {"/", "/login"}:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def invalid_value(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.get("/health")
    async def health():
        with db.connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"status": "ok"}

    @app.get("/")
    async def index():
        return FileResponse(WEB / "index.html")

    @app.get("/login")
    async def login_page():
        if not config.password:
            return RedirectResponse("/", status_code=303)
        return FileResponse(WEB / "login.html")

    @app.post("/api/login")
    async def login(body: Login, request: Request):
        ip = request.client.host if request.client else "unknown"
        history = attempts[ip]
        while history and history[0] < time.monotonic() - 60:
            history.popleft()
        if len(history) >= 5:
            raise HTTPException(429, "Muitas tentativas. Aguarde um minuto.")
        if not config.password or not hmac.compare_digest(body.password.encode(), config.password.encode()):
            history.append(time.monotonic())
            raise HTTPException(401, "Senha incorreta.")
        history.clear()
        response = JSONResponse({"ok": True})
        response.set_cookie("session", signed_session(), max_age=43200, httponly=True,
                            secure=config.mode == "live", samesite="strict")
        return response

    @app.post("/api/logout")
    async def logout():
        response = JSONResponse({"ok": True})
        response.delete_cookie("session")
        return response

    @app.get("/api/status")
    async def status():
        return {"mode": config.mode, "timezone": config.timezone,
                "ai_enabled": bool(config.ai_key), "auth_enabled": bool(config.password),
                "meta_configured": bool(config.meta_token and config.instagram_id),
                "public_url_configured": bool(config.public_url),
                "api_version": config.api_version}

    @app.get("/api/brand")
    async def brand():
        return db.brand()

    @app.put("/api/brand")
    async def save_brand(body: Brand):
        db.save_brand(body.model_dump())
        return db.brand()

    @app.get("/api/posts")
    async def posts():
        return db.posts()

    @app.get("/api/events")
    async def events():
        return db.events()

    @app.get('/api/automation')
    async def automation():
        rule = db.automation()
        return {**rule, 'next_run': next_run(config, rule), 'runs': db.automation_runs(),
                'active': rule['enabled'] and rule.get('target') == config.delivery_key}

    @app.put('/api/automation')
    async def save_automation(body: AutomationConfig):
        if any(day < 0 or day > 6 for day in body.days) or len(set(body.days)) != len(body.days):
            raise HTTPException(422, 'Escolha dias da semana válidos, sem repetição.')
        topics = [topic.strip() for topic in body.topics]
        if any(not 3 <= len(topic) <= 160 for topic in topics):
            raise HTTPException(422, 'Cada tema deve conter de 3 a 160 caracteres.')
        if body.enabled and not body.approved:
            raise HTTPException(422, 'Autorize a criação e o envio automático antes de ativar a rotina.')
        rule = body.model_dump(exclude={'approved'})
        rule.update(topics=topics, approved_at=datetime.now(timezone.utc).isoformat() if body.enabled else None,
                    mode=config.mode, target=config.delivery_key)
        db.save_automation(rule)
        return await automation()

    def find(post_id):
        post = db.get(post_id)
        if not post:
            raise HTTPException(404, "Publicação não encontrada.")
        return post

    @app.post("/api/posts/generate", status_code=201)
    async def generate(body: Generate):
        current_brand = db.brand()
        try:
            content = await generate_content(config, current_brand, body.topic, body.objective)
        except ContentError as exc:
            raise HTTPException(502, str(exc)) from None
        image = await asyncio.to_thread(render_image, media, current_brand, content["title"])
        return db.create(image=image, **content)

    @app.put("/api/posts/{post_id}")
    async def edit(post_id: str, body: PostEdit):
        post = find(post_id)
        fields = body.model_dump(exclude={"regenerate_image"})
        # O título da arte sempre acompanha alterações no título do rascunho.
        if body.regenerate_image or body.title != post["title"]:
            fields["image"] = await asyncio.to_thread(render_image, media, db.brand(), body.title)
        return db.edit(post_id, fields)

    @app.post("/api/posts/{post_id}/image")
    async def upload_image(post_id: str, request: Request):
        post = find(post_id)
        if post["status"] not in {"draft", "scheduled", "failed"}:
            raise HTTPException(409, "Esta publicação não pode ser editada.")
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > 8_000_000:
                raise HTTPException(413, "Imagem muito grande. Limite: 8 MB.")
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("format")
                if not 320 <= image.width <= 14400 or image.height < 320 or image.width * image.height > 40_000_000:
                    raise ValueError("dimensions")
                ratio = image.width / image.height
                if not 0.8 <= ratio <= 1.91:
                    raise ValueError("ratio")
                image.load()
                image = image.convert("RGB")
                image.thumbnail((1080, 1350))
                filename = uuid.uuid4().hex + ".jpg"
                image.save(media / filename, "JPEG", quality=92, optimize=True)
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
            raise HTTPException(422, "Use JPEG, PNG ou WebP entre 4:5 e 1,91:1, com pelo menos 320 px e até 40 MP.") from None
        return db.edit(post_id, {"image": filename})

    @app.post("/api/posts/{post_id}/schedule")
    async def schedule(post_id: str, body: Schedule):
        find(post_id)
        if not body.approved:
            raise HTTPException(422, "Aprove o conteúdo antes de agendar.")
        if body.scheduled_at.tzinfo is None:
            raise HTTPException(422, "Informe data e hora com fuso horário.")
        when = body.scheduled_at.astimezone(timezone.utc)
        if when <= datetime.now(timezone.utc) + timedelta(seconds=5):
            raise HTTPException(422, "Escolha uma data pelo menos 5 segundos no futuro.")
        return db.schedule(post_id, when.isoformat(), config.delivery_key)

    @app.post("/api/posts/{post_id}/cancel")
    async def cancel(post_id: str):
        find(post_id)
        return db.cancel(post_id)

    @app.post("/api/posts/{post_id}/publish")
    async def publish(post_id: str, body: Approval):
        find(post_id)
        if not body.approved:
            raise HTTPException(422, "Aprove o conteúdo antes de publicar.")
        result = await publisher.publish(post_id)
        if result is None:
            raise HTTPException(409, "Publicação já enviada ou indisponível. Cancele o agendamento antes de enviar agora.")
        return result

    @app.post("/api/meta/test")
    async def meta_test():
        if not config.meta_token or not config.instagram_id:
            raise HTTPException(409, "Configure META_ACCESS_TOKEN e INSTAGRAM_ACCOUNT_ID nas variáveis seguras do servidor.")
        try:
            account = await publisher.meta.account()
        except MetaError as exc:
            raise HTTPException(502, str(exc)) from None
        return {"id": account.get("id"), "username": account.get("username"), "media_count": account.get("media_count")}

    app.mount("/static", StaticFiles(directory=WEB), name="static")
    app.mount("/media", StaticFiles(directory=media), name="media")
    return app
