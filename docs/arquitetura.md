# Arquitetura

O contêiner OpenClaw mantém a conversa, as ferramentas Plow e o registro de uso.
Latch transmite operações ao Mac de acordo com suas permissões. O helper Python
do Mac executa os comandos de manutenção, controla o escopo e guarda resultados.

O coletor local executa check a cada 15 minutos e check --full às 09:10.
Os jobs são de sessão do usuário. Eles não rodam quando o Mac está desligado;
launchd retoma no login ou após o despertar conforme suas regras.
Nenhum desses jobs chama um modelo nem envia dados ao Agent Index.

A política local controla raízes, idade e limites. A limpeza exige um plano
recente e repete as verificações imediatamente antes de remover. Projetos
alterados e worktrees gerenciados são preservados. A organização usa hardlinks
temporários no mesmo volume para publicar um destino sem sobrescrever arquivo.
O registro contém origem, destino e hash para desfazer a movimentação.

Um backup é um snapshot novo dentro de repositório privado. O helper clona,
envia, clona novamente e compara hashes. A exclusão local exige a opção offload,
uma origem autorizada e nova validação. Um recibo verificado é salvo antes de
começar a excluir, e cada arquivo removido tem um registro.
Uma falha durante offload pode deixar a operação parcial; o backup já existe
e o recibo permite recuperar os arquivos. Não há transação distribuída com GitHub.

O inventário de serviços usa o executável e o hash do plist, sem publicar
ProgramArguments, que podem conter tokens. A linha de base ajuda a detectar
alterações; não classifica automaticamente o que é legítimo.

O reporter é herdado da base Plow, separado do coletor do Mac. Ele lê as sessões
reais do OpenClaw e precisa de AGENT_ID. A imagem pública contém apenas código,
persona e skills. Os dados pessoais não são montados no contêiner.
