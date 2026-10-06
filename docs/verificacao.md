# Verificação

O teste local do helper passou em 16 casos. Ele cobre arquivos recentes,
cache em uso, alteração depois do plano, plano expirado, links simbólicos,
projeto Git alterado, metadados de app malformados e reversão de organização.

Os testes de backup usam Git de verdade com um remoto temporário. Eles validam
restauração antes de offload, recusa de repositório público e preservação do
original diante de restauração corrompida. Worktrees com arquivos ignorados
ou commits não enviados são preservados; um worktree antigo, limpo e com todos
os commits no remoto é removido sem force.

O build local da variante OpenClaw passou em Apple Silicon. O serviço Plow
conectou à linha configurada e o proxy do painel respondeu HTTP 200.
O teste de conversa pela CLI carregou a persona e a skill mac-health e retornou
status ok, sem entregar mensagens a destinatários externos.
O teste pela conversa do proprietário passou de ponta a ponta: o iMessage
foi entregue, o OpenClaw invocou plow_run_command e o helper nativo check
retornou exit_code 0 com métricas do Mac. A resposta chegou no iMessage.
O primeiro comando omitiu o caminho de escrita da wiki e foi bloqueado; a nova
invocação declarou esse caminho e passou. A skill agora explicita os dois
diretórios de escrita. A execução completa pela ponte ainda exige validação;
essa tentativa excedeu a espera do handle. Houve também um HTTP 500 transitório
do provedor, recuperado pela repetição automática. As primeiras tentativas pela
CLI tiveram falhas de descoberta/relay MCP. O LaunchAgent local funciona.

O script nativo foi executado no Mac real. Foram coletados inventários, realizada
uma limpeza limitada a cache antigo, organizada uma seleção de arquivos antigos
e validado um backup privado da wiki por clone independente.
Os detalhes e caminhos pessoais ficam somente nos relatórios privados.

O proprietário autorizou o nome Mac Guardian. O slug de publicação é
mac-guardian e a descrição resume as funções solicitadas. A configuração da
publicação fica fora do Git. O reporter oficial é habilitado quando AGENT_ID
está definido. Cadastro, telemetria, imagem pública, deploy de um clique e
saída de WIP exigem confirmações independentes; consulte o registro da publicação.
O GitHub Actions não iniciou o runner. A anotação do GitHub informa pagamentos
recentes falhos ou limite de gastos. Os testes locais permanecem a evidência
executada; não há confirmação de CI verde.

As imagens e o vídeo deste PR mostram uma interface real com inventário
ilustrativo. As métricas de disco e memória foram medidas no Mac. A navegação
do vídeo foi capturada pelo navegador; os nomes e caminhos pessoais não aparecem.
