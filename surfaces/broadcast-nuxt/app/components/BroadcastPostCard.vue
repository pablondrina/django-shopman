<script setup lang="ts">
// O card acionável — a tela inteira do Broadcast existe por causa dele.
//
// O gestor lê, ajusta o texto, confere a audiência e decide. Tudo num gesto:
// as edições viajam JUNTO com a aprovação (um request), porque salvar e depois
// publicar abriria a janela de publicar a versão anterior.
import type { BroadcastPost, PostEdits } from "~/types/broadcast";
import {
  audienceSummary,
  displayHashtag,
  expiryLabel,
  expiryTone,
  parseHashtags,
  platformIcon,
  vipSummary,
} from "~/presentation/broadcast";

const props = defineProps<{
  post: BroadcastPost;
  platformOptions: { value: string; label: string }[];
  busy?: boolean;
}>();

const emit = defineEmits<{
  approve: [pk: number, edits: PostEdits];
  discard: [pk: number];
}>();

// Rascunho local. O card é um formulário: até decidir, nada vai pro servidor.
const body = ref(props.post.body);
const hashtagsText = ref(props.post.hashtags.map(displayHashtag).join(" "));
const platforms = ref<string[]>([...props.post.platforms]);
const scheduling = ref(false);
const publishAt = ref("");

// Post substituído por um refetch (SSE/poll) enquanto a tela estava aberta:
// re-sincroniza o rascunho SÓ quando é outro post, para não apagar a edição em
// curso a cada ciclo de poll.
watch(
  () => props.post.pk,
  () => {
    body.value = props.post.body;
    hashtagsText.value = props.post.hashtags.map(displayHashtag).join(" ");
    platforms.value = [...props.post.platforms];
    scheduling.value = false;
    publishAt.value = "";
  },
);

const expiry = computed(() => expiryLabel(props.post.expires_in_minutes));
const expiryClass = computed(
  () =>
    ({
      urgent: "bg-destructive/10 text-destructive",
      warning: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
      calm: "bg-muted text-muted-foreground",
      none: "",
    })[expiryTone(props.post.expires_in_minutes)],
);

const audience = computed(() => audienceSummary(props.post.audience));
const vip = computed(() => vipSummary(props.post.audience));

const canPublish = computed(
  () => !props.busy && body.value.trim().length > 0 && platforms.value.length > 0,
);

function togglePlatform(value: string) {
  const index = platforms.value.indexOf(value);
  if (index >= 0) platforms.value.splice(index, 1);
  else platforms.value.push(value);
}

function edits(): PostEdits {
  return {
    body: body.value.trim(),
    hashtags: parseHashtags(hashtagsText.value),
    platforms: [...platforms.value],
  };
}

function publishNow() {
  if (!canPublish.value) return;
  emit("approve", props.post.pk, edits());
}

function schedule() {
  if (!canPublish.value || !publishAt.value) return;
  emit("approve", props.post.pk, { ...edits(), publish_at: publishAt.value });
}
</script>

