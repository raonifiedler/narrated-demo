# Segurança e privacidade

## Dados e repositórios
- **Só dados fictícios** na tela e no roteiro. Antes de gravar, confira as telas (2 ou 3 quadros por clipe) à
  procura de nomes, e-mails, documentos ou caminhos pessoais. Prefira perfil de navegador e pasta de demonstração limpos.
- **Trabalhe numa cópia** do repositório (`git clone <original> <área>/copias/<nome>`). O original não é alterado.
- Contas de teste locais e descartáveis; senhas de teste vêm dos arquivos de seed/exemplo do próprio projeto.

## Serviços e Docker
- **Avise o usuário antes** de subir Docker, bancos ou servidores, e diga quais portas usará. Derrube tudo no fim.
- Use um nome de projeto compose próprio e portas altas para não colidir com o que o usuário já roda.

## Nada sai da máquina sem aprovação
| Ação | Padrão | Para ligar |
| --- | --- | --- |
| TTS em nuvem (edge-tts, serviços pagos) | **desligado** | aprovação explícita do usuário no chat, registrada em `projeto.json` (`nuvem.permitida`, `aprovado_por`, `aprovado_em`) |
| Enviar prints, telas ou vídeo a serviços externos (inclusive IA de terceiros) | proibido | aprovação explícita, por envio |
| Baixar modelos (vozes, Whisper) | só `vdia instalar` (URLs do catálogo, sha256) | o usuário pediu a instalação |
| Página de fonética | só em 127.0.0.1 | não abra para a rede |

TTS em nuvem não é implementado pela skill: o catálogo só documenta as vozes (`vozes.json`, bloco `nuvem`). Se o
usuário aprovar, explique que **o texto do roteiro** vai para o serviço (o edge-tts usa um endpoint não oficial;
termos e estabilidade não garantidos) e mantenha as telas e os dados locais.

HyperFrames (opcional): use só a CLI de render local, com `DO_NOT_TRACK=1` (a eficácia não foi verificada); não faça
login em serviços da HeyGen nem use as skills que sugerem TTS na nuvem.

## Rota desktop com mouse real: trava obrigatória
`vdia.gravar_desktop.SessaoDesktop` não expõe gesto sem trava. Antes de **cada** clique, scroll, arrasto, tecla ou texto:
1. **Tela bloqueada?** (`OpenInputDesktop` + `SwitchDesktop`): aborta.
2. **Cursor onde o script o deixou?** (tolerância de 4 px): senão alguém mexeu no mouse; aborta (`Interferencia`).
3. **Janela sob o cursor e janela da frente são do pid do app?** (`WindowFromPoint`, `GetForegroundWindow`,
   `GetAncestor(GA_ROOT)`): senão o gesto cairia em outro programa; aborta sem tocar (`GestoCancelado`).
4. **FAILSAFE** do PyAutoGUI ligado: levar o cursor ao canto superior esquerdo aborta tudo.

Antes da gravação: `esperar_ocioso(20)` (nenhuma entrada do usuário por 20 s, via `GetLastInputInfo`) e
`trazer_para_frente(hwnd)` (falha = cancela). A gravação cobre só a região do app, recortada à área útil.
Combine o horário com o usuário: durante a gravação o PC fica por conta do script.
A trava é testada sem mouse real (`tests/test_basico.py::test_trava_desktop`, com um sistema falso).
