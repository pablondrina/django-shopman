"""Shop (singleton) and NotificationTemplate models."""

from __future__ import annotations

import os

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models

from shopman.shop.fonts import BODY_FONTS, HEADING_FONTS

SHOP_CACHE_KEY = "shop_singleton"
LOGO_ALLOWED_EXTENSIONS = {".svg", ".png", ".jpg", ".jpeg", ".webp"}
LOGO_MAX_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB


def validate_logo(value):
    """Validate logo file: extension and size."""
    ext = os.path.splitext(value.name)[1].lower()
    if ext not in LOGO_ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(LOGO_ALLOWED_EXTENSIONS))
        raise ValidationError(f"Formato não suportado ({ext}). Use: {allowed}")
    if value.size > LOGO_MAX_SIZE_BYTES:
        raise ValidationError(f"Arquivo muito grande ({value.size // 1024}KB). Máximo: 2MB.")


SHOP_CACHE_TTL = 60  # seconds


# ── Social link detection ──

_SOCIAL_PLATFORMS = [
    ("wa.me", "whatsapp", "WhatsApp"),
    ("whatsapp.com", "whatsapp", "WhatsApp"),
    ("instagram.com", "instagram", "Instagram"),
    ("facebook.com", "facebook", "Facebook"),
    ("fb.com", "facebook", "Facebook"),
    ("tiktok.com", "tiktok", "TikTok"),
    ("youtube.com", "youtube", "YouTube"),
    ("youtu.be", "youtube", "YouTube"),
    ("twitter.com", "x", "X"),
    ("x.com", "x", "X"),
    ("linkedin.com", "linkedin", "LinkedIn"),
    ("t.me", "telegram", "Telegram"),
    ("telegram.me", "telegram", "Telegram"),
    ("pinterest.com", "pinterest", "Pinterest"),
]

_SOCIAL_ICONS: dict[str, str] = {
    "whatsapp": '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>',
    "instagram": '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="5"/><circle cx="12" cy="12" r="5"/><circle cx="17.5" cy="6.5" r="1.5" fill="currentColor" stroke="none"/></svg>',
    "facebook": '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>',
    "tiktok": '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.5 2.89 2.89 0 01-2.89-2.89 2.89 2.89 0 012.89-2.89c.28 0 .54.04.79.1v-3.5a6.37 6.37 0 00-.79-.05A6.34 6.34 0 003.15 15.2a6.34 6.34 0 0010.86 4.46V13a8.18 8.18 0 005.58 2.17V11.7a4.77 4.77 0 01-3.77-1.78V6.69h3.77z"/></svg>',
    "youtube": '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 00-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 00.502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 002.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 002.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>',
    "x": '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>',
    "linkedin": '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>',
    "telegram": '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M11.944 0A12 12 0 000 12a12 12 0 0012 12 12 12 0 0012-12A12 12 0 0012 0a12 12 0 00-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 01.171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.479.33-.913.492-1.302.48-.428-.013-1.252-.242-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>',
    "pinterest": '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M12.017 0C5.396 0 .029 5.367.029 11.987c0 5.079 3.158 9.417 7.618 11.162-.105-.949-.199-2.403.041-3.439.219-.937 1.406-5.957 1.406-5.957s-.359-.72-.359-1.781c0-1.668.967-2.914 2.171-2.914 1.023 0 1.518.769 1.518 1.69 0 1.029-.655 2.568-.994 3.995-.283 1.194.599 2.169 1.777 2.169 2.133 0 3.772-2.249 3.772-5.495 0-2.873-2.064-4.882-5.012-4.882-3.414 0-5.418 2.561-5.418 5.207 0 1.031.397 2.138.893 2.738.098.119.112.224.083.345l-.333 1.36c-.053.22-.174.267-.402.161-1.499-.698-2.436-2.889-2.436-4.649 0-3.785 2.75-7.262 7.929-7.262 4.163 0 7.398 2.967 7.398 6.931 0 4.136-2.607 7.464-6.227 7.464-1.216 0-2.359-.631-2.75-1.378l-.748 2.853c-.271 1.043-1.002 2.35-1.492 3.146C9.57 23.812 10.763 24 12.017 24c6.624 0 11.99-5.367 11.99-11.988C24.007 5.367 18.641.001 12.017.001z"/></svg>',
}

_GENERIC_LINK_ICON = '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>'


