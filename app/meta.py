import asyncio
import re

import httpx


class MetaError(Exception):
    def __init__(self, message, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


class MetaClient:
    def __init__(self, settings, transport=None, poll_seconds=3, poll_attempts=20):
        self.settings = settings
        self.transport = transport
        self.poll_seconds = poll_seconds
        self.poll_attempts = poll_attempts

    async def request(self, method, path, data=None, publishing=False):
        try:
            async with httpx.AsyncClient(
                base_url=f"https://graph.facebook.com/{self.settings.api_version}/",
                headers={"Authorization": f"Bearer {self.settings.meta_token}"},
                timeout=30, transport=self.transport,
            ) as client:
                response = await client.request(method, path, params=data if method == "GET" else None,
                                                data=data if method == "POST" else None)
            try:
                payload = response.json()
            except ValueError:
                raise MetaError("A Meta retornou uma resposta inválida.", uncertain=publishing)
            if not isinstance(payload, dict):
                raise MetaError("Formato inesperado da resposta da Meta.", uncertain=publishing)
            if response.is_error or "error" in payload:
                error = payload.get("error", {})
                code = error.get("code") if isinstance(error, dict) else None
                # Mensagens externas podem conter tokens ou URLs. Exponha apenas códigos numéricos.
                label = f" (código {code})" if isinstance(code, int) else ""
                hint = "Confira token, permissões, conta profissional e imagem pública."
                if code == 190:
                    hint = "O token expirou ou foi recusado. Atualize META_ACCESS_TOKEN nas configurações seguras."
                elif code in {4, 17, 32, 613}:
                    hint = "Limite da Meta atingido. Aguarde antes de tentar novamente."
                raise MetaError(f"A Meta recusou a solicitação{label}. {hint}", uncertain=publishing and response.status_code >= 500)
            return payload
        except httpx.HTTPError:
            raise MetaError("Falha de conexão com a Meta. Verifique rede e disponibilidade.", uncertain=publishing) from None

    async def account(self):
        return await self.request("GET", self.settings.instagram_id, {"fields": "id,username,media_count"})

    async def create_container(self, post):
        data = await self.request("POST", f"{self.settings.instagram_id}/media", {
            "image_url": f"{self.settings.public_url}/media/{post['image']}",
            "caption": post["caption"], "alt_text": post["alt_text"],
        })
        return self.identifier(data)

    @staticmethod
    def identifier(data, publishing=False):
        value = data.get("id")
        if not isinstance(value, str) or not re.fullmatch(r"\d+", value):
            raise MetaError("A Meta não retornou um identificador válido.", uncertain=publishing)
        return value

    async def publish(self, container_id):
        for _ in range(self.poll_attempts):
            data = await self.request("GET", container_id, {"fields": "status_code"})
            status = data.get("status_code")
            if status == "FINISHED":
                break
            if status == "PUBLISHED":
                raise MetaError("O contêiner já consta como publicado. Confira o Instagram.", uncertain=True)
            if status in {"ERROR", "EXPIRED"}:
                raise MetaError("A Meta não conseguiu processar a imagem. Revise a mídia e gere um novo rascunho.")
            await asyncio.sleep(self.poll_seconds)
        else:
            raise MetaError("O processamento da imagem ainda não terminou. Aguarde antes de tentar novamente.")
        data = await self.request("POST", f"{self.settings.instagram_id}/media_publish",
                                  {"creation_id": container_id}, publishing=True)
        return self.identifier(data, publishing=True)
