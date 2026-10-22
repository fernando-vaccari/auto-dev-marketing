# Referências técnicas consultadas

Consulta em 22/10/2026, com HTTPS e verificação TLS. URLs públicas; nenhum token enviado à pesquisa.

| Área | Fonte | O que foi usado |
| --- | --- | --- |
| Meta | https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/content-publishing/ | Facebook Login for Business, permissões, contêiner REELS, sessão resumível, rupload local, consulta de processamento e media_publish |
| Amostra Meta | https://github.com/fbsamples/reels_publishing_apis/tree/main/insta_reels_publishing_api_sample | Referência oficial de publicação de Reels |
| OBS v5 | https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md | Hello/Identify/Identified, desafio SHA-256, GetSourceActive, cenas/fontes e StartRecord/StopRecord/SetRecordDirectory; este último exige suporte introduzido no v5.3 |
| Câmera Roblox | https://github.com/Roblox/creator-docs/blob/main/content/en-us/reference/engine/classes/Camera.yaml | CurrentCamera, CameraType Scriptable, CFrame, FieldOfView e CameraSubject |
| Kokoro | https://github.com/hexgrad/kokoro | Suporte documentado a português brasileiro, pesos Apache e biblioteca de inferência |
| Licença Kokoro | https://github.com/hexgrad/kokoro/blob/main/LICENSE | Apache 2.0 |
| Kokoro ONNX | https://github.com/thewh1teagle/kokoro-onnx | Integração CPU, API e classificação do modelo como Apache 2.0 |
| Licença ONNX wrapper | https://github.com/thewh1teagle/kokoro-onnx/blob/main/LICENSE | MIT |
| Pesos fixos | https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.1 | Arquivos kokoro-v1.0.onnx e voices-v1.0.bin, baixados e hashes registrados no instalador |
| Piper atual | https://github.com/OHF-Voice/piper1-gpl/blob/main/COPYING | GPL 3 do motor; não substitui a licença individual de uma voz |

Os hashes SHA-256 no instalador foram calculados a partir dos arquivos obtidos do release público citado via TLS e são conferidos nas instalações seguintes. Não são apresentados como assinatura digital do autor. Pesos e dependências não são copiados para o Git ou ZIP.

O proxy deste ambiente recusou o acesso a Hugging Face e create.roblox.com. A referência oficial de câmera foi acessada no repositório Roblox/creator-docs; pesos Kokoro e termos puderam ser obtidos pelas fontes GitHub acima. O cartão individual de vozes Piper não pôde ser verificado, por isso nenhuma voz Piper é recomendada como comercialmente liberada nesta entrega. Não se desativou TLS, assinatura ou checksum para contornar a restrição.

Verificar uma documentação não equivale a testar uma conta Meta real, OBS real com um jogo ou Roblox Studio. Essas validações continuam explicitamente externas.
