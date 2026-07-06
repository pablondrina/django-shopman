// TS mirror of the generic operator session API
// (shopman/backstage/api/operations.py: operator/session|eligible|unlock|lock).
// Camada 2 da auth (Opção C): quem está operando agora, por PIN ou crachá.

export interface OperatorCard {
  id: number;
  username: string;
  name: string;
}

export interface OperatorSession {
  require_operator: boolean;
  device_user: string;
  operator: OperatorCard | null;
  locked: boolean;
  // O operador ativo recebeu um PIN temporário (reset do gerente) e precisa
  // trocá-lo antes de operar. O shell força a troca quando true.
  pin_must_change: boolean;
}

export type OperatorSessionResponse = OperatorSession;

export interface OperatorEligibleResponse {
  operators: OperatorCard[];
}

export interface OperatorUnlockResponse {
  ok: boolean;
  operator: OperatorCard;
}
