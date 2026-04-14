#!/usr/bin/env bash
# Download self-hosted fonts for Shopman storefront.
# Usage: bash scripts/download-fonts.sh
#
# Downloads Inter (body) and Playfair Display (heading) from Google Fonts
# in WOFF2 format for optimal performance.
# After running, the Google Fonts CDN links in _design_tokens.html can be removed.

set -euo pipefail

FONT_DIR="channels/web/static/storefront/fonts"
mkdir -p "$FONT_DIR"

echo "Downloading Inter (body font)..."
# Inter — Variable font, weights 400-700
curl -sL "https://fonts.gstatic.com/s/inter/v18/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuLyfAZ9hjQ.woff2" \
  -o "$FONT_DIR/inter-latin-400.woff2"
curl -sL "https://fonts.gstatic.com/s/inter/v18/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuI6fAZ9hjQ.woff2" \
  -o "$FONT_DIR/inter-latin-500.woff2"
curl -sL "https://fonts.gstatic.com/s/inter/v18/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuGKYAZ9hjQ.woff2" \
  -o "$FONT_DIR/inter-latin-600.woff2"
curl -sL "https://fonts.gstatic.com/s/inter/v18/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuFuYAZ9hjQ.woff2" \
  -o "$FONT_DIR/inter-latin-700.woff2"

echo "Downloading Playfair Display (heading font)..."
# Playfair Display — weights 400, 600, 700; plus italic 400, 600
curl -sL "https://fonts.gstatic.com/s/playfairdisplay/v37/nuFvD-vYSZviVYUb_rj3ij__anPXJzDwcbmjWBN2PKdFvXDXbtM.woff2" \
  -o "$FONT_DIR/playfair-latin-400.woff2"
curl -sL "https://fonts.gstatic.com/s/playfairdisplay/v37/nuFvD-vYSZviVYUb_rj3ij__anPXJzDwcbmjWBN2PKd1unDXbtM.woff2" \
  -o "$FONT_DIR/playfair-latin-600.woff2"
curl -sL "https://fonts.gstatic.com/s/playfairdisplay/v37/nuFvD-vYSZviVYUb_rj3ij__anPXJzDwcbmjWBN2PKdMunDXbtM.woff2" \
  -o "$FONT_DIR/playfair-latin-700.woff2"
curl -sL "https://fonts.gstatic.com/s/playfairdisplay/v37/nuFRD-vYSZviVYUb_rj3ij__anPXDTnCjmHKM4nYO7KN_qiTbtbK-F2rA0s.woff2" \
  -o "$FONT_DIR/playfair-latin-400i.woff2"
curl -sL "https://fonts.gstatic.com/s/playfairdisplay/v37/nuFRD-vYSZviVYUb_rj3ij__anPXDTnCjmHKM4nYO7KN_pqVbtbK-F2rA0s.woff2" \
  -o "$FONT_DIR/playfair-latin-600i.woff2"

echo "Done! Fonts saved to $FONT_DIR/"
echo "Verify with: ls -la $FONT_DIR/*.woff2"
