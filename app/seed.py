"""Cria três rascunhos de demonstração sem fazer chamadas externas."""
from dataclasses import replace
import asyncio

from .config import Settings
from .content import generate_content, render_image
from .db import Database


async def main():
    config = Settings.from_env()
    if config.mode != "demo":
        raise SystemExit("Rascunhos de exemplo só podem ser criados em APP_MODE=demo.")
    config = replace(config, ai_key="")
    db = Database(config.data_dir)
    if db.posts():
        print("Já existem conteúdos; nenhum rascunho foi alterado.")
        return
    brand = db.brand()
    for topic, objective in [
        ("Consistência vale mais que inspiração", "educate"),
        ("Seu conteúdo começa com uma boa conversa", "engage"),
        ("Transforme sua presença digital em conexão", "sell"),
    ]:
        content = await generate_content(config, brand, topic, objective)
        image = render_image(config.data_dir / "media", brand, content["title"])
        db.create(image=image, **content)
    print("Três rascunhos criados para Auto Posts. Nenhuma publicação ou aprovação realizada.")


if __name__ == "__main__":
    asyncio.run(main())
