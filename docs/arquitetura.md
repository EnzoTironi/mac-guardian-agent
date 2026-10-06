# Arquitetura

O contêiner OpenClaw mantém a conversa, as ferramentas Plow e o registro de uso.
Latch transmite operações ao Mac de acordo com suas permissões. O helper Python
do Mac executa os comandos de manutenção, controla o escopo e guarda resultados.

O componente local executa maintain a cada 15 minutos e check --full às 09:10.
Os jobs são de sessão do usuário. Eles não rodam quando o Mac está desligado;
launchd retoma no login ou após o despertar conforme suas regras.
Nenhum desses jobs chama um modelo nem envia dados ao Agent Index.

maintain coleta saúde, aplica a limpeza com plano novo, organiza arquivos
estáveis, renomeia pelo conteúdo, atualiza pacotes compatíveis e executa o backup operacional configurado.
Cada etapa registra seu resultado. Um lock impede workers concorrentes; status,
history e doctor continuam acessíveis durante o trabalho. pause mantém o
monitoramento e suspende mutações. As etapas retomam em ciclos futuros.

A wiki pessoal contém os arquivos em file_wiki_root/categoria/assunto. Páginas
geradas apontam para esses arquivos e nunca sobrescrevem notas pessoais. Fontes
com Git, manifestos de projetos ou vaults são preservadas. O relatório de saúde
em health_wiki_root é separado e pode receber backup automático; a organização
não habilita upload do conteúdo pessoal.
A raiz padrão é ~/Wiki, fora de Documents. Documents, Mobile Documents e
CloudStorage estão excluídos também quando acessados por aliases.

A extração de nomes lê até 64 KiB de texto, títulos Office ou a primeira página
de PDFs. Tesseract lê imagens localmente e ffprobe consulta títulos de mídia.
Títulos com evidência suficiente viram nomes descritivos; assuntos existentes e
datas explícitas refinam o nome. Casos ambíguos ficam numa fila privada para o
agente interpretar por naming-context e aplicar com SHA-256 e justificativa.
As observações sem conteúdo evitam reler arquivos inalterados em todo ciclo.
Projetos e índices gerados não são renomeados.

A política local controla raízes, idade e limites. A limpeza exige um plano
recente e repete as verificações imediatamente antes de remover. Projetos
alterados e worktrees gerenciados são preservados. A organização usa hardlinks
temporários no mesmo volume para publicar um destino sem sobrescrever arquivo.
O registro contém origem, destino e hash para desfazer a movimentação e o nome.
Organização e renomeação no mesmo ciclo compartilham uma transação de reversão.

Um backup é um snapshot novo dentro de repositório privado. O helper clona,
envia, clona novamente e compara hashes. A exclusão local exige a opção offload,
uma origem autorizada e nova validação. Um recibo verificado é salvo antes de
começar a excluir, e cada arquivo removido tem um registro.
Uma falha durante offload pode deixar a operação parcial; o backup já existe
e o recibo permite recuperar os arquivos. Não há transação distribuída com GitHub.

O inventário de serviços usa o executável e o hash do plist, sem publicar
ProgramArguments, que podem conter tokens. A linha de base ajuda a detectar
alterações; não classifica automaticamente o que é legítimo.
Mudanças relevantes permanecem numa fila privada até uma investigação com
evidência, mesmo depois que a mudança deixa de ser nova no próximo check.

O reporter é herdado da base Plow, separado do coletor do Mac. Ele lê as sessões
reais do OpenClaw e precisa de AGENT_ID. A imagem pública contém apenas código,
persona e skills. Os dados pessoais não são montados no contêiner.
