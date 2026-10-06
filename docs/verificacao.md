# Verificação da versão 0.2.0

Os 52 testes locais passaram. Eles exercitam limpeza com revalidação de idade,
conteúdo e arquivos em uso; preservação de projetos, links e worktrees; escrita
privada; backup com Git real, clone independente e restauração antes de offload.
Também cobrem organização física, nomes iguais, interrupção entre link e remoção,
reversão de nomes e locais, índices que preservam páginas pessoais, exclusão de
Documents e aliases cloud, atualizações verificadas, pausa e filas de revisão.

A renomeação foi testada com títulos Markdown, metadados Office, texto de PDF,
OCR local e títulos de mídia. Datas inválidas são ignoradas. Conteúdo com possíveis
segredos não aparece no contexto. O hash da análise precisa continuar igual na
execução. Arquivos sem mudanças reutilizam observações; arquivos alterados são
analisados novamente. Uma revisão concluída não volta à fila apenas porque o
novo nome difere de uma sugestão mecânica.

scripts/demo_wiki.py executou maintain e undo em um diretório temporário com
arquivos sintéticos. Cinco arquivos foram organizados; uma nota recebeu o nome
pelo título. Os cinco voltaram aos nomes e locais originais, com hashes iguais.
Um projeto e um arquivo recente permaneceram no lugar. A imagem e o vídeo da
versão 0.2 mostram essas saídas reais no navegador. O vídeo é uma gravação da
navegação pelos resultados, sem documentos pessoais ou atualização de apps.
Tesseract foi executado sobre a imagem e reconheceu o nome derivado do título.

No Mac real, a wiki foi movida para ~/Wiki. Documents e as raízes cloud estão
excluídas da política. Um ciclo da versão 0.2 organizou 100 arquivos, renomeou
43 e verificou três atualizações de pacotes. Cada movimentação tem um journal;
esses arquivos pessoais não aparecem nas evidências públicas. A auditoria
completa local foi atualizada; fontes de atualização desconhecidas continuam
pendentes e assinaturas não são um veredito antimalware.

Os dois LaunchAgents executam maintain a cada 15 minutos e check --full às
09:10. A rotina nativa continua sem Docker. Ela preserva a política e o estado
nas reinstalações. O acompanhamento por modelo investiga as filas sem enviar
relatórios de rotina ou pedir aprovação para cada tarefa já autorizada.

OpenClaw retornou health ok. O teste de experiência pela CLI, sem ferramentas
nem entrega a contatos, respondeu em português sobre manutenção automática,
wiki fora de Documents, nomes pelo conteúdo e interação apenas nas exceções.
O boot Plow e o reporter oficial de cinco minutos permanecem herdados da base;
a identidade de telemetria foi preservada na recriação do contêiner.

O teste anterior pela conversa do proprietário passou de ponta a ponta:
iMessage, comando nativo por Latch com exit code 0 e resposta na conversa.
A auditoria completa por essa ponte permanece sem validação: uma tentativa
anterior excedeu a espera do handle. A auditoria local não prova essa integração.
Restrições de fixture e permissões do Latch continuam sendo respeitadas.

O workflow de GitHub Actions executa a mesma suíte em Python 3.12 no Ubuntu.
A execução da versão 0.1 passou; o resultado do commit atual fica nos checks do
PR. Imagens e vídeos de revisão são anexados com gh --attach. O código é MIT;
relatórios, configurações de publicação e credenciais ficam fora do Git e Docker.
Deploy de um clique e retirada de WIP dependem da equipe Plow.
