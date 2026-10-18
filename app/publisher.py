import asyncio
import logging

from .meta import MetaClient, MetaError

logger = logging.getLogger(__name__)


class Publisher:
    def __init__(self, settings, db, meta=None):
        self.settings, self.db = settings, db
        self.meta = meta or MetaClient(settings)
        self.automator = None

    async def publish(self, post_id, due=False):
        post = self.db.claim(post_id, self.settings.delivery_key, due=due)
        if not post:
            return None
        try:
            if not (self.settings.data_dir / "media" / post["image"]).is_file():
                raise MetaError("A imagem não está disponível. Edite o rascunho para gerar outra arte.")
            if self.settings.mode == "demo":
                self.db.finish(post_id, "simulated")
            else:
                container_id = post["container_id"]
                if not container_id:
                    container_id = await self.meta.create_container(post)
                    self.db.save_container(post_id, container_id)
                media_id = await self.meta.publish(container_id)
                self.db.finish(post_id, "published", media_id=media_id)
        except MetaError as exc:
            self.db.finish(post_id, "review_required" if exc.uncertain else "failed", error=str(exc))
        except asyncio.CancelledError:
            self.db.finish(post_id, "review_required", error="Envio interrompido. Confira o Instagram antes de publicar novamente.")
            raise
        except Exception:
            # Não registre requisições, respostas ou segredos em logs.
            logger.error("Falha interna ao processar publicação %s", post_id)
            self.db.finish(post_id, "review_required", error="Falha interna durante envio. Confira o Instagram antes de criar outro rascunho.")
        return self.db.get(post_id)

    async def tick(self):
        for post_id in self.db.due(self.settings.delivery_key):
            await self.publish(post_id, due=True)

    async def run(self):
        while True:
            try:
                if self.automator:
                    await self.automator.tick()
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("Falha na fila; nova verificação ocorrerá no próximo ciclo.")
            await asyncio.sleep(self.settings.scheduler_seconds)
