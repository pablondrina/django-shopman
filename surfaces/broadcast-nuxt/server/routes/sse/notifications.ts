// Rota SSE same-origin do canal PESSOAL do gestor: /sse/notifications →
// streaming do eventstream do Django (/gestor/events/me/, canal `user-<id>`).
// Transporte na layer operator-kit (server/utils/eventStream.ts, auto-importado).
//
// O Django resolve o dono do canal pela sessão — o id do usuário nunca vem do
// cliente, então ninguém escuta a caixa alheia trocando um parâmetro.
export default defineEventHandler((event) => proxyEventStream(event, "/gestor/events/me/"));
