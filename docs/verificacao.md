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

O script nativo foi executado no Mac real. Foram coletados inventários, realizada
uma limpeza limitada a cache antigo, organizada uma seleção de arquivos antigos
e validado um backup privado da wiki por clone independente.
Os detalhes e caminhos pessoais ficam somente nos relatórios privados.

O Agent Index ainda depende da identidade fornecida pelo proprietário. AGENT_ID
vazio desativa o reporter oficial, conforme contrato da base. Build e teste local
não certificam cadastro, telemetria publicada, deploy de um clique ou saída de WIP.

As imagens e o vídeo deste PR mostram uma interface real com inventário
ilustrativo. As métricas de disco e memória foram medidas no Mac. A navegação
do vídeo foi capturada pelo navegador; os nomes e caminhos pessoais não aparecem.
