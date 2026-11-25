# Modelo de roteiro (`roteiro/ROTEIRO.md`)

O `vdia` lê este arquivo: é a fonte única do texto. O usuário revisa e reescreve as falas aqui.

## Formato

- Cada cena começa com `## <número>. <título>`.
- Campos, um por linha, exatamente assim: `**Tela:**`, `**Fala:**`, `**Prova:**`, `**Transição:**`, `**Tempo:**`.
- `**Fala:**` é obrigatória (texto escrito, que vira a legenda). `**Transição:**` é a do xfade que **entra** na cena
  (padrão `fade`; a da cena 1 não é usada). `**Tempo:**` é preenchido por `vdia roteiro medir`.
- Cena N do roteiro = clipe `cenas/bruto<N-1>.*`.

## Exemplo (app de tarefas fictício)

```markdown
# Roteiro: App de tarefas

## 1. Abertura
**Tela:** [lista da semana com três projetos; o cursor percorre as tarefas e o painel de progresso]
**Fala:** O App de tarefas é um aplicativo web para organizar o trabalho da equipe, e com ele cada pessoa vê num só lugar o que vence e o que já foi feito.
**Prova:** src/paginas/Semana.tsx; src/componentes/Progresso.tsx
**Transição:** fade
**Tempo:** 8.9 s (29 palavras, 145 pal/min)

## 2. Filtro de hoje
**Tela:** [clique em "Hoje": sobram duas tarefas; o cursor passa por elas]
**Fala:** O filtro de hoje deixa só o que vence agora, sem rolar a lista inteira.
**Prova:** src/componentes/Filtros.tsx (filtro "hoje")
**Transição:** smoothleft
**Tempo:**

## 3. Concluir
**Tela:** [clique no círculo da 1ª tarefa: ela fica riscada e a barra de progresso sobe]
**Fala:** Ao concluir uma tarefa, a barra de progresso da semana se atualiza na hora; na proposta, o responsável também recebe um aviso.
**Prova:** src/acoes/concluir.ts; aviso ao responsável: não existe no código (proposta)
**Transição:** circleopen
**Tempo:**
```

## Como escrever

- Cena 1: o que é, para que serve, quem usa, o que melhora, em até 15 s.
- Uma frase por ação visível; descreva o que está na tela **naquele momento**.
- Conte ~2,4 palavras por segundo de ação no ritmo padrão (145 pal/min); o `medir` dá o tempo real.
- O que não existe no código vira "na proposta, ..." e a prova diz que é proposta.
- Siglas e nomes estrangeiros: escreva normalmente; a fonética cuida da fala (`vdia fonetica faltantes`).
- Números e datas: por extenso quando a voz tropeçar (teste na página `vdia fonetica servir`).
