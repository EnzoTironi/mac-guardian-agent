# Mac Guardian

Agente de manutenção automática de macOS baseado em OpenClaw e Plow. Ele limpa
conteúdo recriável, atualiza apps fechados e organiza os arquivos pessoais em
uma wiki. O proprietário conversa quando quiser; a rotina trabalha em silêncio.
Latch executa ações do OpenClaw no Mac e o componente local continua a manutenção
mesmo quando o contêiner está parado. Não é necessário acompanhar um dashboard.

O nome público é **Mac Guardian**, com slug `mac-guardian` no Agent Index.
O código deste projeto é MIT. OpenClaw, Plow, Caddy, Mole e Vorssaint mantêm
suas próprias licenças. Mole e Vorssaint não são copiados nem distribuídos aqui.

## O que funciona

- Rotina automática a cada 15 minutos, com armazenamento, memória, swap,
  processos por CPU/RAM, carga, bateria e histórico de até 30 dias.
- Auditoria diária às 09:10 no fuso configurado no Mac.
- Inventário de apps, assinatura, Gatekeeper, Homebrew, App Store quando mas está instalado,
  serviços de inicialização e portas locais.
- Organização física de arquivos estáveis de Downloads, Desktop e
  da raiz pessoal em ~/Wiki, por categoria e assunto. Índices Markdown
  ligam diretamente aos arquivos; assuntos existentes são preservados.
- Renomeação por título e conteúdo de notas, PDFs, documentos Office, OCR local
  de imagens e títulos de mídia. Casos ambíguos ficam para análise do agente.
- Movimentos e renomeações reversíveis, recuperação após interrupção e nomes iguais preservados.
- Atualizações automáticas verificadas de fontes Homebrew oficiais, até três
  por ciclo, com apps e dependências em uso adiados. App Store via mas quando
  disponível; instalações que exigem privilégio/autenticação podem depender do dono.
- Limpeza de caches autorizados com idade mínima de 14 dias; artefatos de projetos
  com 30 dias, lockfile, Git limpo e nenhum arquivo aberto.
- Backup em GitHub privado, com clone independente e SHA-256 antes de offload.
- Relatórios privados em ~/Library/Application Support/MacGuardian/reports, fila persistente para investigação
  de serviços alterados, diagnóstico do próprio agente e pausa por conversa.

Por exemplo, Downloads/Viagens/Italia/roteiro.pdf passa para
~/Wiki/Documentos/Viagens/Italia/roteiro.pdf. Uma nota untitled-3.md cujo título
é “Planejamento da viagem — Itália” recebe planejamento-da-viagem-italia.md.
Uma data explicitamente escrita no documento pode compor o nome.
Um arquivo solto entra na
categoria e no ano correspondente. A rotina aguarda duas horas sem alterações e
verifica arquivos abertos; mantém projetos, vaults existentes, apps, bibliotecas,
links e segredos nos seus caminhos. Documents, Library/Mobile Documents e
Library/CloudStorage ficam excluídos, incluindo aliases que apontem para essas
raízes. A wiki contém os arquivos organizados, além das páginas de navegação.

A CLI inventaria worktrees e remove worktrees Git secundários antigos somente
após atualizar remotos e verificar commits, alterações locais, arquivos ignorados
e locks. Worktrees gerenciados pelo Codex
dependem do arquivamento nativo na conversa proprietária. A rotina não remove esses
diretórios à força. Apps sem fonte de atualização ficam com estado unknown.
As verificações de assinatura e Gatekeeper não comprovam ausência de malware.

## Instalar o componente do Mac

Requer macOS, Python 3.11 ou mais recente e Git. Homebrew, gh e Mole são opcionais
para diagnóstico, mas gh autenticado é necessário para backup.
Poppler (pdftotext), Tesseract e FFmpeg (ffprobe) habilitam os extratores locais:

```sh
brew install poppler tesseract ffmpeg
```

O helper funciona sem esses extratores; nomes que dependem deles ficam pendentes.
O [Tesseract](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html)
usa inglês por padrão. Outros idiomas dependem dos modelos locais instalados.
Para o agente conversar e executar ações, é preciso Docker, Plow e Latch conectado
ao Mac real. Uma instalação fixture do Latch não tem acesso operacional ao Mac.

```sh
git clone --branch v0.2.0 --depth 1 https://github.com/EnzoTironi/mac-guardian-agent.git
cd mac-guardian-agent
python3 -m unittest discover -s tests -v
python3 scripts/install_native.py
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" check --full
```

O instalador não altera a configuração do shell. Ele instala dois LaunchAgents e
preserva a política existente em reinstalações. A desinstalação preserva relatórios,
wiki e backups:

```sh
python3 scripts/install_native.py --uninstall
```

## Configurar e executar o OpenClaw

Use os valores públicos fornecidos pelo proprietário. O script seguinte prepara
o Compose e os argumentos da imagem; ele não cadastra o agente no índice.

```sh
python3 scripts/configure_listing.py \
  --slug seu-slug \
  --name 'Nome do agente' \
  --blurb 'Descrição de uma linha'
```