<template>
  <article class="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
    <!-- Cabeçalho: de onde veio e quanto tempo ainda vale -->
    <header class="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2.5">
      <Icon name="lucide:zap" class="size-4 text-muted-foreground" />
      <span class="text-sm font-semibold">{{ post.rule_name || "Post avulso" }}</span>
      <span v-if="post.trigger_label" class="text-xs text-muted-foreground">
        {{ post.trigger_label }}
      </span>
      <span v-if="post.sku" class="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
        {{ post.sku }}
      </span>
      <span
        v-if="expiry"
        class="ml-auto rounded-full px-2 py-0.5 text-xs font-semibold"
        :class="expiryClass"
      >
        {{ expiry }}
      </span>
    </header>

    <div class="flex flex-col gap-4 p-4 sm:flex-row">
      <!-- Foto do produto: o post é visual antes de ser texto -->
      <div class="shrink-0">
        <img
          v-if="post.image_url"
          :src="post.image_url"
          :alt="`Foto de ${post.sku || 'produto'}`"
          class="size-32 rounded-lg border border-border object-cover"
        >
        <div
          v-else
          class="grid size-32 place-items-center rounded-lg border border-dashed border-border bg-muted/40 text-muted-foreground"
        >
          <Icon name="lucide:image-off" class="size-6" />
        </div>
      </div>

      <div class="min-w-0 flex-1 space-y-3">
        <!-- Texto editável: o template escreveu o rascunho, o gestor dá o tom -->
        <div>
          <label :for="`body-${post.pk}`" class="mb-1 block text-xs font-semibold text-muted-foreground">
            Texto do post
          </label>
          <textarea
            :id="`body-${post.pk}`"
            v-model="body"
            rows="4"
            class="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-ring"
          ></textarea>
          <p v-if="!body.trim()" class="mt-1 text-xs text-destructive" role="alert">
            O post precisa de um texto.
          </p>
        </div>

        <!-- Hashtags: guardadas limpas, lidas com "#" -->
        <div>
          <label :for="`tags-${post.pk}`" class="mb-1 block text-xs font-semibold text-muted-foreground">
            Hashtags
          </label>
          <input
            :id="`tags-${post.pk}`"
            v-model="hashtagsText"
            type="text"
            placeholder="#padaria #fornada"
            class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
          >
        </div>

        <!-- Plataformas: pré-marcadas pela regra, o gestor tira ou põe -->
        <fieldset>
          <legend class="mb-1 text-xs font-semibold text-muted-foreground">Publicar em</legend>
          <div class="flex flex-wrap gap-1.5">
            <label
              v-for="option in platformOptions"
              :key="option.value"
              class="inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors"
              :class="platforms.includes(option.value)
                ? 'border-primary bg-primary/10 text-foreground'
                : 'border-border text-muted-foreground hover:bg-muted'"
            >
              <!-- O input é sr-only (a pílula é a affordance visual), então o nome
                   acessível precisa vir explícito — sem ele o leitor de tela anuncia
                   só "caixa de seleção". -->
              <input
                type="checkbox"
                class="sr-only"
                :aria-label="option.label"
                :checked="platforms.includes(option.value)"
                @change="togglePlatform(option.value)"
              >
              <Icon :name="platformIcon(option.value)" class="size-3.5" />
              {{ option.label }}
            </label>
          </div>
          <p v-if="platforms.length === 0" class="mt-1 text-xs text-destructive" role="alert">
            Escolha ao menos uma plataforma.
          </p>
        </fieldset>

        <!-- Audiência resolvida: quem recebe, e por quê -->
        <div class="rounded-lg bg-muted/50 px-3 py-2">
          <p class="flex items-center gap-1.5 text-sm">
            <Icon name="lucide:users" class="size-4 text-muted-foreground" />
            <span>{{ audience }}</span>
          </p>
          <p v-if="vip" class="mt-0.5 pl-6 text-xs text-muted-foreground">{{ vip }}</p>
        </div>
      </div>
    </div>

    <!-- Decisão -->
    <footer class="flex flex-wrap items-center gap-2 border-t border-border bg-muted/30 px-4 py-3">
      <button
        type="button"
        :disabled="!canPublish"
        class="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
        @click="publishNow"
      >
        <Icon :name="busy ? 'line-md:loading-loop' : 'lucide:send'" class="size-4" />
        Publicar agora
      </button>

      <button
        type="button"
        class="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm font-medium transition hover:bg-muted"
        :aria-expanded="scheduling"
        @click="scheduling = !scheduling"
      >
        <Icon name="lucide:clock" class="size-4" />
        Agendar
      </button>

      <button
        type="button"
        :disabled="busy"
        class="ml-auto inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm font-medium text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
        @click="emit('discard', post.pk)"
      >
        <Icon name="lucide:trash-2" class="size-4" />
        Descartar
      </button>

      <!-- Agendamento: aparece só quando pedido, para não pesar o caminho comum -->
      <div v-if="scheduling" class="flex w-full flex-wrap items-center gap-2 pt-2">
        <label :for="`when-${post.pk}`" class="text-sm text-muted-foreground">Publicar em</label>
        <input
          :id="`when-${post.pk}`"
          v-model="publishAt"
          type="datetime-local"
          class="h-9 rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
        >
        <button
          type="button"
          :disabled="!canPublish || !publishAt"
          class="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
          @click="schedule"
        >
          <Icon name="lucide:calendar-check" class="size-4" />
          Confirmar agendamento
        </button>
      </div>
    </footer>
  </article>
</template>