def _resolve_social_link(url: str) -> dict:
    """Detect platform from URL and return {url, platform, label, icon_svg}."""
    url_lower = url.lower()
    for domain_fragment, platform, label in _SOCIAL_PLATFORMS:
        if domain_fragment in url_lower:
            return {
                "url": url,
                "platform": platform,
                "label": label,
                "icon_svg": _SOCIAL_ICONS.get(platform, _GENERIC_LINK_ICON),
            }
    from urllib.parse import urlparse

    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path
    domain = domain.replace("www.", "")
    return {
        "url": url,
        "platform": "website",
        "label": domain or "Site",
        "icon_svg": _GENERIC_LINK_ICON,
    }


class Shop(models.Model):
    """O estabelecimento. Singleton."""

    # ── Identidade ──
    name = models.CharField("nome fantasia", max_length=200)
    legal_name = models.CharField("razão social", max_length=200, blank=True)
    document = models.CharField("CNPJ/CPF", max_length=20, blank=True)

    # ── Endereço (padrão Google Places) ──
    formatted_address = models.CharField("endereço completo", max_length=500, blank=True,
        help_text="Endereço formatado completo (ex: Av. Madre Leônia Milito, 446 - Bela Suíça, Londrina - PR, 86050-270)")
    route = models.CharField("logradouro", max_length=200, blank=True)
    street_number = models.CharField("número", max_length=20, blank=True)
    complement = models.CharField("complemento", max_length=100, blank=True)
    neighborhood = models.CharField("bairro", max_length=100, blank=True)
    city = models.CharField("cidade", max_length=100, blank=True)
    state_code = models.CharField("UF", max_length=5, blank=True)
    postal_code = models.CharField("CEP", max_length=20, blank=True)
    country = models.CharField("país", max_length=100, default="Brasil")
    country_code = models.CharField("código do país", max_length=5, default="BR")
    latitude = models.DecimalField("latitude", max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField("longitude", max_digits=10, decimal_places=7, null=True, blank=True)
    place_id = models.CharField("Google Place ID", max_length=255, blank=True)

    # ── Contato ──
    phone = models.CharField("telefone", max_length=20, blank=True)
    email = models.EmailField("e-mail", blank=True)
    default_ddd = models.CharField("DDD padrão", max_length=4, default="11")

    # ── Operação ──
    currency = models.CharField("moeda", max_length=3, default="BRL")
    timezone = models.CharField("fuso horário", max_length=50, default="America/Sao_Paulo")
    opening_hours = models.JSONField(
        "horários",
        default=dict,
        blank=True,
        help_text=(
            'Horários por dia da semana. Exemplo: '
            '{"monday": {"open": "06:00", "close": "20:00"}, '
            '"tuesday": {"open": "06:00", "close": "20:00"}, ...}. '
            'Dias: monday, tuesday, wednesday, thursday, friday, saturday, sunday.'
        ),
    )

    # ── Branding ──
    brand_name = models.CharField("marca", max_length=100, blank=True)
    short_name = models.CharField("nome curto (PWA)", max_length=30, blank=True)
    tagline = models.CharField("tagline", max_length=200, blank=True)
    description = models.TextField("descrição", blank=True)
    conservation_tips_default = models.TextField(
        "dicas de conservação (padrão)",
        blank=True,
        help_text=(
            "Texto exibido no accordion de conservação do PDP quando o produto "
            "não tiver dica específica (Product.storage_tip). Cada produto pode "
            "sobrescrever individualmente."
        ),
    )
    primary_color = models.CharField("cor primária", max_length=9, default="#1a1a1a")
    logo = models.FileField(
        "logotipo", upload_to="branding/", blank=True,
        validators=[validate_logo],
        help_text="SVG, PNG, JPG ou WebP. Máximo 2MB. Exibido com altura de 40px no header.",
    )

    # ── Paleta de Cores (OKLCH) ──
    secondary_color = models.CharField(
        "cor secundária", max_length=9, blank=True, default="",
        help_text="Cor de apoio. Vazio = derivada automaticamente (hue +120° da primária)",
    )
    accent_color = models.CharField(
        "cor de destaque", max_length=9, blank=True, default="",
        help_text="Cor de destaque/CTA. Vazio = derivada automaticamente (hue -60° da primária)",
    )
    neutral_color = models.CharField(
        "tom neutro (claro)", max_length=9, blank=True, default="",
        help_text="Fundo da página no modo claro. Superfícies clareiam para branco. Vazio = creme derivado da primária.",
    )
    neutral_dark_color = models.CharField(
        "tom neutro (escuro)", max_length=9, blank=True, default="",
        help_text="Fundo da página no modo escuro. Superfícies escurecem para preto. Vazio = derivado do tom claro.",
    )
    COLOR_MODE_CHOICES = [
        ("light", "Claro"),
        ("dark", "Escuro"),
        ("auto", "Automático (sistema do usuário)"),
    ]
    color_mode = models.CharField(
        "modo de cor", max_length=10, default="light", choices=COLOR_MODE_CHOICES,
        help_text="Automático respeita a preferência de tema do sistema do usuário",
    )

    # ── Tipografia & Forma ──
    heading_font = models.CharField(
        "fonte de títulos", max_length=100, default="Inter",
        choices=HEADING_FONTS,
    )
    body_font = models.CharField(
        "fonte de corpo", max_length=100, default="Inter",
        choices=BODY_FONTS,
    )
    RADIUS_CHOICES = [
        ("square",  "Quadrado (0px)"),
        ("soft",    "Suave (8px)"),
        ("default", "Padrão (12px)"),
        ("strong",  "Forte (24px)"),
        ("round",   "Redondo (9999px)"),
    ]
    border_radius = models.CharField(
        "arredondamento", max_length=20, default="default", choices=RADIUS_CHOICES,
        help_text="Define o arredondamento dos cantos de botões, cards e inputs",
    )

    # ── Redes sociais ──
    social_links = models.JSONField(
        "redes sociais",
        default=list,
        blank=True,
        help_text=(
            'Lista de URLs das redes sociais. Exemplo:\n'
            '[\n'
            '  "https://wa.me/5511999999999",\n'
            '  "https://instagram.com/example",\n'
            '  "https://www.facebook.com/example",\n'
            '  "https://www.tiktok.com/@example",\n'
            '  "https://www.youtube.com/@example",\n'
            '  "https://twitter.com/example",\n'
            '  "https://www.example.com.br"\n'
            ']\n'
            'Plataformas reconhecidas: WhatsApp, Instagram, Facebook, TikTok, '
            'YouTube, X/Twitter, LinkedIn, Telegram, Pinterest. '
            'Qualquer outra URL aparece como ícone de link genérico.'
        ),
    )

    # ── Textos do acompanhamento (tracking page) ──
    tracking_copy = models.JSONField(
        "textos do acompanhamento",
        default=dict,
        blank=True,
        help_text=(
            "Mensagens exibidas ao cliente na página de acompanhamento do pedido.\n"
            "Deixe vazio para usar os textos padrão. Preencha apenas as que quiser personalizar.\n\n"
            "Chaves disponíveis:\n"
            '  "new" — pedido recebido, aguardando confirmação\n'
            '  "new_countdown" — texto acima do timer de confirmação\n'
            '  "confirmed" — pedido confirmado\n'
            '  "preparing" — pedido em preparo\n'
            '  "ready" — pedido pronto para retirada/entrega\n'
            '  "dispatched" — pedido saiu para entrega\n'
            '  "delivered" — pedido entregue\n'
            '  "completed" — pedido concluído\n'
            '  "cancelled" — pedido cancelado\n'
            '  "confirmed_celebration" — texto ao confirmar (timer zerou)\n'
        ),
    )

    # ── Defaults de negócio (cascata: canal ← AQUI ← hardcoded) ──
    defaults = models.JSONField(
        "configurações padrão",
        default=dict,
        blank=True,
        help_text="Mesmo schema do ChannelConfig. Canais herdam se não sobreescreverem.",
    )

    # ── Integrações (adapter selection — Admin-configurável) ──
    integrations = models.JSONField(
        "integrações",
        default=dict,
        blank=True,
        help_text=(
            "Seleção de adapters por tipo. Sobreescreve settings.py. "
            "Mesmo schema que SHOPMAN_*_ADAPTERS.\n\n"
            "Exemplo:\n"
            "{\n"
            '  "payment": {"pix": "shopman.shop.adapters.payment_efi", "card": "shopman.shop.adapters.payment_stripe"},\n'
            '  "notification": {"default": "shopman.shop.adapters.notification_manychat"},\n'
            '  "fiscal": "shopman.shop.adapters.fiscal_nfce"\n'
            "}"
        ),
    )

    class Meta:
        verbose_name = "loja"
        verbose_name_plural = "loja"
        permissions = [
            ("manage_orders", "Pode confirmar/rejeitar/avançar/cancelar pedidos"),
            ("manage_production", "Pode criar WorkOrders e avançar produção"),
            ("manage_catalog", "Pode criar/editar Product, Listing e Collection"),
            ("manage_customers", "Pode criar/editar Customer, grupos e loyalty"),
            ("view_reports", "Pode acessar dashboard e relatórios analíticos"),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if not self.defaults:
            return
        from shopman.shop.config import ChannelConfig, deep_merge

        try:
            config = ChannelConfig.from_dict(
                deep_merge(ChannelConfig.defaults(), self.defaults)
            )
            config.validate()
        except ValueError as exc:
            raise ValidationError({"defaults": str(exc)}) from exc

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(SHOP_CACHE_KEY)

    @classmethod
    def load(cls) -> Shop | None:
        shop = cache.get(SHOP_CACHE_KEY)
        if shop is None:
            shop = cls.objects.first()
            if shop is not None:
                cache.set(SHOP_CACHE_KEY, shop, SHOP_CACHE_TTL)
        return shop

    # ── Propriedades de compatibilidade (usadas nos templates) ──

    @property
    def theme_color(self) -> str:
        return self.primary_color or "#1a1a1a"

    @property
    def background_color(self) -> str:
        """Hex background color (derived from OKLCH neutral scale). Used by PWA manifest."""
        return self.design_tokens.get("background_hex", "#F5F0EB")

    @property
    def default_city(self) -> str:
        return self.city

    @property
    def location(self) -> str:
        if self.city and self.state_code:
            return f"{self.city} — {self.state_code}"
        return self.city or self.state_code or ""

    @property
    def phone_display(self) -> str:
        """Format phone for display: 554333231997 → (43) 3323-1997."""
        digits = "".join(c for c in self.phone if c.isdigit())
        if digits.startswith("55") and len(digits) >= 12:
            digits = digits[2:]  # strip country code
        if len(digits) == 11:
            return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
        if len(digits) == 10:
            return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
        return self.phone

    @property
    def phone_url(self) -> str:
        """Phone as tel: URI: 554333231997 → tel:+554333231997."""
        digits = "".join(c for c in self.phone if c.isdigit())
        if not digits:
            return ""
        if not digits.startswith("55"):
            digits = f"55{digits}"
        return f"tel:+{digits}"

    @property
    def whatsapp_url(self) -> str:
        """Phone as wa.me URI: 554333231997 → https://wa.me/554333231997.

        Prefers an explicit wa.me / whatsapp.com entry in social_links if present;
        otherwise falls back to deriving from `phone`.
        """
        for link in (self.social_links or []):
            if "wa.me" in link or "whatsapp.com" in link:
                return link
        digits = "".join(c for c in self.phone if c.isdigit())
        if not digits:
            return ""
        if not digits.startswith("55"):
            digits = f"55{digits}"
        return f"https://wa.me/{digits}"

    @property
    def full_address(self) -> str:
        """Full formatted address for display."""
        if self.formatted_address:
            return self.formatted_address
        parts = []
        street = self.route
        if street and self.street_number:
            street = f"{street}, {self.street_number}"
        if street and self.complement:
            street = f"{street} — {self.complement}"
        if street:
            parts.append(street)
        if self.neighborhood:
            parts.append(self.neighborhood)
        city_state = self.location
        if city_state:
            if self.postal_code:
                parts.append(f"{city_state} — CEP {self.postal_code}")
            else:
                parts.append(city_state)
        elif self.postal_code:
            parts.append(f"CEP {self.postal_code}")
        return "\n".join(parts)

    @property
    def maps_url(self) -> str:
        """Google Maps URL for the shop location."""
        if self.place_id:
            return f"https://www.google.com/maps/place/?q=place_id:{self.place_id}"
        if self.latitude and self.longitude:
            return f"https://www.google.com/maps/@{self.latitude},{self.longitude},17z"
        if self.formatted_address:
            from urllib.parse import quote
            return f"https://www.google.com/maps/search/?api=1&query={quote(self.formatted_address)}"
        return ""

    @property
    def social_links_resolved(self) -> list[dict]:
        """Resolve social_links URLs into display-ready dicts."""
        urls = self.social_links or []
        return [_resolve_social_link(url) for url in urls if url]

    @property
    def description_html(self) -> str:
        return self.description.replace("\n", "<br>")

    @property
    def design_tokens(self) -> dict:
        """Return complete design token dict for template rendering."""
        from shopman.shop.oxbow_tokens import build_storefront_design_tokens

        return build_storefront_design_tokens(
            heading_font=self.heading_font or "Inter",
            body_font=self.body_font or "Inter",
            color_mode=self.color_mode or "light",
        )


class NotificationTemplate(models.Model):
    """Template de notificação editável pelo lojista."""

    event = models.SlugField(
        "evento", max_length=50, unique=True,
        help_text="Identificador do evento (ex: order_confirmed, payment_refunded)",
    )
    subject = models.CharField(
        "assunto", max_length=200,
        help_text="Assunto do email. Suporta {placeholders}.",
    )
    body = models.TextField(
        "mensagem",
        help_text="Texto principal da notificação (WhatsApp-first). Suporta {placeholders}.",
    )
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["event"]
        verbose_name = "template de notificação"
        verbose_name_plural = "templates de notificação"

    def __str__(self):
        return f"{self.event} — {self.subject}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # TODO WP-R3: reconnect template cache invalidation via services
