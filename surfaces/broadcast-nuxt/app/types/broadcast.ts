// Contrato do Broadcast — espelha `shopman/backstage/projections/broadcast.py`.
// Chaves em inglês (convenção de projection); rótulos ficam na apresentação.

export interface PlatformResult {
  platform: string;
  label: string;
  status: "published" | "pending_manual" | "failed" | "queued" | string;
  detail: string;
  url: string;
}

export interface BroadcastPost {
  pk: number;
  status: string;
  status_label: string;
  body: string;
  image_url: string;
  hashtags: string[];
  link: string;
  platforms: string[];
  audience: Record<string, number>;
  audience_total: number;
  platform_results: PlatformResult[];
  trigger: string;
  trigger_label: string;
  rule_name: string;
  template_name: string;
  sku: string;
  created_at: string;
  expires_at: string;
  /** -1 = não expira; 0 = o prazo já passou. */
  expires_in_minutes: number;
  published_at: string;
  approved_by: string;
}

export interface BroadcastStats {
  pending_count: number;
  published_today: number;
  audience_reached_today: number;
  failed_today: number;
}

export interface BroadcastBoard {
  pending: BroadcastPost[];
  recent: BroadcastPost[];
  stats: BroadcastStats;
}

export interface BroadcastRule {
  pk: number;
  name: string;
  trigger: string;
  trigger_label: string;
  trigger_filter: Record<string, unknown>;
  template_id: number;
  template_name: string;
  platforms: string[];
  audience_rules: AudienceRules;
  schedule: Record<string, unknown>;
  requires_approval: boolean;
  expires_after_minutes: number;
  is_active: boolean;
}

export interface AudienceRules {
  favorites?: boolean;
  alerts?: boolean;
  recompra_days?: number;
  vip_first_minutes?: number;
}

export interface PostTemplate {
  pk: number;
  name: string;
  body: string;
  variables: string[];
  use_ai_generation: boolean;
  image_source: string;
  is_active: boolean;
}

export interface Choice {
  value: string;
  label: string;
}

export interface BroadcastOptions {
  triggers: Choice[];
  platforms: Choice[];
  templates: PostTemplate[];
  variables: string[];
}

export interface BoardResponse {
  board: BroadcastBoard;
}

export interface RulesResponse {
  rules: BroadcastRule[];
}

export interface OptionsResponse {
  options: BroadcastOptions;
}

export interface HistoryResponse {
  posts: BroadcastPost[];
}

/** Edições do card enviadas junto com a aprovação. */
export interface PostEdits {
  body?: string;
  hashtags?: string[];
  platforms?: string[];
  image_url?: string;
  publish_at?: string;
}