Instale a CLI oficial Plow seguindo
[plow-agents](https://github.com/plow-pbc/plow-agents).
Quando não houver sessão válida:

```sh
plow-agents login
plow-agents lines
plow-agents deploy --local --line ln_p1
docker compose logs -f agent
```

Escolha uma linha livre; ln_p1 é apenas o exemplo deste setup.
Abra http://localhost:3012 e envie uma mensagem para o número mostrado pela CLI.
Para investigações por modelo, o agente reutiliza automations do Plow na conversa
do proprietário. O componente nativo não depende dessa rotina de conversa.

O contêiner herda o boot e o reporter da base OpenClaw oficial, fixada por digest.
Com AGENT_ID definido, a base registra o índice e reporta uso real a cada cinco
minutos. Sem essa identidade, o reporter não é iniciado. Uma imagem compilada
com identidade vazia precisa ser reconstruída antes da publicação.
Não monte o diretório pessoal, o socket Docker ou credenciais GitHub no contêiner.

## Operar o Mac

```sh
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" check
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" status
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" doctor
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" maintain --dry-run
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" maintain
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" plan
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" clean --apply
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" organize
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" organize --apply
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" rename --apply
```

O plano de limpeza expira em uma hora. Arquivos recentes, diretórios substituídos,
arquivos em uso e checagens inconclusivas são preservados. A organização retorna
uma transação que pode ser revertida com undo. maintain retorna file_transaction
para desfazer organização e nomes daquele ciclo. Para vários ciclos, desfaça
do mais recente ao mais antigo.

A renomeação mantém extensão e pasta, verifica conteúdo e arquivos em uso, e
reconstrói os índices. O agente resolve pending_naming com naming-context e
rename-file --path ARQUIVO --name NOME --sha256 HASH --evidence MOTIVO.
Trechos são limitados, locais e privados; possíveis segredos não são retornados.
Sem evidência de um nome melhor, o nome atual é preservado.

Pela conversa: “como está o Mac?”, “o que ocupou espaço hoje?”, “pause por duas
horas”, “retome a manutenção” ou “desfaça a última organização”. O agente usa
status/history, pause/resume e o journal. Não pede nova autorização para a rotina
já habilitada na política. Investiga exceções e só avisa quando houver risco
confirmado, falta crítica persistente de espaço ou uma decisão do proprietário.

O instalador habilita auto_cleanup, auto_organize, auto_name e auto_updates por padrão e
preserva escolhas existentes. policy.json define raízes, idades, limites,
file_wiki_root, health_wiki_root e os intervalos. Para manter um diagnóstico
sem mutações, use pause. A meta de espaço livre prioriza limpeza; conteúdo
recriável insuficiente exige outra estratégia, sem apagar documentos por impulso.

Mole já oferece prévias oficiais:

```sh
mo clean --dry-run
mo purge --dry-run
mo optimize --dry-run
```

mo clean pode esvaziar a Lixeira e alcançar categorias além da política deste
agente. Use a prévia para decidir sobre uma operação ampla. Vorssaint é tratado
como app nativo; esta versão não presume uma CLI de manutenção dele.

## Backup e offload

Edite backup_roots na política para selecionar a pasta que será enviada.
Crie um repositório privado inicializado. O relatório de saúde já é uma origem autorizada:

```sh
gh repo create SEU_USUARIO/mac-backups --private --add-readme
python3 "$HOME/Library/Application Support/MacGuardian/mac_guardian.py" \
  backup --source "$HOME/Library/Application Support/MacGuardian/reports" --repo SEU_USUARIO/mac-backups
```

Use --offload somente para uma pasta específica autorizada para exclusão.
A wiki ativa e os relatórios não podem ser excluídos pelo offload.
Configure backup_repo para o backup diário do relatório em health_wiki_root.
Essa rotina não envia a wiki de arquivos pessoais inteira ao GitHub. Uma pasta
de documentos ou projetos exige seleção em backup_roots antes do envio.
Segredos, arquivos ocultos, links, hardlinks e arquivos maiores que 45 MiB
bloqueiam esse fluxo. A inspeção de segredos é heurística: revise a origem.
GitHub privado não substitui um backup completo nem criptografia de dados pessoais.

## Publicar no Agent Index

A identidade desta publicação é Mac Guardian (`mac-guardian`). Outros criadores
que publicarem uma variante escolhem seu próprio slug. Depois do teste de resposta
e da conexão real do Latch, compile uma imagem que contenha essa identidade:

```sh
python3 scripts/build_publish.py ghcr.io/SEU_USUARIO/seu-agente:v1
plow-agents image push ghcr.io/SEU_USUARIO/seu-agente:v1
plow-agents profile --show
```

O build padrão é linux/amd64 para Plow. Para testar localmente em Apple Silicon,
use --platform linux/arm64. Mantenha a imagem pública e guarde o digest impresso.
Um administrador habilita o primeiro deploy de um clique após receber UID, slug
e digest em [Discord do Agent Index](https://aiworthusing.com/discord).

Registre o vídeo, a imagem e o guia pelo
[cliente oficial](https://github.com/plow-pbc/agent-index-client).
Os campos --video, --image e --install-url do cliente têm formatos próprios;
consulte --help antes de usar. Depois, envie repositório, commit e ID na
[thread de verificação](https://discord.com/channels/1519035948191449268/1549100840583700481).
A equipe Plow remove WIP após validar. A criação do repositório e o build local
não equivalem à publicação ou à retirada de WIP.

## Dados e revisão

private/, plow-credentials e .env ficam fora do Git e do contexto Docker.
Os relatórios reais contêm nomes e caminhos pessoais e permanecem no Mac.
Evidências destinadas à publicação usam arquivos de exemplo e resultados de teste.
PRs deste projeto recebem imagens e vídeos com gh --attach.

Os testes exercitam limpeza, arquivos abertos, alterações depois do plano,
links simbólicos, reversão de organização e backup/restauração antes de offload.
```sh
python3 -m unittest discover -s tests -v
```
